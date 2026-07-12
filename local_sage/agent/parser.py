"""Model output parsing utilities for extracting unified diffs and search-replace blocks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SearchReplaceBlock:
    """A single SEARCH/REPLACE edit block from model output.

    Attributes:
        search: Exact text to find in the target file.
        replace: Text to substitute in place of the search text.
    """

    search: str
    replace: str


class ModelOutputParser:
    """Extract unified diff or search-replace blocks from raw model output.

    Handles raw diffs, fenced code blocks, embedded diff sections, and
    SEARCH/REPLACE blocks.  Pure string processing with no I/O.
    """

    def extract_search_replace_blocks(self, raw: str) -> list[SearchReplaceBlock]:
        """Extract all SEARCH/REPLACE blocks from *raw*.

        Two-phase extraction — strict first, forgiving fallback only when
        the strict pass yields nothing.  Preserving the strict path as the
        primary ensures existing passing benchmarks are unaffected; the
        fallback addresses the format-drift observed in 7 B-parameter models
        that wrap output in markdown fences or use "SEARCH:" / "REPLACE:"
        keyword syntax instead of the angled-bracket delimiters.

        Strict form (must appear verbatim)::

            <<<<<<< SEARCH
            <exact text to find>
            =======
            <replacement text>
            >>>>>>> REPLACE

        Accepted fallback forms (tried in order):

        1. Angled-bracket block without "SEARCH"/"REPLACE" labels::

               <<<<<<< ...
               <search>
               =======
               <replace>
               >>>>>>> ...

        2. Keyword-colon form (with optional markdown fences inside)::

               SEARCH: <search text>
               REPLACE: <replace text>

        3. Bare-keyword block form::

               SEARCH
               <search text>
               REPLACE
               <replace text>
               (next SEARCH or end)

        Markdown fences (``` …language… ```) are stripped from the text
        before the fallback patterns are applied.

        Args:
            raw: Raw text from the model.

        Returns:
            List of :class:`SearchReplaceBlock` objects (may be empty).
        """
        # --- Phase 1: strict <<<<<<< SEARCH / >>>>>>> REPLACE ---
        blocks = self._extract_strict_blocks(raw)
        if blocks:
            return blocks

        # --- Phase 2: forgiving fallbacks ---
        cleaned = self._strip_markdown_fences(raw)

        blocks = self._extract_angle_bracket_blocks(cleaned)
        if blocks:
            import logging
            logging.getLogger(__name__).debug(
                "parser: used angle-bracket fallback (%d blocks)", len(blocks)
            )
            return blocks

        blocks = self._extract_keyword_colon_blocks(cleaned)
        if blocks:
            import logging
            logging.getLogger(__name__).debug(
                "parser: used SEARCH:/REPLACE: colon fallback (%d blocks)", len(blocks)
            )
            return blocks

        blocks = self._extract_hybrid_blocks(cleaned)
        if blocks:
            import logging
            logging.getLogger(__name__).debug(
                "parser: used hybrid SEARCH/======= fallback (%d blocks)", len(blocks)
            )
            return blocks

        blocks = self._extract_bare_keyword_blocks(cleaned)
        if blocks:
            import logging
            logging.getLogger(__name__).debug(
                "parser: used bare SEARCH/REPLACE keyword fallback (%d blocks)", len(blocks)
            )
            return blocks

        return []

    # ------------------------------------------------------------------
    # Strict extraction (original implementation, unchanged)
    # ------------------------------------------------------------------

    def _extract_strict_blocks(self, raw: str) -> list[SearchReplaceBlock]:
        """Extract blocks using the exact <<<<<<< / >>>>>>> delimiters."""
        blocks: list[SearchReplaceBlock] = []
        remaining = raw
        while True:
            block = self._extract_one_block(remaining)
            if block is None:
                break
            blocks.append(block)
            end_marker = ">>>>>>> REPLACE"
            idx = remaining.find(end_marker)
            if idx == -1:
                break
            remaining = remaining[idx + len(end_marker):]
        return blocks

    def _extract_one_block(self, text: str) -> SearchReplaceBlock | None:
        """Extract the first SEARCH/REPLACE block from *text*.

        Args:
            text: Text that may contain a SEARCH/REPLACE block.

        Returns:
            A :class:`SearchReplaceBlock` or ``None`` if not found.
        """
        start_marker = "<<<<<<< SEARCH"
        sep_marker = "======="
        end_marker = ">>>>>>> REPLACE"

        start = text.find(start_marker)
        if start == -1:
            return None
        after_start = start + len(start_marker)
        # skip the newline immediately after the marker
        if after_start < len(text) and text[after_start] == "\n":
            after_start += 1

        sep = text.find(sep_marker, after_start)
        if sep == -1:
            return None
        search_text = text[after_start:sep].rstrip("\n")

        after_sep = sep + len(sep_marker)
        if after_sep < len(text) and text[after_sep] == "\n":
            after_sep += 1

        end = text.find(end_marker, after_sep)
        if end == -1:
            return None
        replace_text = text[after_sep:end].rstrip("\n")

        return SearchReplaceBlock(search=search_text, replace=replace_text)

    # ------------------------------------------------------------------
    # Forgiving fallback helpers
    # ------------------------------------------------------------------

    def _strip_markdown_fences(self, text: str) -> str:
        """Remove ``` language ``` fence wrappers, keeping inner content.

        Handles ```python, ```plaintext, ```py, and plain ``` fences.
        Does not recurse — only one level of fences is stripped.
        """
        import re
        return re.sub(r"```[a-z]*\n?", "", text)

    def _extract_angle_bracket_blocks(self, text: str) -> list[SearchReplaceBlock]:
        """Accept <<< / >>> blocks that lack the SEARCH/REPLACE labels.

        Some models emit the angled-bracket structure but drop the keyword
        labels after the opening/closing markers.
        """
        import re
        pattern = re.compile(
            r"<{3,}.*?\n(.*?)\n={3,}\s*\n(.*?)\n>{3,}",
            re.DOTALL,
        )
        return [
            SearchReplaceBlock(search=m.group(1).strip(), replace=m.group(2).strip())
            for m in pattern.finditer(text)
            if m.group(1).strip()
        ]

    def _extract_hybrid_blocks(self, text: str) -> list[SearchReplaceBlock]:
        """Accept hybrid forms like SEARCH\\n...\\n=======\\n... (with or without >>>>>>> REPLACE)."""
        import re
        pattern = re.compile(
            r"SEARCH.*?\n(.*?)\n={3,}\s*\n(.*?)(?=\n>{3,}|\nSEARCH.*?\n|\Z)",
            re.DOTALL,
        )
        return [
            SearchReplaceBlock(search=m.group(1).strip(), replace=m.group(2).strip())
            for m in pattern.finditer(text)
            if m.group(1).strip()
        ]

    def _extract_keyword_colon_blocks(self, text: str) -> list[SearchReplaceBlock]:
        """Accept "SEARCH: <text> REPLACE: <text>" conversational form.

        The model consistently emits this when reminded via
        RETRY_FORMAT_REMINDER but still doesn't nail the strict delimiters.
        Leading/trailing whitespace and embedded blank lines are preserved
        in the captured content.
        """
        import re
        pattern = re.compile(
            r"SEARCH:\s*(.+?)\s*REPLACE:\s*(.+?)(?=\nSEARCH:|\Z)",
            re.DOTALL,
        )
        return [
            SearchReplaceBlock(search=m.group(1).strip(), replace=m.group(2).strip())
            for m in pattern.finditer(text)
            if m.group(1).strip()
        ]

    def _extract_bare_keyword_blocks(self, text: str) -> list[SearchReplaceBlock]:
        """Accept bare SEARCH / REPLACE section headings with body text.

        Handles output where the model uses SEARCH and REPLACE as plain
        section headers on their own lines without colons or brackets.
        """
        import re
        pattern = re.compile(
            r"^SEARCH\s*\n(.*?)\nREPLACE\s*\n(.*?)(?=\nSEARCH\s*\n|\Z)",
            re.DOTALL | re.MULTILINE,
        )
        return [
            SearchReplaceBlock(search=m.group(1).strip(), replace=m.group(2).strip())
            for m in pattern.finditer(text)
            if m.group(1).strip()
        ]


    def extract_diff(self, raw: str) -> str | None:
        """Return the diff substring from *raw*, or ``None`` if not found.

        Extraction priority (first match wins):

        1. ``raw`` starts with ``---`` after leading whitespace.
        2. Content inside a `` ```diff `` code fence.
        3. Content inside a plain `` ``` `` fence that contains ``---``.
        4. First line starting with ``---`` followed by a ``+++`` line.
        5. No match → ``None``.

        Args:
            raw: Raw text from the model.

        Returns:
            Extracted unified diff string, or ``None``.
        """
        if raw.lstrip().startswith("---"):
            return raw

        diff_fence = self._extract_fenced_diff(raw)
        if diff_fence is not None:
            return diff_fence

        plain_fence = self._extract_plain_fence_with_diff(raw)
        if plain_fence is not None:
            return plain_fence

        return self._extract_from_scan(raw)

    def extract_fenced_code(self, raw: str) -> str | None:
        """Extract content from a ```python or plain ``` code fence."""
        for marker in ("```python", "```py", "```"):
            if marker in raw:
                start = raw.index(marker) + len(marker)
                if start < len(raw) and raw[start] == "\n":
                    start += 1
                closing = raw.find("```", start)
                if closing != -1:
                    return raw[start:closing].strip()
        return None

    def _extract_fenced_diff(self, raw: str) -> str | None:
        """Extract content from a ```diff code fence."""
        marker = "```diff"
        if marker not in raw:
            return None
        start = raw.index(marker) + len(marker)
        if start < len(raw) and raw[start] == "\n":
            start += 1
        closing = raw.find("```", start)
        if closing == -1:
            return None
        return raw[start:closing].strip()

    def _extract_plain_fence_with_diff(self, raw: str) -> str | None:
        """Extract content from a plain ``` fence when it contains ---."""
        if "```" not in raw:
            return None
        first_fence = raw.index("```")
        after_fence = first_fence + 3
        newline_after = raw.find("\n", after_fence)
        if newline_after == -1:
            return None
        content_start = newline_after + 1
        closing_fence = raw.find("```", content_start)
        if closing_fence == -1:
            return None
        content = raw[content_start:closing_fence]
        if "---" not in content:
            return None
        return content.strip()

    def _extract_from_scan(self, raw: str) -> str | None:
        """Scan for the first --- line followed by +++."""
        lines = raw.splitlines()
        for i, line in enumerate(lines):
            if not line.startswith("---"):
                continue
            for j in range(i + 1, len(lines)):
                if not lines[j].strip():
                    continue
                if lines[j].startswith("+++"):
                    return "\n".join(lines[i:])
                break
        return None

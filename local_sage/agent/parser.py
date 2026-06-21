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

        Each block has the form::

            <<<<<<< SEARCH
            <exact text to find>
            =======
            <replacement text>
            >>>>>>> REPLACE

        Args:
            raw: Raw text from the model.

        Returns:
            List of :class:`SearchReplaceBlock` objects (may be empty).
        """
        blocks: list[SearchReplaceBlock] = []
        remaining = raw
        while True:
            block = self._extract_one_block(remaining)
            if block is None:
                break
            blocks.append(block)
            # Advance past the consumed block
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

"""Patch application utilities for Layer 6 — Validation.

Provides the :class:`Patcher` class, which applies unified diff patches or
search-replace blocks to a repository copy for validation and final apply.

Uses ``whatthepatch`` for pure-Python, cross-platform diff application.
The system ``patch -p1`` utility is intentionally **not** used.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

import whatthepatch

from local_sage.validation.exceptions import PatchError

logger = logging.getLogger(__name__)

_KNOWN_ROOTS = ("local_sage/", "tests/", "evals/", "wiki/", "contracts/")


class Patcher:
    """Applies unified diff patches or search-replace blocks to a repository.

    All diff application is done in pure Python via ``whatthepatch``.
    Search-replace application uses exact text matching — no line numbers.

    Example (unified diff)::

        patcher = Patcher()
        temp_dir = patcher.apply_to_temp(repo_root, patch_text)
        try:
            patcher.apply_to_repo(repo_root, patch_text)
        finally:
            patcher.revert(temp_dir)
    """

    # ------------------------------------------------------------------
    # Unified diff public API
    # ------------------------------------------------------------------

    def apply_to_temp(self, repo_root: Path, patch: str) -> Path:
        """Copy the repository to a temp directory and apply the patch there.

        Args:
            repo_root: Absolute path to the root of the repository.
            patch: Unified diff string to apply.

        Returns:
            Path to the temporary directory containing the patched copy.
        """
        temp_path = Path(tempfile.mkdtemp())
        shutil.copytree(repo_root, temp_path, dirs_exist_ok=True)
        self._apply_patch(temp_path, patch)
        return temp_path

    def apply_to_repo(self, repo_root: Path, patch: str) -> None:
        """Apply the unified diff directly to the real repository.

        Args:
            repo_root: Absolute path to the root of the repository.
            patch: Unified diff string to apply.
        """
        self._apply_patch(repo_root, patch)

    # ------------------------------------------------------------------
    # Search-replace public API
    # ------------------------------------------------------------------

    def apply_search_replace_to_temp(self, repo_root: Path, blocks: list) -> Path:
        """Copy repo to a temp dir and apply search-replace blocks there.

        Args:
            repo_root: Absolute path to the repository root.
            blocks: List of SearchReplaceBlock objects.

        Returns:
            Path to the patched temporary directory.
        """
        temp_path = Path(tempfile.mkdtemp())
        shutil.copytree(repo_root, temp_path, dirs_exist_ok=True)
        self.apply_search_replace(temp_path, blocks)
        return temp_path

    def apply_search_replace(self, repo_root: Path, blocks: list) -> None:
        """Apply a list of search-replace blocks to files under *repo_root*.

        No line numbers needed — pure exact text matching.

        Args:
            repo_root: Absolute path to the repository root.
            blocks: List of SearchReplaceBlock objects.

        Raises:
            PatchError: If any block's search text is missing or ambiguous.
        """
        for block in blocks:
            self._apply_one_block(repo_root, block)

    # ------------------------------------------------------------------
    # Shared cleanup
    # ------------------------------------------------------------------

    def revert(self, temp_dir: Path) -> None:
        """Remove the temporary directory created by apply_to_temp or similar.

        Args:
            temp_dir: Path to the temporary directory to remove.
        """
        shutil.rmtree(temp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Search-replace internals
    # ------------------------------------------------------------------

    def _apply_one_block(self, repo_root: Path, block: object) -> None:
        """Apply one search-replace block to a file under *repo_root*.

        Args:
            repo_root: Repository root directory.
            block: A SearchReplaceBlock with ``search`` and ``replace`` attrs.

        Raises:
            PatchError: If search text is not found or matches multiple files.
        """
        search_text: str = block.search  # type: ignore[attr-defined]
        replace_text: str = block.replace  # type: ignore[attr-defined]
        matches = self._find_files_with_text(repo_root, search_text)
        self._assert_single_match(matches, search_text)
        target = matches[0]
        original = target.read_text(encoding="utf-8")
        target.write_text(original.replace(search_text, replace_text, 1), encoding="utf-8")

    def _find_files_with_text(self, repo_root: Path, search_text: str) -> list[Path]:
        """Return all .py files under *repo_root* containing *search_text*.

        Args:
            repo_root: Repository root directory.
            search_text: Exact text to search for.

        Returns:
            List of matching Path objects.
        """
        return [
            f for f in repo_root.rglob("*.py")
            if search_text in f.read_text(encoding="utf-8")
        ]

    def _assert_single_match(self, matches: list[Path], search_text: str) -> None:
        """Raise PatchError if match count is not exactly one.

        Args:
            matches: Files containing the search text.
            search_text: The text that was searched for.

        Raises:
            PatchError: If zero or multiple files matched.
        """
        if len(matches) == 0:
            raise PatchError(
                "No valid diff hunks found in patch — search text not found "
                "in any file. explanation text may have been produced.",
                patch_preview=search_text[:200],
            )
        if len(matches) > 1:
            paths = ", ".join(str(m) for m in matches[:3])
            raise PatchError(
                f"No valid diff hunks found in patch — search text matches "
                f"{len(matches)} files ({paths}). "
                "explanation text may have been produced.",
                patch_preview=search_text[:200],
            )

    # ------------------------------------------------------------------
    # Unified diff internals
    # ------------------------------------------------------------------

    def _resolve_file_path(self, raw_path: str, target_dir: Path) -> Path | None:
        """Resolve a diff header path to an existing file under *target_dir*.

        Args:
            raw_path: File path from the diff header.
            target_dir: Root directory of the patched copy.

        Returns:
            Resolved existing path, or ``None`` if all strategies fail.
        """
        clean = raw_path.lstrip("ab/")
        candidate = target_dir / clean
        if candidate.exists():
            return candidate
        resolved = self._resolve_by_known_root(raw_path, target_dir)
        if resolved is not None:
            return resolved
        return self._resolve_by_filename(raw_path, target_dir, clean)

    def _resolve_by_known_root(self, raw_path: str, target_dir: Path) -> Path | None:
        """Try resolving *raw_path* by stripping to a known repository root."""
        for root in _KNOWN_ROOTS:
            idx = raw_path.find(root)
            if idx < 0:
                continue
            fallback = target_dir / raw_path[idx:]
            if fallback.exists():
                logger.warning("Patch path %s using fallback resolution", raw_path)
                return fallback
        return None

    def _resolve_by_filename(self, raw_path: str, target_dir: Path, clean: str) -> Path | None:
        """Try resolving *raw_path* by unique filename match under *target_dir*."""
        filename = Path(clean).name
        if not filename or any(c in filename for c in (":", "*", "?", '"', "<", ">", "|")):
            logger.warning("unresolvable path %s", raw_path)
            return None
        try:
            matches = list(target_dir.rglob(filename))
        except (NotImplementedError, ValueError):
            logger.warning("unresolvable path %s", raw_path)
            return None
        if len(matches) == 1:
            logger.warning("Patch path %s using fallback resolution", raw_path)
            return matches[0]
        logger.warning("unresolvable path %s", raw_path)
        return None

    def _apply_patch(self, target_dir: Path, patch: str) -> None:
        """Apply a unified diff string to *target_dir*.

        Args:
            target_dir: Directory against which the patch is applied.
            patch: Unified diff string.

        Raises:
            PatchError: If no valid hunks found or all hunks failed to apply.
        """
        diffs = list(whatthepatch.parse_patch(patch))
        if not diffs:
            raise PatchError(
                "No valid diff hunks found in patch — the model likely produced "
                "explanation text instead of a unified diff",
                patch_preview=patch[:200],
            )
        applied, skipped = self._apply_all_diffs(target_dir, diffs)
        if applied == 0 and skipped > 0:
            raise PatchError(
                "No valid diff hunks found in patch — all hunks failed to apply "
                "(context mismatch or missing files). "
                "explanation text may have been produced.",
                patch_preview=patch[:200],
            )

    def _apply_all_diffs(self, target_dir: Path, diffs: list) -> tuple[int, int]:
        """Apply each diff object and return (applied_count, skipped_count).

        Args:
            target_dir: Directory against which the diffs are applied.
            diffs: List of parsed diff objects from ``whatthepatch``.

        Returns:
            Tuple of (number applied, number skipped).
        """
        applied = 0
        skipped = 0
        for diff in diffs:
            if diff.changes is None:
                skipped += 1
                continue
            if getattr(diff, "header", None) is None:
                logger.warning("Skipping diff with no header — malformed patch")
                skipped += 1
                continue
            if self._apply_single_diff(target_dir, diff):
                applied += 1
            else:
                skipped += 1
        return applied, skipped

    def _apply_single_diff(
        self,
        target_dir: Path,
        diff: whatthepatch.patch.diffobj,
    ) -> bool:
        """Apply a single parsed diff object to a file inside *target_dir*.

        Args:
            target_dir: Root directory of the patched copy.
            diff: A parsed diff object from ``whatthepatch.parse_patch()``.

        Returns:
            True if the diff was successfully applied, False if skipped.
        """
        if getattr(diff, "header", None) is None:
            logger.warning("Skipping diff with no header — malformed patch")
            return False
        raw_path = diff.header.new_path or diff.header.old_path
        if raw_path is None:
            logger.warning("Skipping diff with no file path in header")
            return False
        file_path = self._resolve_file_path(raw_path, target_dir)
        if file_path is None:
            return False
        try:
            old_text = file_path.read_text(encoding="utf-8")
            new_lines: list[str] = list(whatthepatch.apply_diff(diff, old_text))
            new_text = "\n".join(new_lines)
            if old_text.endswith("\n"):
                new_text += "\n"
            file_path.write_text(new_text, encoding="utf-8")
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to apply diff to %s: %s", file_path, exc)
            return False

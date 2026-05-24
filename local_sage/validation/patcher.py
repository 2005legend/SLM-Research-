"""Patch application utilities for Layer 6 — Validation.

Provides the :class:`Patcher` class, which applies unified diff patches to
either a temporary copy of the repository (for safe validation) or directly
to the real repository (after all validators have passed).

Uses ``whatthepatch`` for pure-Python, cross-platform diff application.
The system ``patch -p1`` utility is intentionally **not** used.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

import whatthepatch

logger = logging.getLogger(__name__)


class Patcher:
    """Applies unified diff patches to a repository using ``whatthepatch``.

    All patch application is done in pure Python via the ``whatthepatch``
    library.  The system ``patch`` utility is never invoked, ensuring
    cross-platform compatibility.

    Example::

        patcher = Patcher()
        temp_dir = patcher.apply_to_temp(repo_root, patch_text)
        try:
            # run validators against temp_dir …
            patcher.apply_to_repo(repo_root, patch_text)
        finally:
            patcher.revert(temp_dir)
    """

    def apply_to_temp(self, repo_root: Path, patch: str) -> Path:
        """Copy the repository to a temp directory and apply the patch there.

        Creates a fresh temporary directory, copies the entire repository
        into it, then applies the unified diff using ``whatthepatch``.

        Args:
            repo_root: Absolute path to the root of the repository.
            patch: Unified diff string to apply.

        Returns:
            Path to the temporary directory containing the patched copy.
            The caller is responsible for cleaning it up (see
            :meth:`revert`).
        """
        temp_path = Path(tempfile.mkdtemp())
        shutil.copytree(repo_root, temp_path, dirs_exist_ok=True)
        self._apply_patch(temp_path, patch)
        return temp_path

    def apply_to_repo(self, repo_root: Path, patch: str) -> None:
        """Apply the patch directly to the real repository.

        This method should only be called after all validators have passed
        on the temporary copy produced by :meth:`apply_to_temp`.

        Args:
            repo_root: Absolute path to the root of the repository.
            patch: Unified diff string to apply.
        """
        self._apply_patch(repo_root, patch)

    def revert(self, temp_dir: Path) -> None:
        """Remove the temporary directory created by :meth:`apply_to_temp`.

        Uses ``shutil.rmtree`` with ``ignore_errors=True`` so that a
        missing or partially-deleted directory does not raise.

        Args:
            temp_dir: Path to the temporary directory to remove.
        """
        shutil.rmtree(temp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _apply_patch(self, target_dir: Path, patch: str) -> None:
        """Iterate over diffs in *patch* and apply each one to *target_dir*.

        Files that do not exist in *target_dir* are skipped with a warning.
        Diffs that ``whatthepatch`` cannot apply are also skipped with a
        warning so that a single bad hunk does not abort the entire patch.

        Args:
            target_dir: Directory against which the patch is applied.
            patch: Unified diff string (may contain multiple file diffs).
        """
        for diff in whatthepatch.parse_patch(patch):
            if diff.changes is None:
                continue
            self._apply_single_diff(target_dir, diff)

    def _apply_single_diff(
        self,
        target_dir: Path,
        diff: "whatthepatch.patch.diffobj",
    ) -> None:
        """Apply a single parsed diff object to a file inside *target_dir*.

        Args:
            target_dir: Root directory of the patched copy.
            diff: A parsed diff object from ``whatthepatch.parse_patch()``.
        """
        raw_path = diff.header.new_path or diff.header.old_path
        if raw_path is None:
            logger.warning("Skipping diff with no file path in header")
            return

        # Strip leading "a/" or "b/" prefixes produced by git diff.
        clean = raw_path.lstrip("ab/")
        file_path = target_dir / clean

        if not file_path.exists():
            logger.warning("Skipping patch for missing file: %s", file_path)
            return

        try:
            old_text = file_path.read_text(encoding="utf-8")
            new_lines: list[str] = list(whatthepatch.apply_diff(diff, old_text))
            new_text = "\n".join(new_lines)
            if old_text.endswith("\n"):
                new_text += "\n"
            file_path.write_text(new_text, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to apply diff to %s: %s", file_path, exc)

"""Unit tests for Patcher (Layer 6 — Validation).

Covers apply_to_temp(), revert(), and apply_to_repo() using the
``tmp_path`` pytest fixture for filesystem isolation.

**Validates: Requirements 6.1, 6.2, 6.3**
"""

from __future__ import annotations

from pathlib import Path

from local_sage.validation.patcher import Patcher

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repo(tmp_path: Path) -> Path:
    """Create a minimal fake repository under tmp_path.

    Creates:
        <tmp_path>/repo/
            local_sage/__init__.py
            local_sage/hello.py

    Args:
        tmp_path: Pytest-provided temporary directory.

    Returns:
        Path to the repo root.
    """
    repo = tmp_path / "repo"
    pkg = repo / "local_sage"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "hello.py").write_text("x = 1\n", encoding="utf-8")
    return repo


def _make_patch(filename: str, old_line: str, new_line: str) -> str:
    """Build a minimal unified diff patch string.

    Args:
        filename: Relative path to the file being patched.
        old_line: The line being replaced (without leading ``-``).
        new_line: The replacement line (without leading ``+``).

    Returns:
        A unified diff string.
    """
    return f"--- a/{filename}\n+++ b/{filename}\n@@ -1,1 +1,1 @@\n-{old_line}\n+{new_line}\n"


# ---------------------------------------------------------------------------
# Unit tests — apply_to_temp()
# ---------------------------------------------------------------------------


class TestApplyToTemp:
    """Unit tests for Patcher.apply_to_temp()."""

    def test_returns_a_path(self, tmp_path: Path) -> None:
        """apply_to_temp() returns a Path object."""
        repo = _make_repo(tmp_path)
        patcher = Patcher()
        temp_dir = patcher.apply_to_temp(repo, "")
        try:
            assert isinstance(temp_dir, Path)
        finally:
            patcher.revert(temp_dir)

    def test_temp_dir_exists_after_call(self, tmp_path: Path) -> None:
        """apply_to_temp() creates a directory that exists on disk."""
        repo = _make_repo(tmp_path)
        patcher = Patcher()
        temp_dir = patcher.apply_to_temp(repo, "")
        try:
            assert temp_dir.is_dir()
        finally:
            patcher.revert(temp_dir)

    def test_temp_dir_is_copy_of_repo(self, tmp_path: Path) -> None:
        """apply_to_temp() copies all repo files into the temp directory."""
        repo = _make_repo(tmp_path)
        patcher = Patcher()
        temp_dir = patcher.apply_to_temp(repo, "")
        try:
            assert (temp_dir / "local_sage" / "__init__.py").exists()
            assert (temp_dir / "local_sage" / "hello.py").exists()
        finally:
            patcher.revert(temp_dir)

    def test_temp_dir_is_different_from_repo(self, tmp_path: Path) -> None:
        """apply_to_temp() returns a path different from the original repo."""
        repo = _make_repo(tmp_path)
        patcher = Patcher()
        temp_dir = patcher.apply_to_temp(repo, "")
        try:
            assert temp_dir != repo
        finally:
            patcher.revert(temp_dir)

    def test_patch_is_applied_to_temp_dir(self, tmp_path: Path) -> None:
        """apply_to_temp() applies the patch to the temp copy, not the original."""
        repo = _make_repo(tmp_path)
        patch = _make_patch("local_sage/hello.py", "x = 1", "x = 42")
        patcher = Patcher()
        temp_dir = patcher.apply_to_temp(repo, patch)
        try:
            patched_content = (temp_dir / "local_sage" / "hello.py").read_text(encoding="utf-8")
            assert "42" in patched_content
        finally:
            patcher.revert(temp_dir)

    def test_original_repo_is_not_modified(self, tmp_path: Path) -> None:
        """apply_to_temp() does not modify the original repository files."""
        repo = _make_repo(tmp_path)
        original_content = (repo / "local_sage" / "hello.py").read_text(encoding="utf-8")
        patch = _make_patch("local_sage/hello.py", "x = 1", "x = 99")
        patcher = Patcher()
        temp_dir = patcher.apply_to_temp(repo, patch)
        try:
            current_content = (repo / "local_sage" / "hello.py").read_text(encoding="utf-8")
            assert current_content == original_content
        finally:
            patcher.revert(temp_dir)


# ---------------------------------------------------------------------------
# Unit tests — revert()
# ---------------------------------------------------------------------------


class TestRevert:
    """Unit tests for Patcher.revert()."""

    def test_revert_removes_temp_dir(self, tmp_path: Path) -> None:
        """revert() deletes the temporary directory from disk."""
        repo = _make_repo(tmp_path)
        patcher = Patcher()
        temp_dir = patcher.apply_to_temp(repo, "")
        assert temp_dir.is_dir()
        patcher.revert(temp_dir)
        assert not temp_dir.exists()

    def test_revert_is_idempotent(self, tmp_path: Path) -> None:
        """revert() does not raise when called on an already-deleted directory."""
        repo = _make_repo(tmp_path)
        patcher = Patcher()
        temp_dir = patcher.apply_to_temp(repo, "")
        patcher.revert(temp_dir)
        # Second call should not raise
        patcher.revert(temp_dir)

    def test_revert_on_nonexistent_path_does_not_raise(self, tmp_path: Path) -> None:
        """revert() silently ignores a path that does not exist."""
        patcher = Patcher()
        patcher.revert(tmp_path / "does_not_exist")


# ---------------------------------------------------------------------------
# Unit tests — apply_to_repo()
# ---------------------------------------------------------------------------


class TestApplyToRepo:
    """Unit tests for Patcher.apply_to_repo()."""

    def test_apply_to_repo_modifies_file_in_real_repo(self, tmp_path: Path) -> None:
        """apply_to_repo() writes the patched content to the real repository."""
        repo = _make_repo(tmp_path)
        patch = _make_patch("local_sage/hello.py", "x = 1", "x = 777")
        patcher = Patcher()
        patcher.apply_to_repo(repo, patch)
        content = (repo / "local_sage" / "hello.py").read_text(encoding="utf-8")
        assert "777" in content

    def test_apply_to_repo_with_empty_patch_leaves_files_unchanged(self, tmp_path: Path) -> None:
        """apply_to_repo() with an empty patch string leaves files unchanged."""
        repo = _make_repo(tmp_path)
        original = (repo / "local_sage" / "hello.py").read_text(encoding="utf-8")
        patcher = Patcher()
        patcher.apply_to_repo(repo, "")
        current = (repo / "local_sage" / "hello.py").read_text(encoding="utf-8")
        assert current == original

    def test_apply_to_repo_skips_missing_file_without_raising(self, tmp_path: Path) -> None:
        """apply_to_repo() skips a diff for a file that does not exist."""
        repo = _make_repo(tmp_path)
        patch = _make_patch("local_sage/nonexistent.py", "old", "new")
        patcher = Patcher()
        # Should not raise
        patcher.apply_to_repo(repo, patch)

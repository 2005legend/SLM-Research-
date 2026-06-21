"""Unit tests for Patcher (Layer 6 — Validation).

Covers apply_to_temp(), revert(), and apply_to_repo() using the
``tmp_path`` pytest fixture for filesystem isolation.

**Validates: Requirements 6.1, 6.2, 6.3**
"""

from __future__ import annotations

from pathlib import Path

import pytest

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


def _noop_patch(filename: str = "local_sage/hello.py") -> str:
    """Return a valid unified diff that leaves file content unchanged."""
    return (
        f"--- a/{filename}\n"
        f"+++ b/{filename}\n"
        f"@@ -1,1 +1,1 @@\n"
        f" x = 1\n"
        f" x = 1\n"
    )


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
        temp_dir = patcher.apply_to_temp(repo, _noop_patch())
        try:
            assert isinstance(temp_dir, Path)
        finally:
            patcher.revert(temp_dir)

    def test_temp_dir_exists_after_call(self, tmp_path: Path) -> None:
        """apply_to_temp() creates a directory that exists on disk."""
        repo = _make_repo(tmp_path)
        patcher = Patcher()
        temp_dir = patcher.apply_to_temp(repo, _noop_patch())
        try:
            assert temp_dir.is_dir()
        finally:
            patcher.revert(temp_dir)

    def test_temp_dir_is_copy_of_repo(self, tmp_path: Path) -> None:
        """apply_to_temp() copies all repo files into the temp directory."""
        repo = _make_repo(tmp_path)
        patcher = Patcher()
        temp_dir = patcher.apply_to_temp(repo, _noop_patch())
        try:
            assert (temp_dir / "local_sage" / "__init__.py").exists()
            assert (temp_dir / "local_sage" / "hello.py").exists()
        finally:
            patcher.revert(temp_dir)

    def test_temp_dir_is_different_from_repo(self, tmp_path: Path) -> None:
        """apply_to_temp() returns a path different from the original repo."""
        repo = _make_repo(tmp_path)
        patcher = Patcher()
        temp_dir = patcher.apply_to_temp(repo, _noop_patch())
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
        temp_dir = patcher.apply_to_temp(repo, _noop_patch())
        assert temp_dir.is_dir()
        patcher.revert(temp_dir)
        assert not temp_dir.exists()

    def test_revert_is_idempotent(self, tmp_path: Path) -> None:
        """revert() does not raise when called on an already-deleted directory."""
        repo = _make_repo(tmp_path)
        patcher = Patcher()
        temp_dir = patcher.apply_to_temp(repo, _noop_patch())
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

    def test_apply_to_repo_with_empty_patch_raises_patch_error(self, tmp_path: Path) -> None:
        """apply_to_repo() with an empty patch string raises PatchError."""
        from local_sage.validation.exceptions import PatchError

        repo = _make_repo(tmp_path)
        patcher = Patcher()
        with pytest.raises(PatchError):
            patcher.apply_to_repo(repo, "")

    def test_apply_to_repo_skips_missing_file_without_raising(self, tmp_path: Path) -> None:
        """apply_to_repo() raises PatchError when the target file does not exist.

        After the fix, a patch that references a non-existent file has all
        hunks failing, so PatchError is raised rather than silently skipping.
        """
        from local_sage.validation.exceptions import PatchError

        repo = _make_repo(tmp_path)
        patch = _make_patch("local_sage/nonexistent.py", "old", "new")
        patcher = Patcher()
        with pytest.raises(PatchError):
            patcher.apply_to_repo(repo, patch)


# ---------------------------------------------------------------------------
# Task 4.3 — Property 1 + unit tests for _resolve_file_path()
# ---------------------------------------------------------------------------

import logging

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st


class TestResolveFilePathUnit:
    """Unit tests for Patcher._resolve_file_path().

    Covers Step 0 (direct / a-b prefix strip), Step 1 (known-root strip),
    Step 2 (rglob by filename), and the None / unresolvable case.

    **Validates: Requirements 1.1, 1.2, 1.3, 1.4**
    """

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _make_target(self, tmp_path: Path) -> tuple[Path, Path]:
        """Create a minimal target_dir tree with one source file.

        Structure::

            <tmp_path>/target/
                local_sage/
                    utils.py

        Args:
            tmp_path: Pytest-provided temporary directory.

        Returns:
            Tuple of (target_dir, file_path) where file_path is the
            created source file.
        """
        target = tmp_path / "target"
        pkg = target / "local_sage"
        pkg.mkdir(parents=True)
        src = pkg / "utils.py"
        src.write_text("# stub\n", encoding="utf-8")
        return target, src

    # ------------------------------------------------------------------
    # Step 0 — direct resolution after a/ / b/ strip
    # ------------------------------------------------------------------

    def test_step0_a_prefix_resolves_directly_no_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """raw_path with 'a/' prefix resolves via Step 0 without any warning.

        Args:
            tmp_path: Pytest temporary directory.
            caplog: Pytest log capture fixture.
        """
        target, src = self._make_target(tmp_path)
        raw = "a/local_sage/utils.py"

        patcher = Patcher()
        with caplog.at_level(logging.WARNING, logger="local_sage.validation.patcher"):
            result = patcher._resolve_file_path(raw, target)

        assert result is not None
        assert result.exists()
        assert result == src
        # Step 0 must NOT emit any warning
        assert not any("fallback" in r.message for r in caplog.records)
        assert not any("unresolvable" in r.message for r in caplog.records)

    def test_step0_b_prefix_resolves_directly_no_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """raw_path with 'b/' prefix resolves via Step 0 without any warning.

        Args:
            tmp_path: Pytest temporary directory.
            caplog: Pytest log capture fixture.
        """
        target, src = self._make_target(tmp_path)
        raw = "b/local_sage/utils.py"

        patcher = Patcher()
        with caplog.at_level(logging.WARNING, logger="local_sage.validation.patcher"):
            result = patcher._resolve_file_path(raw, target)

        assert result is not None
        assert result.exists()
        assert result == src
        assert not any("fallback" in r.message for r in caplog.records)

    # ------------------------------------------------------------------
    # Step 1 — known-root strip fallback
    # ------------------------------------------------------------------

    def test_step1_known_root_prefix_emits_fallback_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """raw_path like 'myrepo/local_sage/utils.py' hits Step 1 and warns.

        The warning message must contain both "Patch path" and
        "using fallback resolution".

        Args:
            tmp_path: Pytest temporary directory.
            caplog: Pytest log capture fixture.
        """
        target, src = self._make_target(tmp_path)
        # Simulate model prefixing with an arbitrary repo folder name
        raw = "myrepo/local_sage/utils.py"

        patcher = Patcher()
        with caplog.at_level(logging.WARNING, logger="local_sage.validation.patcher"):
            result = patcher._resolve_file_path(raw, target)

        assert result is not None, "Step 1 should resolve the path"
        assert result.exists()
        assert result == src

        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any(
            "Patch path" in msg and "using fallback resolution" in msg
            for msg in warning_messages
        ), f"Expected fallback warning, got: {warning_messages}"

    # ------------------------------------------------------------------
    # Step 2 — rglob filename match fallback
    # ------------------------------------------------------------------

    def test_step2_rglob_unique_match_emits_fallback_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A path unresolvable by Steps 0/1 but unique by filename uses Step 2.

        The warning must contain "Patch path" and "using fallback resolution".

        Args:
            tmp_path: Pytest temporary directory.
            caplog: Pytest log capture fixture.
        """
        target = tmp_path / "target"
        # Deeply nested file with no known-root in path
        nested = target / "deep" / "nesting"
        nested.mkdir(parents=True)
        src = nested / "unique_module.py"
        src.write_text("# nested\n", encoding="utf-8")

        # raw_path has a completely unknown prefix — not a known root
        raw = "some/unknown/prefix/unique_module.py"

        patcher = Patcher()
        with caplog.at_level(logging.WARNING, logger="local_sage.validation.patcher"):
            result = patcher._resolve_file_path(raw, target)

        assert result is not None, "Step 2 rglob should find the unique file"
        assert result.exists()
        assert result == src

        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any(
            "Patch path" in msg and "using fallback resolution" in msg
            for msg in warning_messages
        ), f"Expected fallback warning, got: {warning_messages}"

    # ------------------------------------------------------------------
    # None case — unresolvable path
    # ------------------------------------------------------------------

    def test_unresolvable_path_returns_none_with_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A path that cannot be resolved by any strategy returns None and warns.

        The warning must contain "unresolvable".

        Args:
            tmp_path: Pytest temporary directory.
            caplog: Pytest log capture fixture.
        """
        target = tmp_path / "target"
        target.mkdir()
        # No files created — nothing can resolve

        raw = "totally/nonexistent/path/ghost.py"

        patcher = Patcher()
        with caplog.at_level(logging.WARNING, logger="local_sage.validation.patcher"):
            result = patcher._resolve_file_path(raw, target)

        assert result is None

        warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
        assert any(
            "unresolvable" in msg for msg in warning_messages
        ), f"Expected 'unresolvable' warning, got: {warning_messages}"


# ---------------------------------------------------------------------------
# Property test — Property 1
# ---------------------------------------------------------------------------


class TestResolveFilePathProperty:
    """Property-based tests for Patcher._resolve_file_path().

    **Property 1: Fallback resolution never silently discards a resolvable diff**

    For any raw_path string, if _resolve_file_path() returns a Path, then
    path.exists() must be True. If it returns None, a warning must have been
    emitted to the logger.

    **Validates: Requirements 1.1, 1.2, 1.3, 1.4**
    """

    @given(raw_path=st.text(min_size=1, max_size=200))
    @settings(max_examples=100)
    def test_property1_resolved_path_always_exists(self, raw_path: str) -> None:
        """For any raw_path: if resolve returns a Path, it must exist on disk.

        Creates a fresh temp directory inside the test body (not via a pytest
        fixture) so that Hypothesis can reset the filesystem state between
        generated inputs without triggering the function-scoped-fixture health
        check.  A small set of real files is seeded so that Hypothesis can
        occasionally find resolvable paths, exercising both the non-None and
        the None branches.

        **Validates: Requirements 1.1, 1.2, 1.3, 1.4**

        Args:
            raw_path: Arbitrary string drawn by Hypothesis.
        """
        import tempfile
        import shutil

        # Skip raw_paths that contain null bytes — illegal on all OSes.
        assume("\x00" not in raw_path)
        # Also skip paths that are just whitespace / empty after stripping,
        # which would resolve to target_dir itself (a directory, not a file).
        assume(raw_path.strip())

        tmp_dir = Path(tempfile.mkdtemp())
        try:
            # Build a small but realistic target directory so that some
            # generated raw_path values actually resolve.
            target = tmp_dir / "target"
            (target / "local_sage").mkdir(parents=True, exist_ok=True)
            (target / "tests").mkdir(parents=True, exist_ok=True)
            (target / "local_sage" / "core.py").write_text("", encoding="utf-8")
            (target / "tests" / "test_core.py").write_text("", encoding="utf-8")

            patcher = Patcher()

            # Capture warnings by monkey-patching the module logger so we
            # can assert the None branch always emits a warning.
            warning_calls: list[str] = []
            logger_obj = logging.getLogger("local_sage.validation.patcher")
            original_warning = logger_obj.warning

            def _capture_warning(msg: str, *args: object, **kwargs: object) -> None:
                formatted = msg % args if args else msg
                warning_calls.append(formatted)
                original_warning(msg, *args, **kwargs)

            logger_obj.warning = _capture_warning  # type: ignore[method-assign]

            try:
                result = patcher._resolve_file_path(raw_path, target)
            finally:
                logger_obj.warning = original_warning  # type: ignore[method-assign]

            # Core property: if a path was returned, it MUST exist on disk
            if result is not None:
                assert result.exists(), (
                    f"_resolve_file_path({raw_path!r}, ...) returned {result!r} "
                    f"but that path does not exist"
                )
            else:
                # None case: a warning must have been emitted (unresolvable path)
                assert len(warning_calls) > 0, (
                    f"_resolve_file_path({raw_path!r}, ...) returned None "
                    f"without emitting any warning"
                )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

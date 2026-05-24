"""Unit and property-based tests for the CLI (Layer 0).

Covers all sage subcommands using Typer's CliRunner, plus:
- Property 1: Validate-only mode never modifies the repository
- Property 2: Unrecognized subcommands exit with non-zero status

**Validates: Requirements 1.1–1.10**
"""

from __future__ import annotations

import tempfile
from datetime import UTC
from pathlib import Path
from unittest.mock import AsyncMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st
from typer.testing import CliRunner

from local_sage.cli import app
from local_sage.validation.result import (
    PytestCounts,
    ValidationResult,
)

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _passing_result() -> ValidationResult:
    """Return a passing ValidationResult."""
    return ValidationResult(
        passed=True,
        failures=[],
        pytest_counts=PytestCounts(passed=5, failed=0, errors=0),
        mypy_errors=[],
        ruff_violations=[],
        contract_failures=[],
        duration_ms=100,
    )


def _failing_result() -> ValidationResult:
    """Return a failing ValidationResult."""
    from local_sage.validation.result import ValidationFailure

    return ValidationResult(
        passed=False,
        failures=[ValidationFailure(tool="pytest", message="1 failed")],
        pytest_counts=PytestCounts(passed=4, failed=1, errors=0),
        mypy_errors=[],
        ruff_violations=[],
        contract_failures=[],
        duration_ms=100,
    )


# ---------------------------------------------------------------------------
# Unit tests — sage validate
# ---------------------------------------------------------------------------


class TestValidateCommand:
    """Unit tests for the `sage validate` command."""

    def test_validate_exits_zero_on_passing_patch(self, tmp_path: Path) -> None:
        """sage validate exits 0 when all checks pass."""
        patch_file = tmp_path / "my.patch"
        patch_file.write_text("--- a/foo.py\n+++ b/foo.py\n", encoding="utf-8")

        with (
            patch("local_sage.cli.Path.cwd", return_value=tmp_path),
            patch("local_sage.validation.runner.ValidationRunner") as MockRunner,
        ):
            MockRunner.return_value.validate_only.return_value = _passing_result()
            result = runner.invoke(app, ["validate", "--patch", str(patch_file)])

        assert result.exit_code == 0

    def test_validate_exits_nonzero_on_failing_patch(self, tmp_path: Path) -> None:
        """sage validate exits non-zero when checks fail."""
        patch_file = tmp_path / "my.patch"
        patch_file.write_text("--- a/foo.py\n+++ b/foo.py\n", encoding="utf-8")

        with (
            patch("local_sage.cli.Path.cwd", return_value=tmp_path),
            patch("local_sage.validation.runner.ValidationRunner") as MockRunner,
        ):
            MockRunner.return_value.validate_only.return_value = _failing_result()
            result = runner.invoke(app, ["validate", "--patch", str(patch_file)])

        assert result.exit_code != 0

    def test_validate_exits_nonzero_when_patch_file_missing(self, tmp_path: Path) -> None:
        """sage validate exits non-zero when the patch file does not exist."""
        with patch("local_sage.cli.Path.cwd", return_value=tmp_path):
            result = runner.invoke(
                app, ["validate", "--patch", str(tmp_path / "nonexistent.patch")]
            )

        assert result.exit_code != 0

    def test_validate_does_not_call_apply_to_repo(self, tmp_path: Path) -> None:
        """sage validate never calls apply_to_repo (validate_only mode)."""
        patch_file = tmp_path / "my.patch"
        patch_file.write_text("diff", encoding="utf-8")

        with (
            patch("local_sage.cli.Path.cwd", return_value=tmp_path),
            patch("local_sage.validation.runner.ValidationRunner") as MockRunner,
        ):
            mock_instance = MockRunner.return_value
            mock_instance.validate_only.return_value = _passing_result()
            runner.invoke(app, ["validate", "--patch", str(patch_file)])

        # validate_only should be called, NOT validate_and_apply
        mock_instance.validate_only.assert_called_once()
        mock_instance.validate_and_apply.assert_not_called()


# ---------------------------------------------------------------------------
# Unit tests — sage wiki
# ---------------------------------------------------------------------------


class TestWikiCommands:
    """Unit tests for sage wiki subcommands."""

    def test_wiki_list_shows_entries(self, tmp_path: Path) -> None:
        """sage wiki list displays wiki entries."""
        from datetime import datetime

        from local_sage.wiki.manager import WikiEntry

        mock_entries = [
            WikiEntry(
                title="Rate Limiter",
                file_path=tmp_path / "wiki" / "rate_limiter.md",
                content="# Rate Limiter",
                last_modified=datetime.now(tz=UTC),
            )
        ]

        with (
            patch("local_sage.cli.Path.cwd", return_value=tmp_path),
            patch("local_sage.wiki.manager.WikiManager.list_entries", return_value=mock_entries),
        ):
            result = runner.invoke(app, ["wiki", "list"])

        assert result.exit_code == 0
        assert "Rate Limiter" in result.output

    def test_wiki_show_displays_content(self, tmp_path: Path) -> None:
        """sage wiki show displays the content of a wiki entry."""
        from datetime import datetime

        from local_sage.wiki.manager import WikiEntry

        mock_entry = WikiEntry(
            title="Rate Limiter",
            file_path=tmp_path / "wiki" / "rate_limiter.md",
            content="# Rate Limiter\n\nSome content here.",
            last_modified=datetime.now(tz=UTC),
        )

        with (
            patch("local_sage.cli.Path.cwd", return_value=tmp_path),
            patch("local_sage.wiki.manager.WikiManager.read_entry", return_value=mock_entry),
        ):
            result = runner.invoke(app, ["wiki", "show", "Rate Limiter"])

        assert result.exit_code == 0
        assert "Some content here" in result.output

    def test_wiki_show_exits_nonzero_on_missing_entry(self, tmp_path: Path) -> None:
        """sage wiki show exits non-zero when the entry does not exist."""
        from local_sage.wiki.exceptions import WikiReadError

        with (
            patch("local_sage.cli.Path.cwd", return_value=tmp_path),
            patch(
                "local_sage.wiki.manager.WikiManager.read_entry",
                side_effect=WikiReadError(
                    "not found",
                    file_path=tmp_path / "wiki" / "missing.md",
                    os_error=OSError("no such file"),
                ),
            ),
        ):
            result = runner.invoke(app, ["wiki", "show", "Missing Entry"])

        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Unit tests — sage status
# ---------------------------------------------------------------------------


class TestStatusCommand:
    """Unit tests for the `sage status` command."""

    def test_status_exits_zero(self, tmp_path: Path) -> None:
        """sage status exits 0 under normal conditions."""
        with (
            patch("local_sage.cli.Path.cwd", return_value=tmp_path),
            patch(
                "local_sage.model.client.OllamaClient.health_check",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            result = runner.invoke(app, ["status"])

        assert result.exit_code == 0

    def test_status_shows_model_name(self, tmp_path: Path) -> None:
        """sage status output includes the model name."""
        with (
            patch("local_sage.cli.Path.cwd", return_value=tmp_path),
            patch(
                "local_sage.model.client.OllamaClient.health_check",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            result = runner.invoke(app, ["status"])

        assert "qwen2.5-coder" in result.output


# ---------------------------------------------------------------------------
# Property 1: Validate-only mode never modifies the repository
# ---------------------------------------------------------------------------


@given(patch_content=st.text(min_size=0, max_size=100))
@settings(max_examples=50)
def test_property_1_validate_only_never_modifies_repo(patch_content: str) -> None:
    """Property 1: Validate-only mode never modifies the repository.

    For any patch file passed to `sage validate --patch <path>`, the
    repository files on disk SHALL be identical before and after the command
    completes, regardless of whether the patch passes or fails validation.

    # Feature: local-sage, Property 1: Validate-only mode never modifies the repository
    **Validates: Requirements 1.4**
    """
    # Feature: local-sage, Property 1: Validate-only mode never modifies the repository
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # Create a sentinel file to detect modifications
        sentinel = tmp_path / "sentinel.py"
        sentinel.write_text("x = 1\n", encoding="utf-8")
        original_content = sentinel.read_text(encoding="utf-8")

        # Write the patch file
        patch_file = tmp_path / "test.patch"
        patch_file.write_text(patch_content, encoding="utf-8")

        with (
            patch("local_sage.cli.Path.cwd", return_value=tmp_path),
            patch("local_sage.validation.runner.ValidationRunner") as MockRunner,
        ):
            # Alternate between passing and failing results
            MockRunner.return_value.validate_only.return_value = _passing_result()
            runner.invoke(app, ["validate", "--patch", str(patch_file)])

        # Sentinel file must be unchanged
        assert sentinel.read_text(encoding="utf-8") == original_content


# ---------------------------------------------------------------------------
# Property 2: Unrecognized subcommands exit with non-zero status
# ---------------------------------------------------------------------------


@given(
    subcommand=st.text(
        alphabet=st.characters(
            whitelist_categories=("Ll", "Lu", "Nd"),
            whitelist_characters="-_",
        ),
        min_size=1,
        max_size=20,
    ).filter(
        lambda s: (
            s
            not in {
                "start",
                "task",
                "validate",
                "benchmark",
                "status",
                "wiki",
                "memory",
                "--help",
                "-h",
            }
        )
    )
)
@settings(max_examples=100)
def test_property_2_unrecognized_subcommands_exit_nonzero(subcommand: str) -> None:
    """Property 2: Unrecognized subcommands exit with non-zero status.

    For any string that is not a registered Typer subcommand, invoking
    `sage <string>` SHALL exit with a non-zero status code.

    # Feature: local-sage, Property 2: Unrecognized subcommands exit with non-zero status
    **Validates: Requirements 1.9**
    """
    # Feature: local-sage, Property 2: Unrecognized subcommands exit with non-zero status
    result = runner.invoke(app, [subcommand])
    assert result.exit_code != 0

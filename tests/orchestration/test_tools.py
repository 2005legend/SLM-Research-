"""Unit tests for LangGraph tools (Layer 2 — Orchestration).

Covers read_file, write_wiki, and run_tests tools.

**Validates: Requirements 7.1**
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from local_sage.orchestration.tools import read_file, run_tests, write_wiki
from local_sage.validation.result import PytestCounts


class TestReadFileTool:
    """Unit tests for the read_file tool."""

    def test_read_file_returns_file_contents(self, tmp_path: Path) -> None:
        """read_file() returns the text content of an existing file."""
        test_file = tmp_path / "hello.py"
        test_file.write_text("x = 1\n", encoding="utf-8")

        with patch("local_sage.orchestration.tools.Path.cwd", return_value=tmp_path):
            result = read_file.invoke({"path": "hello.py"})

        assert result == "x = 1\n"

    def test_read_file_returns_error_string_for_missing_file(self, tmp_path: Path) -> None:
        """read_file() returns an error string when the file does not exist."""
        with patch("local_sage.orchestration.tools.Path.cwd", return_value=tmp_path):
            result = read_file.invoke({"path": "nonexistent.py"})

        assert "Error" in result

    def test_read_file_uses_pathlib_path(self, tmp_path: Path) -> None:
        """read_file() constructs the path using pathlib.Path."""
        test_file = tmp_path / "sub" / "module.py"
        test_file.parent.mkdir()
        test_file.write_text("y = 2\n", encoding="utf-8")

        with patch("local_sage.orchestration.tools.Path.cwd", return_value=tmp_path):
            result = read_file.invoke({"path": "sub/module.py"})

        assert result == "y = 2\n"


class TestWriteWikiTool:
    """Unit tests for the write_wiki tool."""

    def test_write_wiki_creates_entry(self, tmp_path: Path) -> None:
        """write_wiki() creates a wiki entry via WikiManager."""
        with (
            patch("local_sage.orchestration.tools.Path.cwd", return_value=tmp_path),
            patch("local_sage.wiki.manager.WikiManager") as MockWiki,
        ):
            mock_instance = MockWiki.return_value
            write_wiki.invoke({"title": "My Entry", "content": "# Hello"})

        mock_instance.write_entry.assert_called_once_with("My Entry", "# Hello")

    def test_write_wiki_does_not_raise_on_error(self, tmp_path: Path) -> None:
        """write_wiki() does not raise when WikiManager.write_entry fails."""
        with (
            patch("local_sage.orchestration.tools.Path.cwd", return_value=tmp_path),
            patch("local_sage.wiki.manager.WikiManager") as MockWiki,
        ):
            MockWiki.return_value.write_entry.side_effect = OSError("disk full")
            # Should not raise
            write_wiki.invoke({"title": "Entry", "content": "content"})


class TestRunTestsTool:
    """Unit tests for the run_tests tool."""

    def test_run_tests_returns_summary_string(self, tmp_path: Path) -> None:
        """run_tests() returns a human-readable summary string."""
        mock_counts = PytestCounts(passed=10, failed=0, errors=0)

        with (
            patch("local_sage.orchestration.tools.Path.cwd", return_value=tmp_path),
            patch("local_sage.validation.pytest_runner.PytestRunner") as MockRunner,
        ):
            MockRunner.return_value.run.return_value = mock_counts
            result = run_tests.invoke({"test_path": None})

        assert "10 passed" in result
        assert "0 failed" in result

    def test_run_tests_returns_error_string_on_exception(self, tmp_path: Path) -> None:
        """run_tests() returns an error string when PytestRunner raises."""
        with (
            patch("local_sage.orchestration.tools.Path.cwd", return_value=tmp_path),
            patch("local_sage.validation.pytest_runner.PytestRunner") as MockRunner,
        ):
            MockRunner.return_value.run.side_effect = Exception("pytest not found")
            result = run_tests.invoke({"test_path": None})

        assert "Error" in result

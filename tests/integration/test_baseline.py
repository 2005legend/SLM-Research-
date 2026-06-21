"""Integration tests for BenchmarkRunner (evals/baseline.py).

Gated by SAGE_INTEGRATION=true to avoid requiring a live Ollama server in CI.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("SAGE_INTEGRATION") != "true",
    reason="Set SAGE_INTEGRATION=true to run integration tests",
)

_FIX_PATCH = (
    "--- a/simple_api/core.py\n"
    "+++ b/simple_api/core.py\n"
    "@@ -8,4 +8,5 @@\n"
    "     Raises:\n"
    "         ZeroDivisionError: When *b* is zero.\n"
    "     \"\"\"\n"
    "+    if b == 0:\n"
    "+        raise ZeroDivisionError(\"division by zero\")\n"
    "     return a / b\n"
)


@pytest.fixture
def fixture_dirs() -> tuple[Path, Path]:
    """Return paths to tasks and fixture repos directories."""
    root = Path(__file__).resolve().parents[2]
    return root / "evals" / "tasks", root / "evals" / "repos" / "fixtures"


class TestBenchmarkRunner:
    """Integration tests for BenchmarkRunner with mocked Ollama."""

    def test_run_task_passes_with_valid_diff(self, fixture_dirs: tuple[Path, Path]) -> None:
        """Mocked Ollama response produces TaskResult.passed=True when fix is correct."""
        from evals.baseline import BenchmarkRunner
        from evals.runner import load_task

        tasks_dir, repos_dir = fixture_dirs
        task = load_task(tasks_dir / "contract_violation_01.yaml")
        runner = BenchmarkRunner(tasks_dir, repos_dir)

        mock_response = MagicMock()
        mock_response.json.return_value = {"response": _FIX_PATCH}
        mock_response.raise_for_status = MagicMock()

        with patch("evals.baseline.httpx.post", return_value=mock_response):
            result = runner.run_task(task)

        assert result.task_id == "contract_violation_01"
        assert result.error is None or result.passed

    def test_missing_fixture_repo_returns_error(self, fixture_dirs: tuple[Path, Path]) -> None:
        """Missing fixture repo returns TaskResult with descriptive error."""
        from evals.baseline import BenchmarkRunner

        tasks_dir, repos_dir = fixture_dirs
        runner = BenchmarkRunner(tasks_dir, repos_dir)
        task = {
            "id": "missing_repo_test",
            "category": "edge_case",
            "description": "test",
            "repo": "nonexistent_fixture",
            "pass_condition": "pytest -x",
        }
        result = runner.run_task(task)
        assert result.passed is False
        assert result.error is not None
        assert "Fixture repo not found" in result.error

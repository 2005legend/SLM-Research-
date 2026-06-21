"""Baseline benchmark runner — raw Ollama with zero scaffolding.

Measures raw model performance without repo graph, session memory, wiki,
or retry loop. Used as a comparison baseline against the full local-sage agent.

Usage::

    python evals/baseline.py
    python evals/baseline.py --tasks-dir evals/tasks --repos-dir evals/repos/fixtures
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

from evals.runner import (
    BenchmarkReport,
    TaskResult,
    load_task,
    print_report,
)

logger = logging.getLogger(__name__)

_DEFAULT_TASKS_DIR = Path(__file__).parent / "tasks"
_DEFAULT_REPOS_DIR = Path(__file__).parent / "repos" / "fixtures"
_OLLAMA_URL = "http://localhost:11434/api/generate"
_DEFAULT_MODEL = "qwen2.5-coder:7b"


class BenchmarkRunner:
    """Run benchmark tasks against raw Ollama output with no agent scaffolding.

    Attributes:
        tasks_dir: Directory containing task YAML files.
        repos_dir: Directory containing fixture repositories.
    """

    def __init__(self, tasks_dir: Path, repos_dir: Path) -> None:
        """Initialise the runner with task and fixture directories.

        Args:
            tasks_dir: Path to the directory of task YAML files.
            repos_dir: Path to the directory of fixture repositories.
        """
        self.tasks_dir = tasks_dir
        self.repos_dir = repos_dir

    def run_all(self) -> BenchmarkReport:
        """Run all tasks and return an aggregated report.

        Returns:
            A :class:`BenchmarkReport` with per-task results.
        """
        report = BenchmarkReport()
        yaml_files = sorted(self.tasks_dir.glob("*.yaml"))
        for yaml_path in yaml_files:
            try:
                task = load_task(yaml_path)
            except (ValueError, Exception) as exc:  # noqa: BLE001
                logger.error("Failed to load task %s: %s", yaml_path, exc)
                continue
            result = self.run_task(task)
            report.results.append(result)
            report.total += 1
            if result.passed:
                report.passed += 1
            cat = result.category
            if cat not in report.by_category:
                report.by_category[cat] = {"total": 0, "passed": 0}
            report.by_category[cat]["total"] += 1
            if result.passed:
                report.by_category[cat]["passed"] += 1
        return report

    def run_task(self, task: dict[str, Any]) -> TaskResult:
        """Run a single benchmark task via raw Ollama and validation.

        Args:
            task: Parsed task dict from :func:`load_task`.

        Returns:
            A :class:`TaskResult` indicating pass/fail and duration.
        """
        start = time.monotonic()
        task_id = str(task["id"])
        category = str(task["category"])
        repo_path = self.repos_dir / str(task["repo"])

        if not repo_path.exists():
            return TaskResult(
                task_id=task_id,
                category=category,
                passed=False,
                duration_s=time.monotonic() - start,
                error=f"Fixture repo not found: {repo_path}",
            )

        try:
            response = self._call_ollama(str(task["description"]))
            passed = self._evaluate(response, task, repo_path)
            return TaskResult(
                task_id=task_id,
                category=category,
                passed=passed,
                duration_s=time.monotonic() - start,
                error=None if passed else "pass_condition not met",
            )
        except Exception as exc:  # noqa: BLE001
            return TaskResult(
                task_id=task_id,
                category=category,
                passed=False,
                duration_s=time.monotonic() - start,
                error=str(exc),
            )

    def _call_ollama(self, task_description: str) -> str:
        """Post a generation request directly to the Ollama HTTP API.

        Args:
            task_description: Natural-language task description.

        Returns:
            Raw model response text.
        """
        payload = {
            "model": _DEFAULT_MODEL,
            "prompt": (
                f"Task: {task_description}\n\n"
                "Output ONLY a unified diff in git diff format. No explanation."
            ),
            "stream": False,
        }
        response = httpx.post(_OLLAMA_URL, json=payload, timeout=120.0)
        response.raise_for_status()
        data = response.json()
        return str(data.get("response", ""))

    def _evaluate(self, response: str, task: dict[str, Any], repo_path: Path) -> bool:
        """Apply *response* to a temp copy and run the pass_condition command.

        Args:
            response: Raw model output (expected to contain a unified diff).
            task: Parsed task dict.
            repo_path: Path to the fixture repository.

        Returns:
            ``True`` if the pass_condition command exits with code 0.
        """
        from local_sage.agent.parser import ModelOutputParser
        from local_sage.validation.patcher import Patcher

        patch = ModelOutputParser().extract_diff(response) or response
        patcher = Patcher()
        temp_dir = patcher.apply_to_temp(repo_path, patch)
        try:
            self._run_validators(temp_dir)
            return self._run_pass_condition(temp_dir, str(task["pass_condition"]))
        finally:
            patcher.revert(temp_dir)

    def _run_validators(self, repo_dir: Path) -> None:
        """Run pytest, mypy, and ruff against *repo_dir*.

        Args:
            repo_dir: Patched copy of the fixture repository.
        """
        for cmd in (
            ["pytest", "--tb=short", "-q"],
            ["mypy", "."],
            ["ruff", "check", "."],
        ):
            subprocess.run(cmd, cwd=repo_dir, check=False, capture_output=True)

    def _run_pass_condition(self, repo_dir: Path, pass_condition: str) -> bool:
        """Execute the task's pass_condition shell command.

        Args:
            repo_dir: Directory to run the command in.
            pass_condition: Shell command string from the task YAML.

        Returns:
            ``True`` if the command exits with code 0.
        """
        result = subprocess.run(
            pass_condition,
            cwd=repo_dir,
            shell=True,
            capture_output=True,
        )
        return result.returncode == 0


def main() -> None:
    """CLI entry point for the baseline benchmark runner."""
    parser = argparse.ArgumentParser(description="local-sage baseline benchmark runner")
    parser.add_argument(
        "--tasks-dir",
        type=Path,
        default=_DEFAULT_TASKS_DIR,
        help="Directory containing task YAML files",
    )
    parser.add_argument(
        "--repos-dir",
        type=Path,
        default=_DEFAULT_REPOS_DIR,
        help="Directory containing fixture repositories",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    report = BenchmarkRunner(args.tasks_dir, args.repos_dir).run_all()
    print_report(report)


if __name__ == "__main__":
    main()

"""Benchmark runner for local-sage evaluation suite.

Runs all task YAML files in ``evals/tasks/`` against their fixture repositories,
measures pass rate per category, and prints a summary report.

Usage::

    python evals/runner.py
    python evals/runner.py --tasks-dir evals/tasks --repos-dir evals/repos/fixtures

Categories:
    contract_violation  — tasks that require fixing contract violations
    edge_case           — tasks that require handling edge cases
    multi_file          — tasks that require changes across multiple files
    context_drift       — tasks that require understanding broader context
"""

from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_TASKS_DIR = Path(__file__).parent / "tasks"
_DEFAULT_REPOS_DIR = Path(__file__).parent / "repos" / "fixtures"

CATEGORIES = ["contract_violation", "edge_case", "multi_file", "context_drift"]


@dataclass
class TaskResult:
    """Result of running a single benchmark task.

    Attributes:
        task_id: Unique identifier for the task.
        category: Task category (e.g. ``"contract_violation"``).
        passed: Whether the task passed its pass_condition.
        duration_s: Wall-clock time in seconds.
        error: Error message if the task failed to run, or ``None``.
    """

    task_id: str
    category: str
    passed: bool
    duration_s: float
    error: str | None = None


@dataclass
class BenchmarkReport:
    """Aggregated benchmark results across all tasks.

    Attributes:
        results: List of individual task results.
        total: Total number of tasks run.
        passed: Number of tasks that passed.
        by_category: Pass counts keyed by category name.
    """

    results: list[TaskResult] = field(default_factory=list)
    total: int = 0
    passed: int = 0
    by_category: dict[str, dict[str, int]] = field(default_factory=dict)

    def pass_rate(self) -> float:
        """Return the overall pass rate as a float between 0.0 and 1.0."""
        if self.total == 0:
            return 0.0
        return self.passed / self.total

    def category_pass_rate(self, category: str) -> float:
        """Return the pass rate for a specific category.

        Args:
            category: Category name to compute pass rate for.

        Returns:
            Pass rate as a float between 0.0 and 1.0, or 0.0 if no tasks.
        """
        stats = self.by_category.get(category, {})
        total = stats.get("total", 0)
        if total == 0:
            return 0.0
        return stats.get("passed", 0) / total


def load_task(yaml_path: Path) -> dict[str, Any]:
    """Load a task YAML file and return its contents as a dict.

    Args:
        yaml_path: Path to the task YAML file.

    Returns:
        Parsed task dict with keys: id, category, description, repo,
        expected_files_changed, pass_condition.

    Raises:
        ValueError: If required fields are missing.
    """
    with yaml_path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    for required in ("id", "category", "description", "repo", "pass_condition"):
        if required not in data:
            raise ValueError(f"Task {yaml_path} missing required field: {required}")
    return data


def run_task(task: dict[str, Any], repos_dir: Path) -> TaskResult:
    """Run a single benchmark task and return its result.

    This is a stub implementation. In a full benchmark run, this would:
    1. Copy the fixture repo to a temp directory.
    2. Run the agent loop with the task description.
    3. Evaluate the pass_condition against the output.

    Args:
        task: Parsed task dict from load_task().
        repos_dir: Directory containing fixture repositories.

    Returns:
        A TaskResult indicating pass/fail and duration.
    """
    start = time.monotonic()
    task_id = task["id"]
    category = task["category"]

    repo_path = repos_dir / task["repo"]
    if not repo_path.exists():
        return TaskResult(
            task_id=task_id,
            category=category,
            passed=False,
            duration_s=time.monotonic() - start,
            error=f"Fixture repo not found: {repo_path}",
        )

    # Stub: in a real run, invoke the agent and evaluate pass_condition.
    # For now, mark as skipped (not passed) with a note.
    logger.info("Task %s: stub run (requires Ollama + full agent)", task_id)
    return TaskResult(
        task_id=task_id,
        category=category,
        passed=False,
        duration_s=time.monotonic() - start,
        error="stub: requires live Ollama server for full benchmark run",
    )


def run_all(tasks_dir: Path, repos_dir: Path) -> BenchmarkReport:
    """Run all tasks in tasks_dir and return an aggregated report.

    Args:
        tasks_dir: Directory containing task YAML files.
        repos_dir: Directory containing fixture repositories.

    Returns:
        A BenchmarkReport with per-task and per-category results.
    """
    report = BenchmarkReport()
    report.by_category = {cat: {"total": 0, "passed": 0} for cat in CATEGORIES}

    yaml_files = sorted(tasks_dir.glob("*.yaml"))
    if not yaml_files:
        logger.warning("No task YAML files found in %s", tasks_dir)
        return report

    for yaml_path in yaml_files:
        try:
            task = load_task(yaml_path)
        except (ValueError, Exception) as exc:  # noqa: BLE001
            logger.error("Failed to load task %s: %s", yaml_path, exc)
            continue

        result = run_task(task, repos_dir)
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


def print_report(report: BenchmarkReport) -> None:
    """Print a human-readable benchmark report to stdout.

    Args:
        report: The BenchmarkReport to display.
    """
    print("\n" + "=" * 60)
    print("local-sage Benchmark Report")
    print("=" * 60)
    print(f"Overall: {report.passed}/{report.total} passed ({report.pass_rate():.1%})")
    print()
    print("By category:")
    for cat in CATEGORIES:
        stats = report.by_category.get(cat, {"total": 0, "passed": 0})
        rate = report.category_pass_rate(cat)
        print(f"  {cat:<22} {stats['passed']}/{stats['total']} ({rate:.1%})")
    print()
    print("Individual results:")
    for r in report.results:
        status = "PASS" if r.passed else "FAIL"
        err = f" — {r.error}" if r.error else ""
        print(f"  [{status}] {r.task_id} ({r.duration_s:.2f}s){err}")
    print("=" * 60)
    target = 0.60
    if report.pass_rate() >= target:
        print(f"[OK] Target pass rate ({target:.0%}) achieved!")
    else:
        print(f"[X] Below target pass rate ({target:.0%}). Current: {report.pass_rate():.1%}")
    print()


def main() -> None:
    """Entry point for the benchmark runner CLI."""
    parser = argparse.ArgumentParser(description="local-sage benchmark runner")
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
    report = run_all(args.tasks_dir, args.repos_dir)
    print_report(report)


if __name__ == "__main__":
    main()

"""Simulate `sage` flows (task and harness plan) with a mocked model+validator.

This script patches `local_sage.model.client.OllamaClient` and
`local_sage.model.client.GroqClient` generate methods to return canned
responses, and patches `ValidationRunner` to always pass. It then runs
one `task` and one `plan` (harness) flow and prints the resulting state.

This is safe to run offline and does NOT call external APIs or reveal
any API keys; it only uses the repo code paths with mocked outputs.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from pathlib import Path

# Import target classes
import local_sage.model.client as client_mod
from local_sage.model.client import ModelResponse, OllamaClient, GroqClient
from local_sage.orchestration.graph import build_graph
from local_sage.orchestration.state import AgentState
from local_sage.validation.result import ValidationResult, ValidationFailure, PytestCounts
from local_sage.validation.runner import ValidationRunner
from local_sage.agent.harness import HarnessPlanner, HarnessExecutor

# ---------------------------------------------------------------------------
# Mocks
# ---------------------------------------------------------------------------

class MockClient:
    async def generate(self, prompt: str, system: str = "") -> ModelResponse:
        # Planner prompt: return numbered steps
        if "Produce a step-by-step implementation plan" in prompt or "Produce a step-by-step" in system:
            text = "1. Add a new helper function to utils.py\n2. Update README.md with usage example"
            return ModelResponse(text=text, tokens_used=10, prompt_tokens=5, finish_reason="stop", duration_ms=10)

        # HarnessPlanner system uses JSON schema — return JSON
        if "Decompose the following goal into a sequence of atomic tasks" in system:
            tasks = {
                "tasks": [
                    {
                        "id": "task_1",
                        "description": "Add helper function to utils.py that returns 42",
                        "target_file": "utils.py",
                        "target_symbol": "get_magic_number",
                        "depends_on": [],
                    }
                ]
            }
            return ModelResponse(text=json.dumps(tasks), tokens_used=20, prompt_tokens=10, finish_reason="stop", duration_ms=20)

        # Code generation prompt: return a small unified diff
        if "Output ONLY a unified diff" in prompt or "Output ONLY a unified diff" in system:
            diff = (
                "--- a/utils.py\n"
                "+++ b/utils.py\n"
                "@@ -0,0 +1,8 @@\n"
                "+def get_magic_number():\n"
                "+    \"\"\"Return a deterministic magic number for tests.\"\"\"\n"
                "+    return 42\n"
            )
            return ModelResponse(text=diff, tokens_used=30, prompt_tokens=15, finish_reason="stop", duration_ms=50)

        # Default fallback: short text
        return ModelResponse(text="(mock) no-op response", tokens_used=0, prompt_tokens=0, finish_reason="stop", duration_ms=1)

# Patch both client constructors to use MockClient.generate
async def _mock_generate_async(prompt: str, system: str = ""):
    return await MockClient().generate(prompt, system)

# Replace generate implementations on OllamaClient and GroqClient
OllamaClient.generate = lambda self, prompt, system="": _mock_generate_async(prompt, system)
GroqClient.generate = lambda self, prompt, system="": _mock_generate_async(prompt, system)

# Also patch the helper get_client_sync to return a MockClient instance
client_mod.get_client_sync = lambda: MockClient()

# Patch ValidationRunner to always return a passing ValidationResult
_orig_validate_only = ValidationRunner.validate_only
_orig_validate_and_apply = ValidationRunner.validate_and_apply

def _mock_validation_result_pass(self, patch: str) -> ValidationResult:
    return ValidationResult(
        passed=True,
        failures=[],
        pytest_counts=PytestCounts(passed=1, failed=0, errors=0),
        mypy_errors=None,
        ruff_violations=None,
        contract_failures=None,
        duration_ms=0,
    )

ValidationRunner.validate_only = _mock_validation_result_pass
ValidationRunner.validate_and_apply = _mock_validation_result_pass
ValidationRunner.validate_search_replace = _mock_validation_result_pass

# ---------------------------------------------------------------------------
# Simulation runs
# ---------------------------------------------------------------------------

def run_task_simulation(task_desc: str):
    print("\n--- TASK simulation ---")
    # Ensure a session exists for recording
    from local_sage.memory.session import SessionManager
    repo_root = Path.cwd()
    db_path = repo_root / ".sage" / "memory.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    sm = SessionManager(db_path)
    try:
        session_id = sm.create_session(repo_root)
    except Exception:
        session = sm.load_latest_session(repo_root)
        session_id = session.session_id if session else "sim-session"
    
    graph = build_graph()
    initial = AgentState(task=task_desc, max_retries=1, session_id="sim-session")
    final = graph.invoke(initial)

    # Extract key outputs
    plan = getattr(final, "plan", None) if not isinstance(final, dict) else final.get("plan")
    patch = getattr(final, "patch", None) if not isinstance(final, dict) else final.get("patch")
    validation = getattr(final, "validation_result", None) if not isinstance(final, dict) else final.get("validation_result")

    print("Task:", task_desc)
    print("Plan:", plan)
    print("Patch (excerpt):")
    if patch:
        print(patch)
    else:
        print("(no patch generated)")
    print("Validation passed:", validation.passed if validation else None)


def run_harness_simulation(goal: str):
    print("\n--- HARNESS plan simulation ---")
    planner = HarnessPlanner()
    tasks = planner.plan(goal)
    print("Planner produced tasks:")
    for t in tasks:
        print(" -", t.id, t.description, "->", t.target_file)

    # Execute plan via HarnessExecutor (Validation always passes due to patch)
    executor = HarnessExecutor()
    repo_root = Path.cwd()
    # config: minimal object with sage_dir and max_retries used by HarnessExecutor
    class C: pass
    c = C()
    c.sage_dir = ".sage"
    c.max_retries = 1

    # Ensure session exists
    from local_sage.memory.session import SessionManager
    db_path = repo_root / ".sage" / "memory.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    sm = SessionManager(db_path)
    try:
        session = sm.load_latest_session(repo_root)
        session_id = session.session_id if session else sm.create_session(repo_root)
    except Exception:
        session_id = "sim-session"

    res = executor.execute_plan(session_id, tasks, repo_root, c)
    print("Harness execution result: passed=", res.passed)


if __name__ == "__main__":
    # Run a task-style simulation
    run_task_simulation("Refactor: add helper to return magic number")

    # Run a harness plan simulation
    run_harness_simulation("Create a helper function and document it in README")

    print("\nSimulation complete.")

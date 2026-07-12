"""Full dry-run verification script for local-sage sprint."""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

# Always resolve relative to the script's own location (project root)
ROOT = Path(__file__).parent

print("=" * 60)
print("local-sage Sprint Verification")
print("=" * 60)

# ---------------------------------------------------------------------------
# 1. ModelOutputParser
# ---------------------------------------------------------------------------
print("\n[1] ModelOutputParser")
from local_sage.agent.parser import ModelOutputParser
p = ModelOutputParser()

raw = "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-x\n+y\n"
print("  Raw diff idempotent:", p.extract_diff(raw) == raw)

fenced = "Here is the fix:\n```diff\n--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-x\n+y\n```\n"
r = p.extract_diff(fenced)
print("  Fenced diff extracted:", r is not None and "---" in r and "```" not in r)

prose = "Sure, apply this:\n--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-x\n+y\n"
r = p.extract_diff(prose)
print("  Prose scan extracted:", r is not None and r.startswith("---"))

print("  Pure prose returns None:", p.extract_diff("Great idea!") is None)
print("  Empty string returns None:", p.extract_diff("") is None)

# ---------------------------------------------------------------------------
# 2. CODE_GENERATOR_SYSTEM_PROMPT
# ---------------------------------------------------------------------------
print("\n[2] CODE_GENERATOR_SYSTEM_PROMPT")
from local_sage.orchestration.nodes import CODE_GENERATOR_SYSTEM_PROMPT
print("  Constant is a string:", isinstance(CODE_GENERATOR_SYSTEM_PROMPT, str))
print("  Says 'No explanation':", "No explanation" in CODE_GENERATOR_SYSTEM_PROMPT)
print("  Says 'No markdown':", "No markdown" in CODE_GENERATOR_SYSTEM_PROMPT)
print("  Mentions ---:", "---" in CODE_GENERATOR_SYSTEM_PROMPT)
print("  Mentions +++:", "+++" in CODE_GENERATOR_SYSTEM_PROMPT)

# ---------------------------------------------------------------------------
# 3. PreValidator fast-fail
# ---------------------------------------------------------------------------
print("\n[3] PreValidator fast-fail")
from local_sage.validation.runner import ValidationRunner
tmp = Path(tempfile.mkdtemp())
runner = ValidationRunner(repo_root=tmp)

r1 = runner.validate_only("")
print("  Empty patch -> pre_check:", r1.failures[0].tool == "pre_check", "|", r1.failures[0].message)

r2 = runner.validate_only("   \n   ")
print("  Whitespace -> pre_check:", r2.failures[0].tool == "pre_check", "|", r2.failures[0].message)

r3 = runner.validate_only("Here is my explanation. No diff here.")
print("  Prose -> pre_check:", r3.failures[0].tool == "pre_check", "|", r3.failures[0].message)
shutil.rmtree(tmp)

# ---------------------------------------------------------------------------
# 4. PatchError
# ---------------------------------------------------------------------------
print("\n[4] PatchError on non-diff input")
from local_sage.validation.patcher import Patcher
from local_sage.validation.exceptions import PatchError
tmp = Path(tempfile.mkdtemp())
try:
    Patcher()._apply_patch(tmp, "This is just prose, not a unified diff.")
except PatchError as e:
    print("  PatchError raised:", True)
    print("  Has 'No valid diff hunks':", "No valid diff hunks found in patch" in e.message)
    print("  Has 'explanation text':", "explanation text" in e.message)
    print("  patch_preview <= 200 chars:", len(e.patch_preview) <= 200)
shutil.rmtree(tmp)

# ---------------------------------------------------------------------------
# 5. ContractChecker missing file
# ---------------------------------------------------------------------------
print("\n[5] ContractChecker missing source file")
from local_sage.validation.contracts import Contract, ContractChecker
tmp = Path(tempfile.mkdtemp())
checker = ContractChecker()
contract = Contract(
    symbol_id="nonexistent.py::my_func",
    exception_types=["ValueError"],
    return_shape={"type": "str"},
    source_file=Path("nonexistent.py"),
    function_name="my_func",
)
r1 = checker._check_exception_types(contract, tmp)
r2 = checker._check_return_shape(contract, tmp)
print("  exception_types -> source_file_not_found:", len(r1) == 1 and r1[0].constraint == "source_file_not_found")
print("  return_shape -> source_file_not_found:", len(r2) == 1 and r2[0].constraint == "source_file_not_found")
print("  No silent empty list (exception):", r1 != [])
print("  No silent empty list (return):", r2 != [])
shutil.rmtree(tmp)

# ---------------------------------------------------------------------------
# 6. ValidationResult retry prompt diff note
# ---------------------------------------------------------------------------
print("\n[6] Retry prompt diff-format note")
from local_sage.validation.result import (
    ValidationResult, ValidationFailure, RuffViolation, PytestCounts
)
result = ValidationResult(
    passed=False,
    failures=[ValidationFailure(tool="ruff", message="1 violation(s)")],
    pytest_counts=PytestCounts(passed=5, failed=0, errors=0),
    mypy_errors=[],
    ruff_violations=[RuffViolation(Path("."), 0, 0, "FORMAT", "not formatted")],
    contract_failures=[],
    duration_ms=50,
)
prompt = result.to_retry_prompt()
print("  Contains 'unified diff':", "unified diff" in prompt)
print("  Contains '--- a/file':", "--- a/file" in prompt)
print("  Contains '+++ b/file':", "+++ b/file" in prompt)
print("  Contains '@@ ... @@ hunks':", "@@ ... @@ hunks" in prompt)

result2 = ValidationResult(
    passed=False,
    failures=[ValidationFailure(tool="pytest", message="1 failed")],
    pytest_counts=PytestCounts(passed=0, failed=1, errors=0),
    mypy_errors=[], ruff_violations=[], contract_failures=[], duration_ms=100,
)
print("  Pytest failure has no note:", "unified diff" not in result2.to_retry_prompt())

# ---------------------------------------------------------------------------
# 7. SessionManager token/cost tracking
# ---------------------------------------------------------------------------
print("\n[7] SessionManager token/cost tracking")
from local_sage.memory.session import SessionManager, COST_PER_TOKEN
tmp = Path(tempfile.mkdtemp())
sm = SessionManager(tmp / "memory.db")
sid = sm.create_session(tmp)
fake_result = SimpleNamespace(passed=True, failures=[])
patch_str = "--- a/foo.py\n+++ b/foo.py\n@@ -1 +1 @@\n-x\n+y\n"

s = sm.get_session_summary(sid)
print("  task_count 0 initially:", s.task_count == 0)
print("  actual_cost_usd always 0.0:", s.actual_cost_usd == 0.0)

for i in range(3):
    sm.record_task(sid, f"task {i}", patch_str, fake_result, prompt_tokens=100, completion_tokens=200)

s = sm.get_session_summary(sid)
print("  task_count == 3:", s.task_count == 3)
print("  prompt_tokens == 300:", s.prompt_tokens == 300)
print("  completion_tokens == 600:", s.completion_tokens == 600)
expected = 900 * COST_PER_TOKEN
print(f"  estimated_cost_usd correct ({expected:.6f}):", abs(s.estimated_cost_usd - expected) < 1e-9)
print("  actual_cost_usd still 0.0:", s.actual_cost_usd == 0.0)
shutil.rmtree(tmp)

# ---------------------------------------------------------------------------
# 8. Benchmark infrastructure
# ---------------------------------------------------------------------------
print("\n[8] Benchmark infrastructure")
tasks = list((ROOT / "evals/tasks").glob("*.yaml"))
print(f"  Total task YAML files: {len(tasks)} (expected 20)")
cats: dict[str, int] = {}
for t in tasks:
    cat = "_".join(t.stem.split("_")[:-1])
    cats[cat] = cats.get(cat, 0) + 1
for cat, count in sorted(cats.items()):
    print(f"  {cat}: {count} tasks (expected 5)")

for repo in ["simple_api", "data_processor"]:
    base = ROOT / f"evals/repos/fixtures/{repo}"
    ok = all([
        (base / "pyproject.toml").exists(),
        (base / "tests" / "test_before.py").exists(),
        (base / "tests" / "test_after.py").exists(),
        (base / "contracts").is_dir(),
    ])
    print(f"  {repo} fixture complete:", ok)

# ---------------------------------------------------------------------------
# 9. README and docs
# ---------------------------------------------------------------------------
print("\n[9] README and docs")
readme = (ROOT / "README.md").read_text()
sections = ["Problem", "How It Works", "Quick Start", "Benchmark Results", "Research Contributions", "Acknowledgements"]
all_present = all(f"## {s}" in readme for s in sections)
print("  All 6 README sections present:", all_present)
for s in sections:
    marker = "✓" if f"## {s}" in readme else "✗"
    print(f"    {marker} {s}")

print("  TBD table present:", "TBD" in readme)
print("  demo_script.md exists:", (ROOT / "docs/demo_script.md").exists())

print("\n" + "=" * 60)
print("Verification complete.")
print("=" * 60)

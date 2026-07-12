import asyncio
from pathlib import Path
from local_sage.config import load_config
from local_sage.memory.session import SessionManager
from local_sage.agent.harness import HarnessExecutor, AtomicTask

config = load_config()
config.ollama_model = "qwen3.5:9b"
repo_root = Path.cwd()
sm = SessionManager(repo_root / config.sage_dir / "memory.db")
session_id = sm.create_session(repo_root)

# Create 3 dummy files
dummy1 = Path("dummy_multi_1.py")
dummy1.write_text("\"\"\"Dummy module 1.\"\"\"\n\n\ndef func1() -> str:\n    \"\"\"Return A.\"\"\"\n    return \"A\"\n", encoding="utf-8")
dummy2 = Path("dummy_multi_2.py")
dummy2.write_text("\"\"\"Dummy module 2.\"\"\"\n\n\ndef func2() -> str:\n    \"\"\"Return B.\"\"\"\n    return \"B\"\n", encoding="utf-8")
dummy3 = Path("dummy_multi_3.py")
dummy3.write_text("\"\"\"Dummy module 3.\"\"\"\n\n\ndef func3() -> str:\n    \"\"\"Return hello.\"\"\"\n    return \"hello\"\n\n\ndef func4() -> str:\n    \"\"\"Return hello.\"\"\"\n    return \"hello\"\n", encoding="utf-8")

tasks = [
    AtomicTask(
        id="task_1",
        description="Modify dummy_multi_1.py so func1 returns \"C\"",
        target_file="dummy_multi_1.py",
        target_symbol=None,
        depends_on=[]
    ),
    AtomicTask(
        id="task_2",
        description="Modify dummy_multi_2.py so func2 returns \"D\"",
        target_file="dummy_multi_2.py",
        target_symbol=None,
        depends_on=[]
    ),
    AtomicTask(
        id="task_3",
        description="Modify dummy_multi_3.py so func4 returns \"world\"",
        target_file="dummy_multi_3.py",
        target_symbol=None,
        depends_on=[]
    )
]

executor = HarnessExecutor()
result = executor.execute_plan(session_id, tasks, repo_root, config)

print("\n--- HARNESS RESULT ---")
print(f"Passed all: {result.passed}")
print(f"Consistency failures: {result.consistency_failures}")

print("\n--- FINAL FILE STATES ---")
print("dummy_multi_1.py:", repr(dummy1.read_text(encoding="utf-8")))
print("dummy_multi_2.py:", repr(dummy2.read_text(encoding="utf-8")))
print("dummy_multi_3.py:", repr(dummy3.read_text(encoding="utf-8")))

dummy1.unlink()
dummy2.unlink()
dummy3.unlink()

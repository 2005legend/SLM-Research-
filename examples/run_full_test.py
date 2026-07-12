import sys
from pathlib import Path
from local_sage.orchestration.graph import build_graph
from local_sage.orchestration.state import AgentState
from local_sage.memory.session import SessionManager
from local_sage.config import load_config

# 1. Create a dummy file to edit
dummy_file = Path("dummy_test_file.py")
dummy_file.write_text("def hello():\n    return 'world'\n", encoding="utf-8")

# 2. Set up local-sage
config = load_config()
repo_root = Path.cwd()
db_path = repo_root / config.sage_dir / 'memory.db'
sm = SessionManager(db_path)
session = sm.load_latest_session(repo_root)
session_id = session.session_id if session else sm.create_session(repo_root)

# 3. Run the task
graph = build_graph()
task = "Modify dummy_test_file.py so that hello() returns 'local sage is awesome'."
print(f"Running task: {task}")
state = AgentState(
    task=task,
    max_retries=3,
    session_id=session_id,
)
result = graph.invoke(state)

# 4. Print results
print("\n--- TEST FINISHED ---")
vr = getattr(result, 'validation_result', None)
print("Validation Passed:", vr.passed if vr else False)

patch = getattr(result, 'patch', '')
if patch:
    print("\nCosmetic Patch Generated:")
    print(patch)

print("\nActual dummy_test_file.py content:")
print(dummy_file.read_text(encoding="utf-8"))

# 5. Clean up
dummy_file.unlink()

from pathlib import Path
from local_sage.config import load_config
from local_sage.memory.session import SessionManager
from local_sage.orchestration.graph import build_graph
from local_sage.orchestration.state import AgentState

config = load_config()
repo_root = Path.cwd()

# Ensure session exists
sm = SessionManager(repo_root / config.sage_dir / "memory.db")
session = sm.load_latest_session(repo_root)
if not session:
    session_id = sm.create_session(repo_root)
else:
    session_id = session.session_id

print('Starting sample agent task (short run). This may contact Ollama...')

graph = build_graph()
state = AgentState(task="Test: generate a small non-invasive refactor comment",
                   max_retries=1,
                   session_id=session_id)

# Invoke the graph (may run the full loop; ValidationRunner prevents harmful applies)
result = graph.invoke(state)
print('\n--- AGENT INVOCATION RESULT ---')
print(result)

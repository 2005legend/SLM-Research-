from pathlib import Path
from local_sage.config import load_config
from local_sage.memory.session import SessionManager
from local_sage.orchestration.graph import build_graph
from local_sage.orchestration.state import AgentState

# Safe, non-invasive task for dry run
TASK = "Add a one-line comment at the top of README.md: '# Checked by local-sage (dry-run)'."

config = load_config()
repo_root = Path.cwd()

# Ensure session exists
sm = SessionManager(repo_root / config.sage_dir / "memory.db")
session = sm.load_latest_session(repo_root)
if not session:
    session_id = sm.create_session(repo_root)
else:
    session_id = session.session_id

print('Running dry agent task:')
print(TASK)

# Build and invoke graph
graph = build_graph()
state = AgentState(task=TASK, max_retries=0, session_id=session_id)

result = graph.invoke(state)

print('\n--- DRY RUN RESULT ---')
print('Patch generated (first 1000 chars):')
print((result.patch or '')[:1000])
print('\nValidation passed:', getattr(result, 'validation_result', None).passed if getattr(result, 'validation_result', None) else None)

# If validation failed, show summary
vr = getattr(result, 'validation_result', None)
if vr and not vr.passed:
    print('\nValidation failures:')
    print(vr.to_retry_prompt())

print('\nFull AgentState:')
print(result)

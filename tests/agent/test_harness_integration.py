import pytest
from pathlib import Path
from local_sage.agent.harness import HarnessExecutor, AtomicTask, HarnessResult
from local_sage.config import load_config
from local_sage.memory.session import SessionManager
from unittest.mock import patch

def test_harness_integration(tmp_path: Path):
    config = load_config()
    db_path = tmp_path / config.sage_dir / "memory.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    sm = SessionManager(db_path)
    session_id = sm.create_session(tmp_path)

    tasks = [
        AtomicTask(id="1", description="Change foo", target_file="foo.py", target_symbol=None, depends_on=[]),
        AtomicTask(id="2", description="Change bar", target_file="bar.py", target_symbol=None, depends_on=["1"]),
    ]

    executor = HarnessExecutor()
    
    with patch("local_sage.orchestration.graph.build_graph") as mock_build_graph:
        mock_graph = mock_build_graph.return_value
        mock_graph.invoke.return_value = {
            "validation_result": type("MockResult", (), {"passed": True})(),
            "patch": "mock patch"
        }
        
        result = executor.execute_plan(session_id, tasks, tmp_path, config)
        
        assert result.passed
        assert mock_graph.invoke.call_count == 2
        
        summaries = sm.get_task_summaries(session_id)
        assert len(summaries) == 2
        assert summaries[0].task_id == "1"
        assert summaries[1].task_id == "2"
        assert "foo.py" in summaries[0].files_changed
        assert "bar.py" in summaries[1].files_changed

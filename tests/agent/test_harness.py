import pytest
from local_sage.agent.harness import HarnessPlanner, AtomicTask, HarnessExecutor, TaskSummary

def test_harness_planner_validation():
    from local_sage.agent.harness import HarnessError
    import networkx as nx
    from pathlib import Path
    planner = HarnessPlanner()
    graph = nx.DiGraph()
    repo_root = Path.cwd()
    tasks_valid = [AtomicTask(id="1", description="desc", target_file="foo.py", target_symbol=None, depends_on=[])]
    planner.validate_plan(tasks_valid, graph, repo_root)  # Should not raise

    tasks_invalid = [AtomicTask(id="1", description="desc", target_file="foo.py, bar.py", target_symbol=None, depends_on=[])]
    _, errors = planner.validate_plan(tasks_invalid, graph, repo_root)
    assert len(errors) > 0

    tasks_empty = [AtomicTask(id="1", description="desc", target_file="", target_symbol=None, depends_on=[])]
    _, errors = planner.validate_plan(tasks_empty, graph, repo_root)
    assert len(errors) > 0

def test_harness_executor_context():
    executor = HarnessExecutor()
    summaries = [
        TaskSummary(task_id="1", files_changed=["foo.py"], symbols_added=[], symbols_modified=[], decisions=[])
    ]
    context = executor._build_task_context(summaries)
    assert "Task 1 modified ['foo.py']" in context

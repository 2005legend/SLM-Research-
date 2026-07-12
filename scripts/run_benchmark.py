import json
import argparse
import shutil
from pathlib import Path
from local_sage.config import load_config
from local_sage.memory.session import SessionManager
from local_sage.agent.harness import HarnessExecutor, AtomicTask

def main():
    parser = argparse.ArgumentParser(description="Run the local-sage benchmark suite.")
    parser.add_argument("--suite", default="evals/tasks/suite_v1.json", help="Path to JSON task suite")
    parser.add_argument("--model", default=None, help="Override ollama model in config")
    args = parser.parse_args()

    suite_path = Path(args.suite)
    if not suite_path.exists():
        print(f"Suite not found: {suite_path}")
        return

    with open(suite_path, "r", encoding="utf-8") as f:
        suite_data = json.load(f)

    config = load_config()
    if args.model:
        config.ollama_model = args.model

    repo_root = Path.cwd()
    sm = SessionManager(repo_root / config.sage_dir / "memory.db")
    session_id = sm.create_session(repo_root)

    print(f"Loading suite: {suite_data.get('description', 'Unknown')}")
    print(f"Target model: {config.ollama_model}")

    tasks = []
    # Setup fixtures
    for t in suite_data.get("tasks", []):
        for target in t.get("target_files", []):
            fixture_src = repo_root / "evals" / "fixtures" / Path(target).name
            fixture_dst = repo_root / target
            if fixture_src.exists():
                shutil.copy(fixture_src, fixture_dst)
        
        tasks.append(
            AtomicTask(
                id=t["task_id"],
                description=t["instruction"],
                target_file=t["target_files"][0] if t.get("target_files") else None,
                target_symbol=None,
                depends_on=[]
            )
        )

    executor = HarnessExecutor()
    result = executor.execute_plan(session_id, tasks, repo_root, config)

    print("\n--- HARNESS RESULT ---")
    print(f"Passed all: {result.passed}")
    print(f"Consistency failures: {result.consistency_failures}")

    # Cleanup fixtures
    for t in suite_data.get("tasks", []):
        for target in t.get("target_files", []):
            fixture_dst = repo_root / target
            if fixture_dst.exists():
                fixture_dst.unlink()

if __name__ == "__main__":
    main()

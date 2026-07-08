"""Harness Engineering Layer for local-sage.

This module provides multi-file AI task decomposition and sequential execution.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AtomicTask:
    id: str
    description: str
    target_file: str
    target_symbol: str | None
    depends_on: list[str]
    status: str = "pending"  # pending, success, failed
    retry_count: int = 0


@dataclass
class TaskSummary:
    task_id: str
    files_changed: list[str]
    symbols_added: list[str]
    symbols_modified: list[str]
    decisions: list[str]


@dataclass
class HarnessResult:
    passed: bool
    consistency_failures: list[Any] = field(default_factory=list)


from local_sage.validation.exceptions import ValidationError

class HarnessError(ValidationError):
    """Raised when a harness plan violates constraints."""
    pass


class HarnessPlanner:
    """Decomposes goals into a sequence of AtomicTasks."""

    def plan(self, goal: str) -> list[AtomicTask]:
        """Generate a plan of single-file tasks for a given goal."""
        from local_sage.model.client import get_client_sync
        import asyncio
        import uuid
        import re

        system_prompt = (
            "You are a task decomposition agent. Break a coding goal into "
            "the minimum number of atomic edits to EXISTING files.\n\n"
            "Rules (enforce strictly):\n"
            "1. Each task targets exactly ONE existing file\n"
            "2. Each task modifies exactly ONE function or class\n"
            "3. Task description is ONE sentence, 15 words max, "
            "stating WHAT changes (not HOW)\n"
            "4. Maximum 5 tasks total\n"
            "5. NEVER create new files\n"
            "6. List tasks in dependency order (tasks that others "
            "depend on come first)\n\n"
            "Output format — JSON array only, no other text:\n"
            "[\n"
            "  {\n"
            '    "id": "task_001",\n'
            '    "description": "Add clear() method to WikiManager class",\n'
            '    "target_file": "local_sage/wiki/manager.py",\n'
            '    "target_symbol": "WikiManager",\n'
            '    "depends_on": [],\n'
            '    "estimated_difficulty": "easy"\n'
            "  }\n"
            "]"
        )

        client = get_client_sync()
        try:
            response = asyncio.run(client.generate(prompt=goal, system=system_prompt))
            json_match = re.search(r'\[.*\]', response.text, re.DOTALL)
            data = json.loads(json_match.group(0)) if json_match else []
            if isinstance(data, dict) and "tasks" in data:
                data = data["tasks"]
        except Exception as exc:
            logger.error("HarnessPlanner failed to generate plan: %s", exc)
            data = []

        tasks = []
        for t_data in data:
            desc = t_data.get("description", "")
            # Forcefully sanitize descriptions to be a single sentence
            # to prevent smaller LLMs from embedding step-by-step instructions.
            desc = desc.split(". ")[0].split("\n")[0].strip()
            if not desc.endswith("."):
                desc += "."
                
            tasks.append(AtomicTask(
                id=t_data.get("id", str(uuid.uuid4())),
                description=desc,
                target_file=t_data.get("target_file", ""),
                target_symbol=t_data.get("target_symbol"),
                depends_on=t_data.get("depends_on", []),
            ))
        return tasks
        
    def validate_plan(
        self,
        tasks: list[AtomicTask],
        graph: Any,
        repo_root: Path
    ) -> tuple[list[AtomicTask], list[str]]:
        """
        Returns (valid_tasks, errors).
        Errors are BLOCKING — plan is rejected if any errors exist.
        
        Hard rejections:
        - target_file does not exist in repo_root
        - target_file path contains directories that don't exist
        - description is longer than 100 characters
        - more than 5 tasks in plan
        - duplicate target_file + target_symbol combinations
        - circular dependencies
        """
        errors = []
        if len(tasks) > 5:
            errors.append("Plan exceeds maximum of 5 tasks.")
            
        seen_targets = set()
        
        for task in tasks:
            if not task.target_file or "," in task.target_file or " " in task.target_file:
                errors.append(f"Task '{task.id}' targets multiple/invalid files: '{task.target_file}'. Each task MUST target exactly one file.")
                continue
                
            file_path = repo_root / task.target_file
            if not file_path.exists():
                errors.append(f"Task '{task.id}' targets '{task.target_file}' which does not exist in the repository. Only existing files may be edited.")
                
            if len(task.description) > 100:
                errors.append(f"Task '{task.id}' description exceeds 100 characters.")
                
            target_key = (task.target_file, task.target_symbol)
            if target_key in seen_targets:
                errors.append(f"Duplicate target file and symbol combination in plan: {target_key}")
            seen_targets.add(target_key)
            
        # Check circular dependencies
        # Simple implementation: check if any depends_on refers to a future task in the list
        task_ids = [t.id for t in tasks]
        for i, task in enumerate(tasks):
            for dep in task.depends_on:
                if dep in task_ids and task_ids.index(dep) >= i:
                    errors.append(f"Task '{task.id}' depends on future or self task '{dep}'.")
                    
        return tasks, errors


class HarnessExecutor:
    """Executes a list of AtomicTasks sequentially."""

    def execute_plan(self, session_id: str, tasks: list[AtomicTask], repo_root: Path, config: Any) -> HarnessResult:
        """Run the provided tasks in dependency order, persisting state."""
        from local_sage.memory.session import SessionManager

        db_path = repo_root / config.sage_dir / "memory.db"
        sm = SessionManager(db_path)
        sm.save_harness_plan(session_id, tasks)

        passed = True
        for task in tasks:
            if not self._execute_single_task(task, session_id, sm, config):
                passed = False
                break

        return HarnessResult(passed=passed)

    def _execute_single_task(self, task: AtomicTask, session_id: str, sm: Any, config: Any) -> bool:
        from local_sage.orchestration.graph import build_graph
        from local_sage.orchestration.state import AgentState
        
        sm.update_task_status(session_id, task.id, "running")
        context = self._build_task_context(sm.get_task_summaries(session_id))
        prompt = f"Goal: {task.description}\nTarget File: {task.target_file}\n"
        if context:
            prompt += f"Context from previous tasks:\n{context}\n"

        initial_state = AgentState(task=prompt, max_retries=config.max_retries, session_id=session_id)
        from typing import Any, cast
        graph = cast(Any, build_graph())
        final_state = graph.invoke(initial_state)

        result = final_state.get("validation_result") if isinstance(final_state, dict) else getattr(final_state, "validation_result", None)

        if result and result.passed:
            sm.update_task_status(session_id, task.id, "success")
            sm.save_task_summary(session_id, TaskSummary(
                task_id=task.id,
                files_changed=[task.target_file],
                symbols_added=[],
                symbols_modified=[task.target_symbol] if task.target_symbol else [],
                decisions=["Task succeeded"]
            ))
            return True
        else:
            sm.update_task_status(session_id, task.id, "failed")
            return False

    def _build_task_context(self, previous_summaries: list[TaskSummary]) -> str:
        lines = [f"Task {s.task_id} modified {s.files_changed}." for s in previous_summaries]
        context = "\n".join(lines)
        return context[-1200:] if len(context) > 1200 else context

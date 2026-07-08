"""Layer 0 â€” CLI: Typer application with all sage subcommands.

All commands are thin wrappers that delegate to the appropriate layer.
Rich is used for all terminal output.
"""

from __future__ import annotations

import asyncio
import warnings
from typing import Any
from pathlib import Path

# Suppress upstream LangGraph / LangChain deprecation warnings at runtime.
warnings.filterwarnings("ignore", category=DeprecationWarning, module="langchain_core.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="langgraph.*")
warnings.filterwarnings("ignore", category=PendingDeprecationWarning, module="langchain_core.*")
warnings.filterwarnings("ignore", category=PendingDeprecationWarning, module="langgraph.*")

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from local_sage.config import load_config

app = typer.Typer(
    name="sage",
    help="local-sage: a repo-aware, validation-gated coding agent.",
    no_args_is_help=True,
)
console = Console()

# Sub-app for wiki subcommands
wiki_app = typer.Typer(help="Manage the agent wiki.")
app.add_typer(wiki_app, name="wiki")

# Sub-app for memory subcommands
memory_app = typer.Typer(help="Inspect session memory.")
app.add_typer(memory_app, name="memory")


# ---------------------------------------------------------------------------
# sage start
# ---------------------------------------------------------------------------


@app.command()
def start() -> None:
    """Boot the agent, index the repo, and enter the interactive task loop."""
    config = load_config()
    repo_root = Path.cwd()
    console.print("[bold green]Starting local-sage...[/bold green]")

    graph, session_id, session_manager = _boot(config, repo_root)

    node_count = len(list(graph._graph.nodes))
    console.print(
        Panel(
            f"[green][OK] Ready[/green]\nIndexed [bold]{node_count}[/bold] symbols\nSession loaded\n\n"
            "[dim]Type a task to run it.  Commands: [bold]status[/bold] Â· "
            "[bold]history[/bold] Â· [bold]quit[/bold][/dim]",
            title="local-sage",
        )
    )
    _repl(config, repo_root, session_id, session_manager)


def _boot(config: object, repo_root: Path) -> tuple[Any, Any, Any]:
    """Index the repo and load/create a session.

    Args:
        config: Loaded SageConfig.
        repo_root: Repository root directory.

    Returns:
        Tuple of (SymbolGraph, session_id, SessionManager).
    """
    from local_sage.memory.session import SessionManager
    from local_sage.repo_graph.indexer import RepoIndexer
    from local_sage.config import SageConfig

    assert isinstance(config, SageConfig)
    indexer = RepoIndexer()
    cache_path = repo_root / config.sage_dir / "index.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with console.status("Indexing repository..."):
        graph = indexer.load_index(cache_path)
        if graph is None:
            graph = indexer.index_repo(repo_root)
            indexer.save_index(graph, cache_path)

    db_path = repo_root / config.sage_dir / "memory.db"
    sm = SessionManager(db_path)
    session = sm.load_latest_session(repo_root)
    if session is None:
        session_id = sm.create_session(repo_root)
        console.print(f"[dim]New session created: {session_id}[/dim]")
    else:
        session_id = session.session_id
        console.print(f"[dim]Resumed session: {session_id}[/dim]")
    return graph, session_id, sm


def _repl(
    config: object,
    repo_root: Path,
    session_id: str,
    session_manager: object,
) -> None:
    """Run the interactive task REPL loop.

    Args:
        config: Loaded SageConfig.
        repo_root: Repository root directory.
        session_id: Active session ID.
        session_manager: Initialised SessionManager.
    """
    console.rule("[dim]interactive mode[/dim]")
    while True:
        try:
            user_input = input("sage â€º ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            break
        if not user_input:
            continue
        if _handle_repl_command(user_input, config, repo_root, session_id, session_manager):
            break


def _handle_repl_command(
    user_input: str,
    config: object,
    repo_root: Path,
    session_id: str,
    session_manager: object,
) -> bool:
    """Dispatch one line of REPL input. Returns True if the loop should exit.

    Args:
        user_input: Raw text typed by the user.
        config: Loaded SageConfig.
        repo_root: Repository root directory.
        session_id: Active session ID.
        session_manager: Initialised SessionManager.

    Returns:
        True if the user wants to quit, False to continue.
    """
    cmd = user_input.lower()
    if cmd in ("quit", "exit", "q"):
        console.print("[dim]Goodbye.[/dim]")
        return True
    if cmd == "status":
        _print_repl_status(session_manager, session_id, repo_root, config)
    elif cmd == "history":
        _print_repl_history(session_manager, session_id)
    elif cmd == "help":
        console.print(
            "[dim]Commands: [bold]status[/bold] Â· [bold]history[/bold] Â· "
            "[bold]quit[/bold]  â€” or just type a task description[/dim]"
        )
    else:
        _run_repl_task(user_input, config, repo_root, session_id)
    return False


def _run_repl_task(description: str, config: object, repo_root: Path, session_id: str) -> None:
    """Run one task inside the REPL and print the result.

    Args:
        description: Natural-language task description from the user.
        config: Loaded SageConfig.
        repo_root: Repository root directory.
        session_id: Active session ID.
    """
    from local_sage.orchestration.graph import build_graph
    from local_sage.orchestration.state import AgentState

    with console.status(f"[cyan]Running:[/cyan] {description}"):
        graph_obj = build_graph()
        initial_state = AgentState(
            task=description,
            max_retries=config.max_retries,  # type: ignore[attr-defined]
            session_id=session_id,
        )
        final_state = graph_obj.invoke(initial_state)  # type: ignore[attr-defined]

    result = (
        final_state.get("validation_result")
        if isinstance(final_state, dict)
        else getattr(final_state, "validation_result", None)
    )
    if result and result.passed:
        console.print("[bold green][OK] Validation passed â€” patch written to disk.[/bold green]")
    else:
        console.print("[bold red]âœ— Validation failed â€” no changes made.[/bold red]")
        if result:
            console.print(result.to_retry_prompt())

    console.rule()


def _print_repl_status(
    session_manager: object,
    session_id: str,
    repo_root: Path,
    config: object,
) -> None:
    """Print a compact session status inside the REPL.

    Args:
        session_manager: Initialised SessionManager.
        session_id: Active session ID.
        repo_root: Repository root directory.
        config: Loaded SageConfig.
    """
    from local_sage.config import SageConfig
    from local_sage.memory.session import SessionManager

    assert isinstance(config, SageConfig)
    assert isinstance(session_manager, SessionManager)
    summary = session_manager.get_session_summary(session_id)
    index_info = _repl_index_info(repo_root, config)
    console.print(
        Panel(
            f"Session  [bold]{session_id[:8]}â€¦[/bold]\n"
            f"Tasks    [bold]{summary.task_count}[/bold]\n"
            f"Tokens   [bold]{summary.prompt_tokens}[/bold] prompt / "
            f"[bold]{summary.completion_tokens}[/bold] completion\n"
            f"Est cost [bold]${summary.estimated_cost_usd:.4f}[/bold]  "
            f"Actual [bold]${summary.actual_cost_usd:.4f}[/bold]\n"
            f"Index    {index_info}",
            title="status",
        )
    )


def _repl_index_info(repo_root: Path, config: object) -> str:
    """Return a human-readable index stats string for the REPL status panel.

    Args:
        repo_root: Repository root directory.
        config: Loaded SageConfig.

    Returns:
        Formatted string with symbol and edge counts.
    """
    import json

    from local_sage.config import SageConfig

    assert isinstance(config, SageConfig)
    cache_path = repo_root / config.sage_dir / "index.json"
    if not cache_path.exists():
        return "[dim]not indexed[/dim]"
    raw = json.loads(cache_path.read_text(encoding="utf-8"))
    return f"{len(raw.get('nodes', []))} symbols, {len(raw.get('edges', []))} edges"


def _print_repl_history(session_manager: object, session_id: str) -> None:
    """Print recent observations recorded for this session.

    Args:
        session_manager: Initialised SessionManager.
        session_id: Active session ID.
    """
    from local_sage.memory.session import SessionManager

    assert isinstance(session_manager, SessionManager)
    summary = session_manager.get_session_summary(session_id)
    if not summary.observations:
        console.print("[dim]No observations recorded yet.[/dim]")
        return
    for i, obs in enumerate(summary.observations[-10:], 1):
        console.print(f"  [dim]{i}.[/dim] {obs}")


# ---------------------------------------------------------------------------
# sage task
# ---------------------------------------------------------------------------


@app.command()
def task(description: str = typer.Argument(..., help="Task description")) -> None:
    """Run a coding task through the full agent loop."""
    config = load_config()
    repo_root = Path.cwd()

    from local_sage.memory.session import SessionManager
    from local_sage.orchestration.graph import build_graph
    from local_sage.orchestration.state import AgentState

    db_path = repo_root / config.sage_dir / "memory.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    session_manager = SessionManager(db_path)
    session = session_manager.load_latest_session(repo_root)
    session_id = session.session_id if session else session_manager.create_session(repo_root)

    with console.status(f"Running task: {description}"):
        graph_obj = build_graph()
        initial_state = AgentState(
            task=description,
            max_retries=config.max_retries,
            session_id=session_id,
        )
        final_state = graph_obj.invoke(initial_state)  # type: ignore[attr-defined]

    result = (
        final_state.get("validation_result")
        if isinstance(final_state, dict)
        else getattr(final_state, "validation_result", None)
    )
    if result and result.passed:
        console.print("[bold green][OK] Task completed and patch applied.[/bold green]")
    else:
        console.print("[bold red]âœ— Task failed â€” no patch applied.[/bold red]")
        if result:
            console.print(result.to_retry_prompt())
# ---------------------------------------------------------------------------
# sage plan
# ---------------------------------------------------------------------------


@app.command()
def plan(
    goal: str,
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
) -> None:
    """Decompose a goal into multi-file atomic tasks and execute them."""
    config = load_config()
    repo_root = Path.cwd()

    from local_sage.memory.session import SessionManager
    from local_sage.agent.harness import HarnessPlanner

    db_path = repo_root / config.sage_dir / "memory.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    session_manager = SessionManager(db_path)
    session = session_manager.load_latest_session(repo_root)
    session_id = session.session_id if session else session_manager.create_session(repo_root)

    planner = HarnessPlanner()
    tasks = _generate_ai_plan(planner, goal)
            
    if not tasks:
        console.print("[yellow]No tasks planned.[/yellow]")
        return
        
    from local_sage.agent.harness import HarnessError
    valid_tasks, errors = planner.validate_plan(tasks, None, repo_root)
    if errors:
        console.print("[bold red]Plan validation failed! Resolving these issues is REQUIRED before execution:[/bold red]")
        for err in errors:
            console.print(f"[red] - {err}[/red]")
        console.print("\n[yellow]Please rephrase your goal to fix these issues.[/yellow]")
        raise typer.Exit(code=1)
        
    tasks = valid_tasks
        
    _execute_plan_interactive(tasks, session_id, repo_root, config, skip_confirm=yes)


def _load_manual_plan(plan_path_str: str) -> list[Any]:
    import json
    import uuid
    from local_sage.agent.harness import AtomicTask
    plan_path = Path(plan_path_str)
    if not plan_path.exists():
        console.print(f"[red]Manual plan not found: {plan_path}[/red]")
        raise typer.Exit(code=1)
    raw_tasks = json.loads(plan_path.read_text(encoding="utf-8"))
    return [
        AtomicTask(
            id=t.get("id", str(uuid.uuid4())),
            description=t.get("description", ""),
            target_file=t.get("target_file", ""),
            target_symbol=t.get("target_symbol"),
            depends_on=t.get("depends_on", []),
        ) for t in raw_tasks.get("tasks", [])
    ]


def _generate_ai_plan(planner: Any, goal: str) -> list[Any]:
    with console.status(f"Decomposing goal: {goal}"):
        return planner.plan(goal)  # type: ignore


def _execute_plan_interactive(tasks: list[Any], session_id: str, repo_root: Path, config: object, skip_confirm: bool = False) -> None:
    from local_sage.agent.harness import HarnessExecutor
    from local_sage.validation.consistency import ConsistencyChecker

    console.print(f"[bold cyan]Generated Plan with {len(tasks)} tasks:[/bold cyan]")
    for i, t in enumerate(tasks, 1):
        console.print(f"  {i}. {t.description} -> {t.target_file}")
        
    # Bypassing prompt for non-interactive execution
    # if not skip_confirm:
    #     user_input = typer.prompt("Execute this plan?", default="Y")
    #     if user_input.lower() not in ("y", "yes"):
    #         console.print("[dim]Aborted by user.[/dim]")
    #         return

    executor = HarnessExecutor()
    with console.status("Executing plan tasks..."):
        result = executor.execute_plan(session_id, tasks, repo_root, config)
        
    checker = ConsistencyChecker()
    modified_files = list(set([str(repo_root / t.target_file) for t in tasks]))
    failures = checker.check(repo_root, files=modified_files)
    
    if result.passed and not failures:
        console.print("[bold green][OK] Harness plan executed successfully![/bold green]")
    else:
        console.print("[bold red]x Harness plan failed or consistency issues found.[/bold red]")
        for f in failures:
            console.print(f"[red]{f.message}[/red]")
# ---------------------------------------------------------------------------
# sage validate
# ---------------------------------------------------------------------------


@app.command()
def validate(
    patch_path: Path = typer.Argument(..., help="Path to the patch file"),  # noqa: B008
) -> None:
    """Validate a patch file without applying it to the repository."""
    config = load_config()
    repo_root = Path.cwd()

    from local_sage.validation.runner import ValidationRunner

    if not patch_path.exists():
        console.print(f"[red]Patch file not found: {patch_path}[/red]")
        raise typer.Exit(code=1)

    patch_text = patch_path.read_text(encoding="utf-8")
    runner = ValidationRunner(
        repo_root=repo_root,
        manual_review=False,
        pytest_timeout=config.pytest_timeout,
        mypy_timeout=config.mypy_timeout,
        ruff_timeout=config.ruff_timeout,
    )

    with console.status("Running validation..."):
        result = runner.validate_only(patch_text)

    if result.passed:
        console.print("[bold green][OK] All checks passed.[/bold green]")
    else:
        console.print("[bold red]âœ— Validation failed.[/bold red]")
        console.print(result.to_retry_prompt())
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# sage benchmark
# ---------------------------------------------------------------------------


@app.command()
def benchmark(
    suite: Path = typer.Option(Path("evals"), "--suite", help="Path to eval suite directory"),  # noqa: B008
) -> None:
    """Run the evaluation benchmark suite."""
    console.print(f"[yellow]Running benchmark suite from: {suite}[/yellow]")
    if not suite.exists():
        console.print(f"[red]Suite directory not found: {suite}[/red]")
        raise typer.Exit(code=1)
    console.print("[dim]Benchmark runner not yet implemented.[/dim]")


# ---------------------------------------------------------------------------
# sage status
# ---------------------------------------------------------------------------


@app.command()
def status() -> None:
    """Show Ollama model status, repo index stats, and session info."""
    config = load_config()
    repo_root = Path.cwd()
    model_status = _get_model_status()
    index_info = _get_index_info(repo_root, config)
    session_info = _get_session_info(repo_root, config)

    from local_sage.model.client import get_client_sync
    
    client = get_client_sync()

    console.print(
        Panel(
            f"[bold]Model[/bold]: {client.MODEL}  {model_status}\n"
            f"[bold]Repo index[/bold]: {index_info}\n"
            f"[bold]Session[/bold]: {session_info}",
            title="local-sage status",
        )
    )


def _get_model_status() -> str:
    """Return a Rich-formatted model online/offline status string."""
    from local_sage.model.client import get_client_sync

    client = get_client_sync()
    online = asyncio.run(client.health_check())
    
    model_name = client.MODEL
    return f"[green][OK] online ({model_name})[/green]" if online else "[red][X] offline[/red]"


def _get_index_info(repo_root: Path, config: object) -> str:
    """Return a formatted string with repo index statistics.

    Args:
        repo_root: Repository root directory.
        config: Loaded SageConfig instance.

    Returns:
        Human-readable index stats string.
    """
    import json

    from local_sage.config import SageConfig

    assert isinstance(config, SageConfig)
    cache_path = repo_root / config.sage_dir / "index.json"
    if not cache_path.exists():
        return "[dim]not indexed â€” run `sage start`[/dim]"
    raw = json.loads(cache_path.read_text(encoding="utf-8"))
    node_count = len(raw.get("nodes", []))
    edge_count = len(raw.get("edges", []))
    return f"{node_count} symbols, {edge_count} edges"


def _get_session_info(repo_root: Path, config: object) -> str:
    """Return a formatted string with current session information.

    Args:
        repo_root: Repository root directory.
        config: Loaded SageConfig instance.

    Returns:
        Human-readable session info string.
    """
    from local_sage.config import SageConfig
    from local_sage.memory.session import SessionManager

    assert isinstance(config, SageConfig)
    db_path = repo_root / config.sage_dir / "memory.db"
    if not db_path.exists():
        return "[dim]no session â€” run `sage start`[/dim]"
    sm = SessionManager(db_path)
    session = sm.load_latest_session(repo_root)
    if not session:
        return "[dim]no session â€” run `sage start`[/dim]"
    summary = sm.get_session_summary(session.session_id)
    return (
        f"ID: {session.session_id[:8]}â€¦ | {summary.task_count} tasks | "
        f"{summary.prompt_tokens} prompt / {summary.completion_tokens} completion tokens | "
        f"est. ${summary.estimated_cost_usd:.4f} | actual ${summary.actual_cost_usd:.4f}"
    )


# ---------------------------------------------------------------------------
# sage memory show
# ---------------------------------------------------------------------------


@memory_app.command("show")
def memory_show() -> None:
    """Display current session memory in a Rich table."""
    config = load_config()
    repo_root = Path.cwd()
    db_path = repo_root / config.sage_dir / "memory.db"

    if not db_path.exists():
        console.print("[yellow]No session database found. Run `sage start` first.[/yellow]")
        raise typer.Exit(code=1)

    from local_sage.memory.session import SessionManager

    sm = SessionManager(db_path)
    session = sm.load_latest_session(repo_root)
    if session is None:
        console.print("[yellow]No sessions found.[/yellow]")
        raise typer.Exit(code=1)

    summary = sm.get_session_summary(session.session_id)
    table = Table(title=f"Session: {session.session_id[:8]}â€¦")
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("Session ID", session.session_id)
    table.add_row("Tasks completed", str(summary.task_count))
    table.add_row("Files patched", str(summary.patch_count))
    table.add_row("Prompt tokens", str(summary.prompt_tokens))
    table.add_row("Completion tokens", str(summary.completion_tokens))
    table.add_row("Estimated cost (USD)", f"{summary.estimated_cost_usd:.6f}")
    table.add_row("Actual cost (USD)", f"{summary.actual_cost_usd:.6f}")
    table.add_row("Last active", str(summary.last_active))
    if summary.observations:
        table.add_row("Observations", "\n".join(summary.observations[:5]))
    console.print(table)


# ---------------------------------------------------------------------------
# sage wiki list
# ---------------------------------------------------------------------------


@wiki_app.command("list")
def wiki_list() -> None:
    """List all wiki entries with titles and last-modified timestamps."""
    config = load_config()
    wiki_dir = Path.cwd() / config.wiki_dir

    from local_sage.wiki.manager import WikiManager

    manager = WikiManager(wiki_dir)
    entries = manager.list_entries()

    if not entries:
        console.print("[yellow]No wiki entries found.[/yellow]")
        return

    table = Table(title="Wiki Entries")
    table.add_column("Title", style="bold")
    table.add_column("Last Modified")
    for entry in entries:
        table.add_row(entry.title, str(entry.last_modified))
    console.print(table)


# ---------------------------------------------------------------------------
# sage wiki show
# ---------------------------------------------------------------------------


@wiki_app.command("show")
def wiki_show(entry: str = typer.Argument(..., help="Wiki entry title")) -> None:
    """Display the full content of a wiki entry."""
    config = load_config()
    wiki_dir = Path.cwd() / config.wiki_dir

    from local_sage.wiki.exceptions import WikiReadError
    from local_sage.wiki.manager import WikiManager

    manager = WikiManager(wiki_dir)
    try:
        wiki_entry = manager.read_entry(entry)
    except WikiReadError as exc:
        console.print(f"[red]Error reading wiki entry '{entry}': {exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(Panel(wiki_entry.content, title=wiki_entry.title))

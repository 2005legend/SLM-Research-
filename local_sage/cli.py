"""Layer 0 — CLI: Typer application with all sage subcommands.

All commands are thin wrappers that delegate to the appropriate layer.
Rich is used for all terminal output.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

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
    """Boot the agent, index the repo, and load the latest session."""
    config = load_config()
    repo_root = Path.cwd()
    console.print("[bold green]Starting local-sage...[/bold green]")

    # Index the repository
    from local_sage.repo_graph.indexer import RepoIndexer

    indexer = RepoIndexer()
    cache_path = repo_root / config.sage_dir / "index.json"
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    with console.status("Indexing repository..."):
        graph = indexer.load_index(cache_path)
        if graph is None:
            graph = indexer.index_repo(repo_root)
            indexer.save_index(graph, cache_path)

    # Load or create session
    from local_sage.memory.session import SessionManager

    db_path = repo_root / config.sage_dir / "memory.db"
    session_manager = SessionManager(db_path)
    session = session_manager.load_latest_session(repo_root)
    if session is None:
        session_id = session_manager.create_session(repo_root)
        console.print(f"[dim]New session created: {session_id}[/dim]")
    else:
        console.print(f"[dim]Resumed session: {session.session_id}[/dim]")

    node_count = len(list(graph._graph.nodes))
    console.print(
        Panel(
            f"[green]✓ Ready[/green]\nIndexed [bold]{node_count}[/bold] symbols\nSession loaded",
            title="local-sage",
        )
    )


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
        console.print("[bold green]✓ Task completed and patch applied.[/bold green]")
    else:
        console.print("[bold red]✗ Task failed — no patch applied.[/bold red]")
        if result:
            console.print(result.to_retry_prompt())


# ---------------------------------------------------------------------------
# sage validate
# ---------------------------------------------------------------------------


@app.command()
def validate(
    patch: Path = typer.Option(..., "--patch", help="Path to the patch file"),  # noqa: B008
) -> None:
    """Validate a patch file without applying it to the repository."""
    config = load_config()
    repo_root = Path.cwd()

    from local_sage.validation.runner import ValidationRunner

    if not patch.exists():
        console.print(f"[red]Patch file not found: {patch}[/red]")
        raise typer.Exit(code=1)

    patch_text = patch.read_text(encoding="utf-8")
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
        console.print("[bold green]✓ All checks passed.[/bold green]")
    else:
        console.print("[bold red]✗ Validation failed.[/bold red]")
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

    from local_sage.model.client import OllamaClient

    console.print(
        Panel(
            f"[bold]Model[/bold]: {OllamaClient.MODEL}  {model_status}\n"
            f"[bold]Repo index[/bold]: {index_info}\n"
            f"[bold]Session[/bold]: {session_info}",
            title="local-sage status",
        )
    )


def _get_model_status() -> str:
    """Return a Rich-formatted model online/offline status string."""
    from local_sage.model.client import OllamaClient

    client = OllamaClient()
    online = asyncio.run(client.health_check())
    return "[green]✓ online[/green]" if online else "[red]✗ offline[/red]"


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
        return "[dim]not indexed — run `sage start`[/dim]"
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
        return "[dim]no session — run `sage start`[/dim]"
    sm = SessionManager(db_path)
    session = sm.load_latest_session(repo_root)
    if not session:
        return "[dim]no session — run `sage start`[/dim]"
    summary = sm.get_session_summary(session.session_id)
    return f"ID: {session.session_id[:8]}… | {summary.task_count} tasks"


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
    table = Table(title=f"Session: {session.session_id[:8]}…")
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("Session ID", session.session_id)
    table.add_row("Tasks completed", str(summary.task_count))
    table.add_row("Files patched", str(summary.patch_count))
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

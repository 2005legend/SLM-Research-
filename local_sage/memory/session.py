"""Session memory persistence for local-sage using stdlib sqlite3.

This module provides:
- ``Session``        — dataclass representing a single agent session.
- ``SessionSummary`` — aggregated summary of a session's activity.
- ``SessionManager`` — SQLite-backed manager for creating and querying sessions.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from local_sage.memory.exceptions import (
    DatabaseCorruptError,
    SessionNotFoundError,
)

if TYPE_CHECKING:
    from local_sage.validation.result import ValidationResult  # noqa: F401
    from local_sage.agent.harness import AtomicTask, TaskSummary

logger = logging.getLogger(__name__)

# Path to the SQL schema file, relative to this module.
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# Estimated cost per token in USD (proxy rate for local models).
COST_PER_TOKEN = 0.000_002


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Session:
    """A single agent session tied to a repository.

    Attributes:
        session_id: Unique UUID4 identifier for this session.
        repo_path: Absolute path to the repository root.
        created_at: UTC timestamp when the session was created.
        updated_at: UTC timestamp of the most recent update.
    """

    session_id: str
    repo_path: Path
    created_at: datetime
    updated_at: datetime


@dataclass
class SessionSummary:
    """Aggregated summary of a session's activity.

    Attributes:
        session_id: Unique UUID4 identifier for the session.
        task_count: Number of test-result rows recorded (one per task attempt).
        patch_count: Number of file-change rows recorded (one per patched file).
        last_active: UTC timestamp of the most recent test result, or the
            session's ``updated_at`` if no test results exist.
        observations: List of decision descriptions recorded for the session.
        prompt_tokens: Total prompt tokens across all recorded tasks.
        completion_tokens: Total completion tokens across all recorded tasks.
        estimated_cost_usd: Estimated cost from token counts and COST_PER_TOKEN.
        actual_cost_usd: Actual cost in USD (always 0.0 for local models).
    """

    session_id: str
    task_count: int
    patch_count: int
    last_active: datetime
    observations: list[str]
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    actual_cost_usd: float


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------


class SessionManager:
    """SQLite-backed manager for local-sage session persistence.

    The database file lives at ``<db_path>``.  Pass a temporary path during
    testing to avoid touching the real ``.sage/memory.db``.

    Attributes:
        db_path: Absolute path to the SQLite database file.
    """

    def __init__(self, db_path: Path) -> None:
        """Initialise the manager and ensure the schema exists.

        Args:
            db_path: Path to the SQLite database file.  The parent directory
                must already exist (``SessionManager`` will not create it).
        """
        self.db_path = db_path
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_session(self, repo_path: Path) -> str:
        """Create a new session for *repo_path* and return its session ID.

        Args:
            repo_path: Absolute path to the repository root.

        Returns:
            A UUID4 string that uniquely identifies the new session.

        Raises:
            DatabaseCorruptError: If the database is corrupt and recovery fails.
        """
        session_id = str(uuid.uuid4())
        now = _utcnow_iso()
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO sessions (id, repo_path, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (session_id, str(repo_path), now, now),
            )
            conn.commit()
        finally:
            conn.close()
        return session_id

    def load_latest_session(self, repo_path: Path) -> Session | None:
        """Return the most recent session for *repo_path*, or ``None``.

        Args:
            repo_path: Absolute path to the repository root.

        Returns:
            The most recently updated ``Session`` for the given repo, or
            ``None`` if no sessions exist for that path.

        Raises:
            DatabaseCorruptError: If the database is corrupt and recovery fails.
        """
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT id, repo_path, created_at, updated_at "
                "FROM sessions WHERE repo_path = ? ORDER BY updated_at DESC LIMIT 1",
                (str(repo_path),),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        return _row_to_session(row)

    def record_task(
        self,
        session_id: str,
        task: str,
        patch: str,
        result: Any,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        """Record a completed task attempt in the database.

        Inserts one row into ``file_changes`` per file mentioned in *patch*
        and one row into ``test_results`` reflecting whether *result* passed.

        Args:
            session_id: ID of the session to record against.
            task: Human-readable task description.
            patch: Unified diff string produced by the code generator.
            result: A ``ValidationResult``-like object with ``passed`` bool.
            prompt_tokens: Number of prompt tokens used for this task.
            completion_tokens: Number of completion tokens used for this task.

        Raises:
            SessionNotFoundError: If *session_id* does not exist.
            DatabaseCorruptError: If the database is corrupt.
        """
        self._assert_session_exists(session_id)
        now = _utcnow_iso()
        conn = self._connect()
        try:
            self._persist_task_record(
                conn, session_id, patch, result, now, prompt_tokens, completion_tokens
            )
            conn.commit()
        finally:
            conn.close()

    def _persist_task_record(
        self,
        conn: sqlite3.Connection,
        session_id: str,
        patch: str,
        result: Any,
        now: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        """Write file_changes and test_results rows for one task."""
        failures_json = _serialise_failures(result)
        passed_int = 1 if result.passed else 0
        file_paths = _extract_file_paths(patch)
        self._insert_file_changes(conn, session_id, file_paths, patch, now)
        self._insert_test_result(
            conn, session_id, passed_int, failures_json, now, prompt_tokens, completion_tokens
        )
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (now, session_id),
        )

    def _insert_file_changes(
        self,
        conn: sqlite3.Connection,
        session_id: str,
        file_paths: list[str],
        patch: str,
        now: str,
    ) -> None:
        """Insert file_changes rows for each file path in the patch.

        Args:
            conn: Open SQLite connection.
            session_id: Session to record against.
            file_paths: List of file paths extracted from the patch.
            patch: Full unified diff string.
            now: ISO-8601 timestamp string.
        """
        for file_path in file_paths:
            conn.execute(
                "INSERT INTO file_changes (session_id, file_path, patch, applied_at) "
                "VALUES (?, ?, ?, ?)",
                (session_id, file_path, patch, now),
            )

    def _insert_test_result(
        self,
        conn: sqlite3.Connection,
        session_id: str,
        passed_int: int,
        failures_json: str | None,
        now: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        """Insert a single test_results row.

        Args:
            conn: Open SQLite connection.
            session_id: Session to record against.
            passed_int: 1 if passed, 0 if failed.
            failures_json: JSON-serialised failures list or None.
            now: ISO-8601 timestamp string.
            prompt_tokens: Prompt tokens used for this task.
            completion_tokens: Completion tokens used for this task.
        """
        conn.execute(
            "INSERT INTO test_results "
            "(session_id, passed, failures, recorded_at, prompt_tokens, completion_tokens) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, passed_int, failures_json, now, prompt_tokens, completion_tokens),
        )

    def record_observation(self, session_id: str, observation: str) -> None:
        """Record a free-text observation as a decision for *session_id*.

        Args:
            session_id: ID of the session to record against.
            observation: Free-text description of the observation or decision.

        Raises:
            SessionNotFoundError: If *session_id* does not exist.
            DatabaseCorruptError: If the database is corrupt and recovery fails.
        """
        self._assert_session_exists(session_id)
        now = _utcnow_iso()
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO decisions (session_id, description, rationale, decided_at) "
                "VALUES (?, ?, NULL, ?)",
                (session_id, observation, now),
            )
            conn.commit()
        finally:
            conn.close()

    def cache_symbol_context(
        self,
        session_id: str,
        symbol_id: str,
        file_path: str,
        content: str,
        line_start: int,
        line_end: int,
    ) -> None:
        """Cache windowed context for a symbol in the database."""
        self._assert_session_exists(session_id)
        now = _utcnow_iso()
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO symbol_snapshots (session_id, symbol_id, file_path, content, line_start, line_end, captured_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, symbol_id, file_path, content, line_start, line_end, now),
            )
            conn.commit()
        finally:
            conn.close()

    def get_symbol_context(self, session_id: str, symbol_id: str) -> str | None:
        """Retrieve the cached context for a symbol if it exists."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT content FROM symbol_snapshots WHERE session_id = ? AND symbol_id = ? ORDER BY captured_at DESC LIMIT 1",
                (session_id, symbol_id),
            ).fetchone()
        finally:
            conn.close()
        return row[0] if row else None
    def save_harness_plan(self, session_id: str, tasks: list["AtomicTask"]) -> None:
        """Save a planned sequence of atomic tasks."""
        self._assert_session_exists(session_id)
        import json
        now = _utcnow_iso()
        conn = self._connect()
        try:
            for task in tasks:
                conn.execute(
                    "INSERT OR REPLACE INTO atomic_tasks (id, session_id, description, target_file, target_symbol, depends_on, status, retry_count, applied_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (task.id, session_id, task.description, task.target_file, task.target_symbol, json.dumps(task.depends_on), task.status, task.retry_count, now)
                )
            conn.commit()
        finally:
            conn.close()

    def update_task_status(self, session_id: str, task_id: str, status: str) -> None:
        """Update the status of an atomic task."""
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE atomic_tasks SET status = ?, applied_at = ? WHERE session_id = ? AND id = ?",
                (status, _utcnow_iso(), session_id, task_id)
            )
            conn.commit()
        finally:
            conn.close()

    def save_task_summary(self, session_id: str, summary: "TaskSummary") -> None:
        """Save the execution summary of an atomic task."""
        import json
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO task_summaries (session_id, task_id, files_changed, symbols_added, symbols_modified, decisions, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, summary.task_id, json.dumps(summary.files_changed), json.dumps(summary.symbols_added), json.dumps(summary.symbols_modified), json.dumps(summary.decisions), _utcnow_iso())
            )
            conn.commit()
        finally:
            conn.close()

    def get_task_summaries(self, session_id: str) -> list["TaskSummary"]:
        """Retrieve all completed task summaries for the session."""
        import json
        from local_sage.agent.harness import TaskSummary
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT task_id, files_changed, symbols_added, symbols_modified, decisions FROM task_summaries WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,)
            ).fetchall()
        finally:
            conn.close()
        return [
            TaskSummary(
                task_id=row[0],
                files_changed=json.loads(row[1]),
                symbols_added=json.loads(row[2]),
                symbols_modified=json.loads(row[3]),
                decisions=json.loads(row[4])
            ) for row in rows
        ]

    def get_session_summary(self, session_id: str) -> SessionSummary:
        """Return an aggregated summary of activity for *session_id*.

        Args:
            session_id: ID of the session to summarise.

        Returns:
            A ``SessionSummary`` with task/patch counts, last-active timestamp,
            and a list of recorded observation strings.

        Raises:
            SessionNotFoundError: If *session_id* does not exist.
            DatabaseCorruptError: If the database is corrupt and recovery fails.
        """
        self._assert_session_exists(session_id)
        conn = self._connect()
        try:
            counts = self._fetch_summary_counts(conn, session_id)
            observations = self._fetch_observations(conn, session_id)
        finally:
            conn.close()
        return SessionSummary(
            session_id=session_id,
            task_count=counts["task_count"],
            patch_count=counts["patch_count"],
            last_active=counts["last_active"],
            observations=observations,
            prompt_tokens=counts["prompt_tokens"],
            completion_tokens=counts["completion_tokens"],
            estimated_cost_usd=counts["estimated_cost_usd"],
            actual_cost_usd=counts["actual_cost_usd"],
        )

    def _fetch_summary_counts(self, conn: sqlite3.Connection, session_id: str) -> dict[str, Any]:
        """Fetch task count, patch count, and last-active timestamp.

        Args:
            conn: Open SQLite connection.
            session_id: Session to query.

        Returns:
            Dict with ``task_count``, ``patch_count``, and ``last_active``.
        """
        task_count = _fetch_scalar(
            conn,
            "SELECT COUNT(*) FROM test_results WHERE session_id = ?",
            (session_id,),
        )
        patch_count = _fetch_scalar(
            conn,
            "SELECT COUNT(*) FROM file_changes WHERE session_id = ?",
            (session_id,),
        )
        last_active_str = _fetch_scalar(
            conn,
            "SELECT MAX(recorded_at) FROM test_results WHERE session_id = ?",
            (session_id,),
        )
        if last_active_str is None:
            last_active_str = self._fallback_last_active(conn, session_id)
        prompt_tokens, completion_tokens = self._fetch_token_totals(conn, session_id)
        total_tokens = prompt_tokens + completion_tokens
        return {
            "task_count": int(task_count),
            "patch_count": int(patch_count),
            "last_active": _parse_iso(last_active_str),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "estimated_cost_usd": total_tokens * COST_PER_TOKEN,
            "actual_cost_usd": 0.0,
        }

    def _fallback_last_active(self, conn: sqlite3.Connection, session_id: str) -> str:
        """Return session updated_at when no test_results exist."""
        row = conn.execute(
            "SELECT updated_at FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return row[0] if row else _utcnow_iso()

    def _fetch_token_totals(self, conn: sqlite3.Connection, session_id: str) -> tuple[int, int]:
        """Return summed prompt and completion tokens for *session_id*."""
        prompt = int(
            _fetch_scalar(
                conn,
                "SELECT COALESCE(SUM(prompt_tokens), 0) FROM test_results WHERE session_id = ?",
                (session_id,),
            )
            or 0
        )
        completion = int(
            _fetch_scalar(
                conn,
                "SELECT COALESCE(SUM(completion_tokens), 0) FROM test_results WHERE session_id = ?",
                (session_id,),
            )
            or 0
        )
        return prompt, completion

    def _fetch_observations(self, conn: sqlite3.Connection, session_id: str) -> list[str]:
        """Fetch all decision descriptions for *session_id*.

        Args:
            conn: Open SQLite connection.
            session_id: Session to query.

        Returns:
            List of observation strings ordered by decided_at.
        """
        return [
            r[0]
            for r in conn.execute(
                "SELECT description FROM decisions WHERE session_id = ? ORDER BY decided_at",
                (session_id,),
            ).fetchall()
        ]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """Open a connection to the database, recovering from corruption.

        The caller is responsible for closing the returned connection.

        Returns:
            An open ``sqlite3.Connection`` with foreign-key enforcement enabled.

        Raises:
            DatabaseCorruptError: If the database is corrupt and a new empty
                database could not be created.
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("PRAGMA foreign_keys = ON")
            # Probe the database to trigger any corruption error early.
            conn.execute("SELECT 1")
            return conn
        except sqlite3.DatabaseError as exc:
            self._recover_corrupt_db()
            raise DatabaseCorruptError(
                f"Database at {self.db_path} was corrupt and has been renamed. "
                "A new empty database has been created."
            ) from exc

    def _ensure_schema(self) -> None:
        """Apply the SQL schema to the database (idempotent).

        Raises:
            DatabaseCorruptError: If the database is corrupt during schema init.
        """
        schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        conn = self._connect()
        try:
            conn.executescript(schema_sql)
            self._migrate_schema(conn)
        finally:
            conn.close()

    def _migrate_schema(self, conn: sqlite3.Connection) -> None:
        """Apply idempotent schema migrations for existing databases.

        Args:
            conn: Open SQLite connection.
        """
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(test_results)").fetchall()
        }
        if "prompt_tokens" not in columns:
            conn.execute(
                "ALTER TABLE test_results ADD COLUMN prompt_tokens INTEGER NOT NULL DEFAULT 0"
            )
        if "completion_tokens" not in columns:
            conn.execute(
                "ALTER TABLE test_results ADD COLUMN completion_tokens INTEGER NOT NULL DEFAULT 0"
            )
        conn.commit()

    def _recover_corrupt_db(self) -> None:
        """Rename the corrupt database and create a fresh one.

        The corrupt file is renamed to ``memory.db.corrupt.<timestamp>`` so
        that it can be inspected later.  A new empty database is then created
        at the original path.
        """
        timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
        corrupt_path = self.db_path.with_suffix(f".db.corrupt.{timestamp}")
        try:
            self.db_path.rename(corrupt_path)
            logger.warning(
                "Corrupt database renamed to %s; creating a new empty database.",
                corrupt_path,
            )
        except OSError:
            logger.warning(
                "Could not rename corrupt database at %s; creating a new one anyway.",
                self.db_path,
            )
        schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.executescript(schema_sql)
        finally:
            conn.close()

    def _assert_session_exists(self, session_id: str) -> None:
        """Raise ``SessionNotFoundError`` if *session_id* is not in the DB.

        Args:
            session_id: The session ID to verify.

        Raises:
            SessionNotFoundError: If the session does not exist.
        """
        conn = self._connect()
        try:
            row = conn.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone()
        finally:
            conn.close()
        if row is None:
            raise SessionNotFoundError(
                f"Session '{session_id}' not found in database.",
                session_id=session_id,
            )


# ---------------------------------------------------------------------------
# Module-level helpers (private)
# ---------------------------------------------------------------------------


def _utcnow_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(tz=UTC).isoformat()


def _parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 string into a timezone-aware ``datetime``.

    Args:
        value: ISO-8601 formatted datetime string.

    Returns:
        A UTC-aware ``datetime`` object.
    """
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _row_to_session(row: tuple[Any, ...]) -> Session:
    """Convert a raw DB row to a ``Session`` dataclass.

    Args:
        row: Tuple of (id, repo_path, created_at, updated_at).

    Returns:
        A populated ``Session`` instance.
    """
    return Session(
        session_id=row[0],
        repo_path=Path(row[1]),
        created_at=_parse_iso(row[2]),
        updated_at=_parse_iso(row[3]),
    )


def _fetch_scalar(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> Any:
    """Execute *sql* and return the first column of the first row.

    Args:
        conn: An open SQLite connection.
        sql: A SELECT statement returning a single scalar value.
        params: Parameterised query arguments.

    Returns:
        The scalar value, or ``None`` if no rows were returned.
    """
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def _extract_file_paths(patch: str) -> list[str]:
    """Extract the list of modified file paths from a unified diff string.

    Looks for lines starting with ``+++ b/`` (the "new file" header in a
    unified diff).  Falls back to ``--- a/`` lines if no ``+++`` lines are
    found.  Returns ``["<unknown>"]`` for empty or unparseable patches.

    Args:
        patch: A unified diff string.

    Returns:
        A deduplicated list of file paths mentioned in the patch.
    """
    paths: list[str] = []
    for line in patch.splitlines():
        if line.startswith("+++ b/"):
            paths.append(line[6:].strip())
        elif line.startswith("+++ ") and not line.startswith("+++ b/"):
            candidate = line[4:].strip()
            if candidate and candidate != "/dev/null":
                paths.append(candidate)
    if not paths:
        for line in patch.splitlines():
            if line.startswith("--- a/"):
                paths.append(line[6:].strip())
    return list(dict.fromkeys(paths)) or ["<unknown>"]


def _serialise_failures(result: Any) -> str | None:
    """Serialise the failures list from a ValidationResult to JSON.

    Args:
        result: A ``ValidationResult``-like object with a ``failures`` attribute.

    Returns:
        A JSON string of failure representations, or ``None`` if there are none.
    """
    if not result.failures:
        return None
    try:
        return json.dumps([str(f) for f in result.failures])
    except (TypeError, ValueError):
        return json.dumps([repr(f) for f in result.failures])

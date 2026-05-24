"""Layer 4 — Session Memory: SQLite session storage and Mem0 semantic search.

Public API:
    SessionManager  — SQLite-backed session persistence and retrieval.
    Session         — dataclass representing a single agent session.
    SessionSummary  — aggregated summary of a session's activity.
    SemanticMemory  — Mem0-backed semantic search over past observations.
    SessionError         — base exception for all session-memory errors.
    DatabaseCorruptError — raised when the SQLite database is corrupt.
    SessionNotFoundError — raised when a requested session does not exist.
"""

from local_sage.memory.exceptions import (
    DatabaseCorruptError,
    SessionError,
    SessionNotFoundError,
)
from local_sage.memory.semantic import SemanticMemory
from local_sage.memory.session import Session, SessionManager, SessionSummary

__all__ = [
    "SessionManager",
    "Session",
    "SessionSummary",
    "SemanticMemory",
    "SessionError",
    "DatabaseCorruptError",
    "SessionNotFoundError",
]

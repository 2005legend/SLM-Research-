"""Layer 5 — Wiki: agent-maintained markdown knowledge base.

Public API:
    WikiManager  — reads, writes, lists, and searches wiki entries.
    WikiEntry    — dataclass representing a single wiki entry.
    WikiError    — base exception for all wiki errors.
    WikiReadError — raised when a wiki entry cannot be read from disk.
"""

from local_sage.wiki.exceptions import WikiError, WikiReadError
from local_sage.wiki.manager import WikiEntry, WikiManager

__all__ = [
    "WikiManager",
    "WikiEntry",
    "WikiError",
    "WikiReadError",
]

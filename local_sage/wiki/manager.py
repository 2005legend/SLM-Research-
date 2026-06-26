"""WikiManager and WikiEntry dataclass for Layer 5 — Wiki.

This module provides:
- ``WikiEntry``   — dataclass representing a single wiki entry.
- ``WikiManager`` — reads, writes, lists, and searches markdown wiki entries.

Files are stored as ``<wiki_dir>/<slug>.md`` where the slug is the title
lowercased with spaces replaced by underscores.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import re

from local_sage.wiki.exceptions import WikiReadError

logger = logging.getLogger(__name__)


@dataclass
class WikiEntry:
    """A single entry in the agent's markdown knowledge base.

    Attributes:
        title: Human-readable title of the entry.
        file_path: Path to the markdown file on disk.
        content: Full markdown content of the entry.
        last_modified: UTC timestamp of the most recent write.
    """

    title: str
    file_path: Path
    content: str
    last_modified: datetime


def _title_to_slug(title: str) -> str:
    """Convert a human-readable title to a filesystem-safe slug.

    Lowercases the title, replaces non-alphanumeric characters
    with underscores, and truncates to 100 characters max.

    Args:
        title: Human-readable entry title (e.g. ``"Rate Limiter"``).

    Returns:
        A slug string suitable for use as a filename stem
        (e.g. ``"rate_limiter"``).
    """
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", title.lower())
    return slug[:100].strip("_")


def _mtime_to_utc(file_path: Path) -> datetime:
    """Return the last-modified time of *file_path* as a UTC-aware datetime.

    Args:
        file_path: Path to the file whose mtime is needed.

    Returns:
        A UTC-aware ``datetime`` representing the file's last-modified time.
    """
    mtime = file_path.stat().st_mtime
    return datetime.fromtimestamp(mtime, tz=UTC)


class WikiManager:
    """Reads, writes, lists, and searches the agent's markdown wiki.

    Files are stored as ``<wiki_dir>/<slug>.md``.  The wiki directory is
    created on first write if it does not already exist.

    Attributes:
        wiki_dir: Path to the directory that holds all wiki markdown files.
    """

    def __init__(self, wiki_dir: Path) -> None:
        """Initialise the manager with the wiki directory path.

        The directory is **not** created here; it is created lazily on the
        first call to :meth:`write_entry`.

        Args:
            wiki_dir: Path to the directory that holds wiki markdown files.
        """
        self.wiki_dir = wiki_dir

    def write_entry(self, title: str, content: str) -> WikiEntry:
        """Create or overwrite a wiki entry for *title*.

        The wiki directory is created if it does not exist.  The file is
        named ``<slug>.md`` where the slug is derived from *title*.

        Args:
            title: Human-readable title for the entry.
            content: Full markdown content to write.

        Returns:
            A :class:`WikiEntry` reflecting the written file.
        """
        self.wiki_dir.mkdir(parents=True, exist_ok=True)
        slug = _title_to_slug(title)
        file_path = self.wiki_dir / f"{slug}.md"
        file_path.write_text(content, encoding="utf-8")
        last_modified = _mtime_to_utc(file_path)
        return WikiEntry(
            title=title,
            file_path=file_path,
            content=content,
            last_modified=last_modified,
        )

    def read_entry(self, title: str) -> WikiEntry:
        """Load and return the wiki entry for *title*.

        Args:
            title: Human-readable title of the entry to read.

        Returns:
            A :class:`WikiEntry` with the file's current content and mtime.

        Raises:
            WikiReadError: If the file does not exist or cannot be read.
        """
        slug = _title_to_slug(title)
        file_path = self.wiki_dir / f"{slug}.md"
        try:
            content = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise WikiReadError(
                f"Cannot read wiki entry '{title}' from {file_path}: {exc}",
                file_path=file_path,
                os_error=exc,
            ) from exc
        last_modified = _mtime_to_utc(file_path)
        return WikiEntry(
            title=title,
            file_path=file_path,
            content=content,
            last_modified=last_modified,
        )

    def list_entries(self) -> list[WikiEntry]:
        """Return all wiki entries sorted by title.

        If the wiki directory does not exist, an empty list is returned
        rather than raising an error.

        Returns:
            A list of :class:`WikiEntry` objects, one per ``.md`` file,
            sorted alphabetically by title.
        """
        if not self.wiki_dir.exists():
            return []
        entries: list[WikiEntry] = []
        for md_file in sorted(self.wiki_dir.glob("*.md")):
            title = md_file.stem.replace("_", " ").title()
            try:
                content = md_file.read_text(encoding="utf-8")
                last_modified = _mtime_to_utc(md_file)
            except OSError:
                logger.warning("Skipping unreadable wiki file: %s", md_file)
                continue
            entries.append(
                WikiEntry(
                    title=title,
                    file_path=md_file,
                    content=content,
                    last_modified=last_modified,
                )
            )
        return entries

    def search_entries(self, query: str) -> list[WikiEntry]:
        """Return all entries whose content contains at least one query token.

        Tokenises *query* by splitting on whitespace and lowercasing each
        token.  An entry matches if any token appears anywhere in its content
        (case-insensitive).  No external dependencies are used.

        Args:
            query: A free-text search string.

        Returns:
            A list of matching :class:`WikiEntry` objects in the order they
            appear in :meth:`list_entries`.  Returns an empty list if *query*
            is blank or no entries match.
        """
        tokens = [t.lower() for t in query.split() if t]
        if not tokens:
            return []
        results: list[WikiEntry] = []
        for entry in self.list_entries():
            content_lower = entry.content.lower()
            if any(token in content_lower for token in tokens):
                results.append(entry)
        return results

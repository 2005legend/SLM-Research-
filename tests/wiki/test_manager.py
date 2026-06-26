"""Unit and property-based tests for WikiManager (Layer 5 — Wiki).

Covers write_entry, read_entry, list_entries, search_entries, WikiReadError
on filesystem failures, and Properties 16, 17, and 18.

**Validates: Requirements 5.1, 5.2, 5.3, 5.4**
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from local_sage.wiki.exceptions import WikiReadError
from local_sage.wiki.manager import WikiEntry, WikiManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manager(tmp_path: Path) -> WikiManager:
    """Return a WikiManager pointing at a fresh temporary wiki directory.

    Args:
        tmp_path: A temporary directory provided by pytest or created by the caller.

    Returns:
        A WikiManager whose wiki_dir is ``tmp_path / "wiki"``.
    """
    return WikiManager(tmp_path / "wiki")


# ---------------------------------------------------------------------------
# Unit tests — write_entry
# ---------------------------------------------------------------------------


class TestWriteEntry:
    """Unit tests for WikiManager.write_entry()."""

    def test_write_entry_creates_file(self, tmp_path: Path) -> None:
        """write_entry() creates a .md file inside wiki_dir."""
        manager = _make_manager(tmp_path)
        manager.write_entry("Rate Limiter", "# Rate Limiter\nSome content.")
        expected = manager.wiki_dir / "rate_limiter.md"
        assert expected.exists()

    def test_write_entry_returns_wiki_entry(self, tmp_path: Path) -> None:
        """write_entry() returns a WikiEntry with correct title and content."""
        manager = _make_manager(tmp_path)
        content = "# Auth Patterns\nUse JWT tokens."
        entry = manager.write_entry("Auth Patterns", content)
        assert isinstance(entry, WikiEntry)
        assert entry.title == "Auth Patterns"
        assert entry.content == content
        assert entry.file_path == manager.wiki_dir / "auth_patterns.md"
        assert entry.last_modified is not None

    def test_write_entry_overwrites_existing_file(self, tmp_path: Path) -> None:
        """write_entry() overwrites an existing entry with new content."""
        manager = _make_manager(tmp_path)
        manager.write_entry("My Topic", "original content")
        entry = manager.write_entry("My Topic", "updated content")
        assert entry.content == "updated content"

    def test_write_entry_creates_wiki_dir_if_missing(self, tmp_path: Path) -> None:
        """write_entry() creates wiki_dir when it does not yet exist."""
        wiki_dir = tmp_path / "nested" / "wiki"
        manager = WikiManager(wiki_dir)
        assert not wiki_dir.exists()
        manager.write_entry("New Entry", "content")
        assert wiki_dir.exists()

    def test_write_entry_invalid_windows_filename(self, tmp_path: Path) -> None:
        """write_entry() succeeds with a title containing invalid Windows path chars."""
        manager = _make_manager(tmp_path)
        title = 'fix the divide-by-zero bug in simple_api/core.py'
        entry = manager.write_entry(title, "content")
        assert entry.title == title
        assert entry.file_path.exists()
        assert entry.file_path.name == "fix_the_divide-by-zero_bug_in_simple_api_core_py.md"


# ---------------------------------------------------------------------------
# Unit tests — read_entry
# ---------------------------------------------------------------------------


class TestReadEntry:
    """Unit tests for WikiManager.read_entry()."""

    def test_read_entry_returns_correct_content(self, tmp_path: Path) -> None:
        """read_entry() returns the content that was previously written."""
        manager = _make_manager(tmp_path)
        content = "# Hello\nThis is a wiki entry."
        manager.write_entry("Hello", content)
        entry = manager.read_entry("Hello")
        assert entry.content == content

    def test_read_entry_returns_wiki_entry_dataclass(self, tmp_path: Path) -> None:
        """read_entry() returns a WikiEntry with correct title and file_path."""
        manager = _make_manager(tmp_path)
        manager.write_entry("My Entry", "some content")
        entry = manager.read_entry("My Entry")
        assert isinstance(entry, WikiEntry)
        assert entry.title == "My Entry"
        assert entry.file_path == manager.wiki_dir / "my_entry.md"
        assert entry.last_modified is not None

    def test_read_entry_raises_wiki_read_error_on_missing_file(self, tmp_path: Path) -> None:
        """read_entry() raises WikiReadError when the file does not exist."""
        manager = _make_manager(tmp_path)
        with pytest.raises(WikiReadError) as exc_info:
            manager.read_entry("Nonexistent Entry")
        error = exc_info.value
        assert error.file_path == manager.wiki_dir / "nonexistent_entry.md"
        assert isinstance(error.os_error, OSError)


# ---------------------------------------------------------------------------
# Unit tests — list_entries
# ---------------------------------------------------------------------------


class TestListEntries:
    """Unit tests for WikiManager.list_entries()."""

    def test_list_entries_returns_empty_for_nonexistent_dir(self, tmp_path: Path) -> None:
        """list_entries() returns [] when wiki_dir does not exist."""
        manager = WikiManager(tmp_path / "does_not_exist")
        assert manager.list_entries() == []

    def test_list_entries_returns_all_entries(self, tmp_path: Path) -> None:
        """list_entries() returns one WikiEntry per written .md file."""
        manager = _make_manager(tmp_path)
        manager.write_entry("Alpha", "content alpha")
        manager.write_entry("Beta", "content beta")
        manager.write_entry("Gamma", "content gamma")
        entries = manager.list_entries()
        assert len(entries) == 3

    def test_list_entries_each_has_last_modified(self, tmp_path: Path) -> None:
        """Every entry returned by list_entries() has a non-None last_modified."""
        manager = _make_manager(tmp_path)
        manager.write_entry("Entry One", "content")
        entries = manager.list_entries()
        assert len(entries) == 1
        assert entries[0].last_modified is not None

    def test_list_entries_returns_empty_for_empty_dir(self, tmp_path: Path) -> None:
        """list_entries() returns [] when wiki_dir exists but has no .md files."""
        manager = _make_manager(tmp_path)
        manager.wiki_dir.mkdir(parents=True, exist_ok=True)
        assert manager.list_entries() == []


# ---------------------------------------------------------------------------
# Unit tests — search_entries
# ---------------------------------------------------------------------------


class TestSearchEntries:
    """Unit tests for WikiManager.search_entries()."""

    def test_search_entries_returns_matching_entries(self, tmp_path: Path) -> None:
        """search_entries() returns entries whose content contains a query token."""
        manager = _make_manager(tmp_path)
        manager.write_entry("Rate Limiter", "token bucket algorithm for rate limiting")
        manager.write_entry("Auth Patterns", "JWT and OAuth2 authentication flows")
        results = manager.search_entries("rate")
        assert len(results) == 1

    def test_search_entries_returns_empty_for_no_match(self, tmp_path: Path) -> None:
        """search_entries() returns [] when no entries contain the query token."""
        manager = _make_manager(tmp_path)
        manager.write_entry("Rate Limiter", "token bucket algorithm")
        results = manager.search_entries("kubernetes")
        assert results == []

    def test_search_entries_returns_empty_for_blank_query(self, tmp_path: Path) -> None:
        """search_entries() returns [] for an empty or whitespace-only query."""
        manager = _make_manager(tmp_path)
        manager.write_entry("Some Entry", "some content here")
        assert manager.search_entries("") == []
        assert manager.search_entries("   ") == []

    def test_search_entries_is_case_insensitive(self, tmp_path: Path) -> None:
        """search_entries() matches tokens regardless of case."""
        manager = _make_manager(tmp_path)
        manager.write_entry("Auth", "JWT Authentication flow")
        assert len(manager.search_entries("JWT")) == 1
        assert len(manager.search_entries("jwt")) == 1

    def test_search_entries_multi_token_matches_any(self, tmp_path: Path) -> None:
        """search_entries() returns entries matching any token in a multi-word query."""
        manager = _make_manager(tmp_path)
        manager.write_entry("Rate Limiter", "token bucket algorithm")
        manager.write_entry("Auth Patterns", "JWT authentication")
        results = manager.search_entries("token jwt")
        assert len(results) == 2


# ---------------------------------------------------------------------------
# Unit tests — WikiReadError on filesystem failures
# ---------------------------------------------------------------------------


class TestWikiReadError:
    """Unit tests for WikiReadError raised on filesystem failures."""

    def test_wiki_read_error_has_file_path_attribute(self, tmp_path: Path) -> None:
        """WikiReadError.file_path points to the missing file."""
        manager = _make_manager(tmp_path)
        expected_path = manager.wiki_dir / "missing_entry.md"
        with pytest.raises(WikiReadError) as exc_info:
            manager.read_entry("Missing Entry")
        assert exc_info.value.file_path == expected_path

    def test_wiki_read_error_has_os_error_attribute(self, tmp_path: Path) -> None:
        """WikiReadError.os_error is the underlying OSError from the filesystem."""
        manager = _make_manager(tmp_path)
        with pytest.raises(WikiReadError) as exc_info:
            manager.read_entry("No Such Entry")
        assert isinstance(exc_info.value.os_error, OSError)

    def test_wiki_read_error_message_contains_title(self, tmp_path: Path) -> None:
        """WikiReadError message includes the entry title."""
        manager = _make_manager(tmp_path)
        with pytest.raises(WikiReadError) as exc_info:
            manager.read_entry("Specific Title")
        assert "Specific Title" in str(exc_info.value)

    def test_wiki_read_error_is_subclass_of_wiki_error(self, tmp_path: Path) -> None:
        """WikiReadError is a subclass of WikiError."""
        from local_sage.wiki.exceptions import WikiError

        manager = _make_manager(tmp_path)
        with pytest.raises(WikiError):
            manager.read_entry("Nonexistent")


# ---------------------------------------------------------------------------
# Property 16: Wiki entry round-trip (write → read)
# ---------------------------------------------------------------------------


@given(
    title=st.text(
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd"),
            whitelist_characters=" ",
        ),
        min_size=1,
        max_size=50,
    ).filter(lambda t: t.strip() != ""),
    content=st.text(
        alphabet=st.characters(
            blacklist_characters="\r",
            blacklist_categories=("Cs",),  # exclude surrogates
        ),
        min_size=0,
        max_size=2000,
    ),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_16_wiki_entry_round_trip(title: str, content: str) -> None:
    """Property 16: Wiki entry round-trip (write → read).

    For any title string and markdown content string, calling
    WikiManager.write_entry(title, content) followed by
    WikiManager.read_entry(title) SHALL return a WikiEntry whose content
    equals the original content string.

    # Feature: local-sage, Property 16: Wiki entry round-trip (write → read)
    **Validates: Requirements 5.1, 5.2**
    """
    # Feature: local-sage, Property 16: Wiki entry round-trip (write → read)
    with tempfile.TemporaryDirectory() as tmp:
        wiki_dir = Path(tmp) / "wiki"
        manager = WikiManager(wiki_dir)
        manager.write_entry(title, content)
        entry = manager.read_entry(title)
        assert entry.content == content


# ---------------------------------------------------------------------------
# Property 17: Wiki search returns entries containing query keywords
# ---------------------------------------------------------------------------


@given(
    keyword=st.text(
        alphabet=st.characters(whitelist_categories=("Ll",)),
        min_size=3,
        max_size=12,
    ).filter(lambda k: k.strip() != ""),
    extra_contents=st.lists(
        st.text(min_size=0, max_size=200),
        min_size=0,
        max_size=4,
    ),
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_17_search_returns_entries_containing_keyword(
    keyword: str,
    extra_contents: list[str],
) -> None:
    """Property 17: Wiki search returns entries containing query keywords.

    For any set of wiki entries where at least one entry contains a keyword K,
    calling WikiManager.search_entries(K) SHALL return a list that includes
    that entry.

    # Feature: local-sage, Property 17: Wiki search returns entries containing query keywords
    **Validates: Requirements 5.4**
    """
    # Feature: local-sage, Property 17: Wiki search returns entries containing query keywords
    with tempfile.TemporaryDirectory() as tmp:
        wiki_dir = Path(tmp) / "wiki"
        manager = WikiManager(wiki_dir)

        matching_content = f"This entry contains the keyword {keyword} in its body."
        manager.write_entry("Matching Entry", matching_content)

        for idx, extra in enumerate(extra_contents):
            safe_content = extra.replace(keyword, "REPLACED")
            manager.write_entry(f"Extra Entry {idx}", safe_content)

        results = manager.search_entries(keyword)
        result_contents = [e.content for e in results]
        assert any(keyword in c for c in result_contents)


# ---------------------------------------------------------------------------
# Property 18: Wiki list completeness
# ---------------------------------------------------------------------------


@given(
    entries=st.lists(
        st.tuples(
            st.from_regex(r"[a-z]{4,12}", fullmatch=True),
            st.text(min_size=0, max_size=200),
        ),
        min_size=1,
        max_size=10,
    )
)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_18_wiki_list_completeness(
    entries: list[tuple[str, str]],
) -> None:
    """Property 18: Wiki list completeness.

    For any set of N wiki entries written via WikiManager.write_entry(),
    calling WikiManager.list_entries() SHALL return exactly N entries
    (assuming no deletions), each with a non-None last_modified timestamp.

    # Feature: local-sage, Property 18: Wiki list completeness
    **Validates: Requirements 5.3**
    """
    # Feature: local-sage, Property 18: Wiki list completeness
    with tempfile.TemporaryDirectory() as tmp:
        wiki_dir = Path(tmp) / "wiki"
        manager = WikiManager(wiki_dir)

        seen_slugs: set[str] = set()
        unique_entries: list[tuple[str, str]] = []
        for title, content in entries:
            slug = title.lower().replace(" ", "_")
            if slug not in seen_slugs:
                seen_slugs.add(slug)
                unique_entries.append((title, content))

        for title, content in unique_entries:
            manager.write_entry(title, content)

        listed = manager.list_entries()
        assert len(listed) == len(unique_entries)
        for entry in listed:
            assert entry.last_modified is not None

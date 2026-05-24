"""Exception hierarchy for Layer 3 — Repo Graph.

All exceptions are typed subclasses of ``RepoGraphError``.
"""

from pathlib import Path


class RepoGraphError(Exception):
    """Base exception for all repo-graph errors.

    Attributes:
        message: Human-readable description of the error.
    """

    def __init__(self, message: str) -> None:
        """Initialise with a descriptive error message.

        Args:
            message: Human-readable description of the error.
        """
        super().__init__(message)
        self.message = message


class IndexLoadError(RepoGraphError):
    """Raised when the cached SymbolGraph index cannot be loaded from disk.

    Attributes:
        cache_path: Path to the index file that could not be loaded.
    """

    def __init__(self, message: str, cache_path: Path) -> None:
        """Initialise with the path to the unreadable cache file.

        Args:
            message: Human-readable description of the error.
            cache_path: Path to the index file that failed to load.
        """
        super().__init__(message)
        self.cache_path = cache_path


class ParseError(RepoGraphError):
    """Raised when a source file cannot be parsed by tree-sitter.

    Attributes:
        file_path: Path to the file that failed to parse.
    """

    def __init__(self, message: str, file_path: Path) -> None:
        """Initialise with the path to the unparseable source file.

        Args:
            message: Human-readable description of the error.
            file_path: Path to the source file that failed to parse.
        """
        super().__init__(message)
        self.file_path = file_path

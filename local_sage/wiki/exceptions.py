"""Exception hierarchy for Layer 5 — Wiki.

All exceptions are typed subclasses of ``WikiError``.
"""

from pathlib import Path


class WikiError(Exception):
    """Base exception for all wiki errors.

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


class WikiReadError(WikiError):
    """Raised when a wiki entry file cannot be read due to a filesystem error.

    Attributes:
        file_path: Path to the wiki file that could not be read.
        os_error: The underlying ``OSError`` from the filesystem.
    """

    def __init__(self, message: str, file_path: Path, os_error: OSError) -> None:
        """Initialise with the file path and underlying OS error.

        Args:
            message: Human-readable description of the error.
            file_path: Path to the wiki file that failed to read.
            os_error: The underlying ``OSError`` raised by the filesystem.
        """
        super().__init__(message)
        self.file_path = file_path
        self.os_error = os_error

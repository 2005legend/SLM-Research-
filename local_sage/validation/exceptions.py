"""Exception hierarchy for Layer 6 — Validation.

All exceptions are typed subclasses of ``ValidationError``.
"""

from pathlib import Path


class ValidationError(Exception):
    """Base exception for all validation errors.

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


class ValidationTimeoutError(ValidationError):
    """Raised when a subprocess validation tool exceeds its configured timeout.

    Attributes:
        tool: Name of the tool that timed out (``"pytest"``, ``"mypy"``, or ``"ruff"``).
        timeout_seconds: The timeout value that was exceeded.
    """

    def __init__(self, message: str, tool: str, timeout_seconds: int) -> None:
        """Initialise with the timed-out tool name and timeout value.

        Args:
            message: Human-readable description of the error.
            tool: Name of the tool that timed out.
            timeout_seconds: The configured timeout that was exceeded.
        """
        super().__init__(message)
        self.tool = tool
        self.timeout_seconds = timeout_seconds


class ContractParseError(ValidationError):
    """Raised when a YAML contract file is malformed or cannot be parsed.

    Attributes:
        file_path: Path to the contract file that failed to parse.
        parse_error: Description of the specific parse failure.
    """

    def __init__(self, message: str, file_path: Path, parse_error: str) -> None:
        """Initialise with the contract file path and parse error details.

        Args:
            message: Human-readable description of the error.
            file_path: Path to the malformed contract YAML file.
            parse_error: Description of the specific parse failure.
        """
        super().__init__(message)
        self.file_path = file_path
        self.parse_error = parse_error

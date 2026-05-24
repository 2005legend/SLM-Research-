"""Exception hierarchy for Layer 4 — Session Memory.

All exceptions are typed subclasses of ``SessionError``.
"""


class SessionError(Exception):
    """Base exception for all session-memory errors.

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


class DatabaseCorruptError(SessionError):
    """Raised when the SQLite database file is missing or corrupted.

    The SessionManager will rename the corrupt file and create a fresh database
    before raising this exception so the caller is aware of the recovery action.
    """


class SessionNotFoundError(SessionError):
    """Raised when a requested session ID does not exist in the database.

    Attributes:
        session_id: The session ID that was not found.
    """

    def __init__(self, message: str, session_id: str) -> None:
        """Initialise with the missing session ID.

        Args:
            message: Human-readable description of the error.
            session_id: The session ID that could not be found.
        """
        super().__init__(message)
        self.session_id = session_id

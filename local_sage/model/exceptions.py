"""Exception hierarchy for Layer 1 — Model (OllamaClient).

All exceptions are typed subclasses of ``OllamaError`` so callers can catch
the base class or a specific subclass as needed.
"""


class OllamaError(Exception):
    """Base exception for all Ollama client errors.

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


class OllamaConnectionError(OllamaError):
    """Raised when the Ollama server at localhost:11434 is unreachable.

    Wraps ``httpx.ConnectError`` with a user-friendly message.
    """


class OllamaRequestError(OllamaError):
    """Raised when the Ollama server returns a non-200 HTTP status code.

    Attributes:
        status_code: The HTTP status code returned by the server.
        body: The raw response body text.
    """

    def __init__(self, message: str, status_code: int, body: str) -> None:
        """Initialise with status code and response body.

        Args:
            message: Human-readable description of the error.
            status_code: HTTP status code (e.g. 400, 500).
            body: Raw response body returned by the server.
        """
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class OllamaTimeoutError(OllamaError):
    """Raised when a generation request exceeds the configured timeout.

    Wraps ``httpx.TimeoutException``.
    """

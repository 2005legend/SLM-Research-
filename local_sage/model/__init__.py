"""Layer 1 — Model: async HTTP client wrapping the Ollama inference server.

Public API:
    OllamaClient  — async client for ``/api/generate`` and health checks.
    ModelResponse — typed response dataclass returned by ``OllamaClient.generate()``.
    OllamaError            — base exception for all Ollama errors.
    OllamaConnectionError  — raised when the Ollama server is unreachable.
    OllamaRequestError     — raised on non-200 HTTP responses.
    OllamaTimeoutError     — raised when a request exceeds the configured timeout.
"""

from local_sage.model.client import ModelResponse, OllamaClient
from local_sage.model.exceptions import (
    OllamaConnectionError,
    OllamaError,
    OllamaRequestError,
    OllamaTimeoutError,
)

__all__ = [
    "OllamaClient",
    "ModelResponse",
    "OllamaError",
    "OllamaConnectionError",
    "OllamaRequestError",
    "OllamaTimeoutError",
]

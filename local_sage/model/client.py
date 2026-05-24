"""Async HTTP client for the Ollama inference server.

Communicates exclusively with ``http://localhost:11434``. Uses
``httpx.AsyncClient`` for all HTTP operations and maps Ollama-specific
errors to the typed exception hierarchy in :mod:`local_sage.model.exceptions`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import httpx

from local_sage.model.exceptions import (
    OllamaConnectionError,
    OllamaRequestError,
    OllamaTimeoutError,
)


@dataclass
class ModelResponse:
    """Typed response returned by :meth:`OllamaClient.generate`.

    Attributes:
        text: The generated text from the model.
        tokens_used: Number of tokens in the generated response (``eval_count``).
        prompt_tokens: Number of tokens in the prompt (``prompt_eval_count``).
        finish_reason: Why generation stopped: ``"stop"``, ``"length"``, or ``"error"``.
        duration_ms: Total generation time in milliseconds (``total_duration / 1_000_000``).
    """

    text: str
    tokens_used: int
    prompt_tokens: int
    finish_reason: str
    duration_ms: int


class OllamaClient:
    """Async HTTP client wrapping the Ollama ``/api/generate`` endpoint.

    Communicates exclusively with ``http://localhost:11434``. All public
    methods are coroutines and must be awaited.

    Class Attributes:
        BASE_URL: The base URL of the Ollama server (always localhost:11434).
        MODEL: The model identifier sent with every request.
        TIMEOUT_SECONDS: Request timeout in seconds.

    Example::

        client = OllamaClient()
        response = await client.generate("Write a hello-world function.")
        print(response.text)
    """

    BASE_URL: ClassVar[str] = "http://localhost:11434"
    MODEL: ClassVar[str] = "qwen2.5-coder:7b"
    TIMEOUT_SECONDS: ClassVar[int] = 120

    async def generate(self, prompt: str, system: str = "") -> ModelResponse:
        """Send a generation request to the Ollama ``/api/generate`` endpoint.

        Args:
            prompt: The user prompt to send to the model.
            system: Optional system prompt prepended to the conversation context.

        Returns:
            A :class:`ModelResponse` populated from the Ollama JSON response.

        Raises:
            OllamaConnectionError: If the Ollama server is unreachable.
            OllamaRequestError: If the server returns a non-200 HTTP status.
            OllamaTimeoutError: If the request exceeds :attr:`TIMEOUT_SECONDS`.
        """
        payload: dict[str, object] = {
            "model": self.MODEL,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {"num_ctx": 8192},
        }
        url = f"{self.BASE_URL}/api/generate"
        response = await self._post(url, payload)
        if response.status_code != 200:
            raise OllamaRequestError(
                f"Ollama returned HTTP {response.status_code}.",
                status_code=response.status_code,
                body=response.text,
            )
        return self._parse_response(response.json())

    async def _post(self, url: str, payload: dict[str, object]) -> httpx.Response:
        """Send a POST request to *url* with *payload*, handling transport errors.

        Args:
            url: Full URL to POST to.
            payload: JSON-serialisable request body.

        Returns:
            The raw ``httpx.Response``.

        Raises:
            OllamaConnectionError: If the server is unreachable.
            OllamaTimeoutError: If the request times out.
        """
        timeout = httpx.Timeout(self.TIMEOUT_SECONDS)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                return await client.post(url, json=payload)
        except httpx.ConnectError as exc:
            raise OllamaConnectionError(
                f"Cannot connect to Ollama at {self.BASE_URL}. "
                "Ensure Ollama is running with `ollama serve`."
            ) from exc
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError(
                f"Request to {url} timed out after {self.TIMEOUT_SECONDS}s."
            ) from exc

    async def health_check(self) -> bool:
        """Check whether the Ollama server is reachable and responding.

        Sends a GET request to ``/api/tags``. Returns ``True`` if the server
        responds with HTTP 200, ``False`` for any other outcome including
        connection errors, timeouts, and non-200 status codes.

        Returns:
            ``True`` if Ollama is online and healthy, ``False`` otherwise.
        """
        url = f"{self.BASE_URL}/api/tags"
        timeout = httpx.Timeout(5.0)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(url)
            return response.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError):
            return False

    def _parse_response(self, data: dict[str, object]) -> ModelResponse:
        """Convert a raw Ollama ``/api/generate`` JSON response to a :class:`ModelResponse`.

        Args:
            data: The parsed JSON dictionary from the Ollama API response.

        Returns:
            A :class:`ModelResponse` with fields mapped from the Ollama response.
        """
        total_ns = data.get("total_duration", 0)
        eval_count = data.get("eval_count", 0)
        prompt_count = data.get("prompt_eval_count", 0)
        return ModelResponse(
            text=str(data.get("response", "")),
            tokens_used=int(eval_count) if isinstance(eval_count, (int, float)) else 0,
            prompt_tokens=int(prompt_count) if isinstance(prompt_count, (int, float)) else 0,
            finish_reason=str(data.get("done_reason", "stop")),
            duration_ms=int(total_ns) // 1_000_000 if isinstance(total_ns, (int, float)) else 0,
        )

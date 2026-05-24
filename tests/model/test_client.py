"""Unit and property-based tests for OllamaClient (Layer 1 — Model).

All HTTP calls are mocked via ``unittest.mock`` — no live connections are made.

**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6**
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from local_sage.model.client import ModelResponse, OllamaClient
from local_sage.model.exceptions import (
    OllamaConnectionError,
    OllamaRequestError,
    OllamaTimeoutError,
)
from tests.strategies import http_status_strategy, ollama_response_strategy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_client(
    *,
    status_code: int = 200,
    json_data: dict[str, Any] | None = None,
    text: str = "",
) -> tuple[MagicMock, MagicMock]:
    """Return (mock_client_class, mock_client_instance) pre-configured for patching.

    Args:
        status_code: HTTP status code the mock response will return.
        json_data: JSON payload the mock response will return.
        text: Raw text the mock response will return (used for error bodies).

    Returns:
        A tuple of (mock_client_class, mock_client_instance).
    """
    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = json_data or {}
    mock_response.text = text

    mock_instance = AsyncMock()
    mock_instance.post.return_value = mock_response
    mock_instance.get.return_value = mock_response

    mock_class = MagicMock()
    mock_class.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_class.return_value.__aexit__ = AsyncMock(return_value=False)

    return mock_class, mock_instance


# ---------------------------------------------------------------------------
# Unit tests — generate()
# ---------------------------------------------------------------------------


def test_generate_raises_connection_error_on_connect_error() -> None:
    """OllamaConnectionError is raised when httpx.ConnectError occurs."""
    with patch("local_sage.model.client.httpx.AsyncClient") as mock_class:
        mock_instance = AsyncMock()
        mock_class.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_class.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_instance.post.side_effect = httpx.ConnectError("refused")

        client = OllamaClient()
        with pytest.raises(OllamaConnectionError):
            asyncio.run(client.generate("hello"))


def test_generate_raises_timeout_error_on_timeout() -> None:
    """OllamaTimeoutError is raised when httpx.TimeoutException occurs."""
    with patch("local_sage.model.client.httpx.AsyncClient") as mock_class:
        mock_instance = AsyncMock()
        mock_class.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_class.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_instance.post.side_effect = httpx.TimeoutException("timed out")

        client = OllamaClient()
        with pytest.raises(OllamaTimeoutError):
            asyncio.run(client.generate("hello"))


def test_generate_raises_request_error_on_non_200() -> None:
    """OllamaRequestError is raised when the server returns a non-200 status."""
    mock_class, _ = _make_mock_client(status_code=500, text="Internal Server Error")

    with patch("local_sage.model.client.httpx.AsyncClient", mock_class):
        client = OllamaClient()
        with pytest.raises(OllamaRequestError) as exc_info:
            asyncio.run(client.generate("hello"))

    assert exc_info.value.status_code == 500


def test_generate_returns_model_response_on_success() -> None:
    """generate() returns a ModelResponse with correct fields on HTTP 200."""
    json_data = {
        "response": "def hello(): pass",
        "eval_count": 10,
        "prompt_eval_count": 5,
        "done_reason": "stop",
        "total_duration": 1_000_000_000,
    }
    mock_class, _ = _make_mock_client(status_code=200, json_data=json_data)

    with patch("local_sage.model.client.httpx.AsyncClient", mock_class):
        client = OllamaClient()
        result = asyncio.run(client.generate("hello"))

    assert isinstance(result, ModelResponse)
    assert result.text == "def hello(): pass"
    assert result.tokens_used == 10
    assert result.prompt_tokens == 5
    assert result.finish_reason == "stop"
    assert result.duration_ms == 1000


# ---------------------------------------------------------------------------
# Unit tests — health_check()
# ---------------------------------------------------------------------------


def test_health_check_returns_true_on_200() -> None:
    """health_check() returns True when the server responds with HTTP 200."""
    mock_class, _ = _make_mock_client(status_code=200)

    with patch("local_sage.model.client.httpx.AsyncClient", mock_class):
        client = OllamaClient()
        result = asyncio.run(client.health_check())

    assert result is True


def test_health_check_returns_false_on_connect_error() -> None:
    """health_check() returns False when the server is unreachable."""
    with patch("local_sage.model.client.httpx.AsyncClient") as mock_class:
        mock_instance = AsyncMock()
        mock_class.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_class.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_instance.get.side_effect = httpx.ConnectError("refused")

        client = OllamaClient()
        result = asyncio.run(client.health_check())

    assert result is False


def test_health_check_returns_false_on_non_200() -> None:
    """health_check() returns False when the server returns a non-200 status."""
    mock_class, _ = _make_mock_client(status_code=503)

    with patch("local_sage.model.client.httpx.AsyncClient", mock_class):
        client = OllamaClient()
        result = asyncio.run(client.health_check())

    assert result is False


# ---------------------------------------------------------------------------
# Property 3: OllamaClient only sends requests to localhost:11434
# ---------------------------------------------------------------------------


@given(prompt=st.text(min_size=0, max_size=200))
@settings(max_examples=100)
def test_property_3_requests_target_localhost_only(prompt: str) -> None:
    """Property 3: OllamaClient only sends requests to localhost:11434.

    For any prompt string passed to OllamaClient.generate(), every HTTP
    request made by the client SHALL target http://localhost:11434 and no
    other host or port.

    **Validates: Requirements 2.1**
    """
    # Property 3: OllamaClient only sends requests to localhost:11434
    json_data = {
        "response": "ok",
        "eval_count": 1,
        "prompt_eval_count": 1,
        "done_reason": "stop",
        "total_duration": 1_000_000,
    }
    mock_class, mock_instance = _make_mock_client(status_code=200, json_data=json_data)

    with patch("local_sage.model.client.httpx.AsyncClient", mock_class):
        client = OllamaClient()
        asyncio.run(client.generate(prompt))

    assert mock_instance.post.call_count == 1
    call_args = mock_instance.post.call_args
    url: str = call_args[0][0] if call_args[0] else call_args[1]["url"]
    assert url.startswith("http://localhost:11434"), (
        f"Expected URL to start with http://localhost:11434, got: {url}"
    )


# ---------------------------------------------------------------------------
# Property 4: ModelResponse round-trip from Ollama API response
# ---------------------------------------------------------------------------


@given(api_response=ollama_response_strategy())
@settings(max_examples=100)
def test_property_4_model_response_round_trip(api_response: dict[str, Any]) -> None:
    """Property 4: ModelResponse round-trip from Ollama API response.

    For any valid Ollama /api/generate response JSON, OllamaClient._parse_response()
    SHALL return a ModelResponse where:
    - text equals the response field
    - tokens_used equals eval_count
    - finish_reason equals done_reason
    - duration_ms equals total_duration // 1_000_000

    **Validates: Requirements 2.2**
    """
    # Property 4: ModelResponse round-trip from Ollama API response
    client = OllamaClient()
    result = client._parse_response(api_response)

    assert result.text == api_response["response"]
    assert result.tokens_used == api_response["eval_count"]
    assert result.finish_reason == api_response["done_reason"]
    assert result.duration_ms == api_response["total_duration"] // 1_000_000


# ---------------------------------------------------------------------------
# Property 5: OllamaRequestError preserves HTTP status code
# ---------------------------------------------------------------------------


@given(status_code=http_status_strategy())
@settings(max_examples=100)
def test_property_5_request_error_preserves_status_code(status_code: int) -> None:
    """Property 5: OllamaRequestError preserves HTTP status code.

    For any HTTP status code in the range 400–599, when the Ollama server
    returns that status code, OllamaClient.generate() SHALL raise an
    OllamaRequestError whose status_code attribute equals the received
    status code.

    **Validates: Requirements 2.4**
    """
    # Property 5: OllamaRequestError preserves HTTP status code
    mock_class, _ = _make_mock_client(
        status_code=status_code,
        text=f"Error {status_code}",
    )

    with patch("local_sage.model.client.httpx.AsyncClient", mock_class):
        client = OllamaClient()
        with pytest.raises(OllamaRequestError) as exc_info:
            asyncio.run(client.generate("test prompt"))

    assert exc_info.value.status_code == status_code


# ---------------------------------------------------------------------------
# Property 6: OllamaClient always uses the correct model name
# ---------------------------------------------------------------------------


@given(prompt=st.text(min_size=0, max_size=200))
@settings(max_examples=100)
def test_property_6_correct_model_name_in_request(prompt: str) -> None:
    """Property 6: OllamaClient always uses the correct model name.

    For any prompt string, the HTTP request body sent by
    OllamaClient.generate() SHALL contain
    "model": "qwen2.5-coder:7b-instruct-q4_K_M".

    **Validates: Requirements 2.6**
    """
    # Property 6: OllamaClient always uses the correct model name
    json_data = {
        "response": "ok",
        "eval_count": 1,
        "prompt_eval_count": 1,
        "done_reason": "stop",
        "total_duration": 1_000_000,
    }
    mock_class, mock_instance = _make_mock_client(status_code=200, json_data=json_data)

    with patch("local_sage.model.client.httpx.AsyncClient", mock_class):
        client = OllamaClient()
        asyncio.run(client.generate(prompt))

    call_kwargs = mock_instance.post.call_args[1]
    request_body: dict[str, Any] = call_kwargs.get("json", {})
    assert request_body.get("model") == OllamaClient.MODEL, (
        f"Expected model '{OllamaClient.MODEL}', got: {request_body.get('model')}"
    )

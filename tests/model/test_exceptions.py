"""Tests for the OllamaClient exception hierarchy (Layer 1 — Model).

Verifies that all exceptions are correctly subclassed, carry the right
attributes, and are NOT direct subclasses of ``Exception`` (they must go
through ``OllamaError``).

**Validates: Requirements 2.3, 2.4, 2.5**
"""

from __future__ import annotations

import pytest

from local_sage.model.exceptions import (
    OllamaConnectionError,
    OllamaError,
    OllamaRequestError,
    OllamaTimeoutError,
)

# ---------------------------------------------------------------------------
# Hierarchy tests
# ---------------------------------------------------------------------------


def test_ollama_error_is_subclass_of_exception() -> None:
    """OllamaError is a subclass of Exception."""
    assert issubclass(OllamaError, Exception)


def test_ollama_connection_error_is_subclass_of_ollama_error() -> None:
    """OllamaConnectionError is a subclass of OllamaError."""
    assert issubclass(OllamaConnectionError, OllamaError)


def test_ollama_request_error_is_subclass_of_ollama_error() -> None:
    """OllamaRequestError is a subclass of OllamaError."""
    assert issubclass(OllamaRequestError, OllamaError)


def test_ollama_timeout_error_is_subclass_of_ollama_error() -> None:
    """OllamaTimeoutError is a subclass of OllamaError."""
    assert issubclass(OllamaTimeoutError, OllamaError)


def test_ollama_connection_error_not_direct_subclass_of_exception() -> None:
    """OllamaConnectionError is NOT a direct subclass of Exception."""
    assert Exception not in OllamaConnectionError.__bases__


def test_ollama_request_error_not_direct_subclass_of_exception() -> None:
    """OllamaRequestError is NOT a direct subclass of Exception."""
    assert Exception not in OllamaRequestError.__bases__


def test_ollama_timeout_error_not_direct_subclass_of_exception() -> None:
    """OllamaTimeoutError is NOT a direct subclass of Exception."""
    assert Exception not in OllamaTimeoutError.__bases__


# ---------------------------------------------------------------------------
# Attribute tests
# ---------------------------------------------------------------------------


def test_ollama_request_error_stores_status_code_and_body() -> None:
    """OllamaRequestError stores status_code and body attributes."""
    exc = OllamaRequestError("bad request", status_code=400, body="Bad Request")
    assert exc.status_code == 400
    assert exc.body == "Bad Request"


def test_ollama_request_error_message_accessible() -> None:
    """OllamaRequestError message is accessible via .message and str()."""
    exc = OllamaRequestError("server error", status_code=500, body="oops")
    assert exc.message == "server error"
    assert "server error" in str(exc)


def test_ollama_connection_error_message_accessible() -> None:
    """OllamaConnectionError message is accessible via .message and str()."""
    exc = OllamaConnectionError("cannot connect")
    assert exc.message == "cannot connect"
    assert "cannot connect" in str(exc)


def test_ollama_timeout_error_message_accessible() -> None:
    """OllamaTimeoutError message is accessible via .message and str()."""
    exc = OllamaTimeoutError("timed out after 120s")
    assert exc.message == "timed out after 120s"
    assert "timed out after 120s" in str(exc)


# ---------------------------------------------------------------------------
# Raise / catch tests
# ---------------------------------------------------------------------------


def test_can_catch_connection_error_as_ollama_error() -> None:
    """OllamaConnectionError can be caught as OllamaError."""
    with pytest.raises(OllamaError):
        raise OllamaConnectionError("unreachable")


def test_can_catch_request_error_as_ollama_error() -> None:
    """OllamaRequestError can be caught as OllamaError."""
    with pytest.raises(OllamaError):
        raise OllamaRequestError("bad", status_code=422, body="unprocessable")


def test_can_catch_timeout_error_as_ollama_error() -> None:
    """OllamaTimeoutError can be caught as OllamaError."""
    with pytest.raises(OllamaError):
        raise OllamaTimeoutError("timeout")


def test_can_catch_all_as_exception() -> None:
    """All OllamaError subclasses can be caught as Exception."""
    for exc_cls, kwargs in [
        (OllamaConnectionError, {"message": "conn"}),
        (OllamaTimeoutError, {"message": "timeout"}),
        (OllamaRequestError, {"message": "req", "status_code": 503, "body": "err"}),
    ]:
        with pytest.raises(Exception):  # noqa: B017
            if exc_cls is OllamaRequestError:
                raise OllamaRequestError(
                    kwargs["message"],
                    status_code=kwargs["status_code"],  # type: ignore[arg-type]
                    body=kwargs["body"],  # type: ignore[arg-type]
                )
            else:
                raise exc_cls(kwargs["message"])  # type: ignore[call-arg]

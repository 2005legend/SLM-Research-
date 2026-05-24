"""Tests for the fixture calculator module."""

from __future__ import annotations

from tests.integration.fixture_repo.calculator import add, multiply, subtract


def test_add() -> None:
    """add() returns the correct sum."""
    assert add(2, 3) == 5


def test_subtract() -> None:
    """subtract() returns the correct difference."""
    assert subtract(5, 3) == 2


def test_multiply() -> None:
    """multiply() returns the correct product."""
    assert multiply(3, 4) == 12

"""Tests for the calculator module."""

from calculator import add, multiply, subtract


def test_add() -> None:
    """Test add function."""
    assert add(2, 3) == 5


def test_subtract() -> None:
    """Test subtract function."""
    assert subtract(5, 3) == 2


def test_multiply() -> None:
    """Test multiply function."""
    assert multiply(3, 4) == 12

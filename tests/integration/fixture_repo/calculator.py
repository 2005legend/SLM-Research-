"""Simple calculator module used as a fixture repository for integration tests."""

from __future__ import annotations


def add(a: int, b: int) -> int:
    """Return the sum of *a* and *b*.

    Args:
        a: First operand.
        b: Second operand.

    Returns:
        The integer sum.
    """
    return a + b


def subtract(a: int, b: int) -> int:
    """Return *a* minus *b*.

    Args:
        a: First operand.
        b: Second operand.

    Returns:
        The integer difference.
    """
    return a - b


def multiply(a: int, b: int) -> int:
    """Return the product of *a* and *b*.

    Args:
        a: First operand.
        b: Second operand.

    Returns:
        The integer product.
    """
    return a * b

"""Tests that pass after the divide-by-zero fix is applied."""

from simple_api.core import divide


def test_divide_normal_case() -> None:
    """divide() returns the quotient for non-zero divisor."""
    assert divide(10.0, 2.0) == 5.0


def test_divide_by_zero_raises() -> None:
    """divide() raises ZeroDivisionError for zero divisor."""
    import pytest

    with pytest.raises(ZeroDivisionError):
        divide(1.0, 0.0)

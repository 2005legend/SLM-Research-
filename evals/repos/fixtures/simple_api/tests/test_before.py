"""Tests that fail before the divide-by-zero fix is applied."""

import pytest

from simple_api.core import divide


def test_divide_by_zero_should_raise() -> None:
    """divide() must raise ZeroDivisionError when b is zero."""
    with pytest.raises(ZeroDivisionError):
        divide(1.0, 0.0)

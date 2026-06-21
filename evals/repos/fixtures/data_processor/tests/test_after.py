"""Tests that pass after the empty-input fix is applied."""

import pytest

from data_processor.processor import average


def test_average_normal_case() -> None:
    """average() returns the mean of non-empty values."""
    assert average([1.0, 2.0, 3.0]) == 2.0


def test_average_empty_raises() -> None:
    """average() raises ValueError for empty input."""
    with pytest.raises(ValueError):
        average([])

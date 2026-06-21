"""Tests that fail before the empty-input fix is applied."""

import pytest

from data_processor.processor import average


def test_average_empty_list_should_raise() -> None:
    """average() must raise ValueError for an empty list."""
    with pytest.raises(ValueError):
        average([])

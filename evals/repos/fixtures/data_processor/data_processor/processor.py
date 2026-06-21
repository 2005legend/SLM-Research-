"""Data processing helpers with an intentional empty-input bug."""


def average(values: list[float]) -> float:
    """Return the arithmetic mean of *values*.

    Raises:
        ValueError: When *values* is empty.
    """
    return sum(values) / len(values)

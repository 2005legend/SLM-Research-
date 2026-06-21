"""Core API helpers with an intentional divide-by-zero bug."""


def divide(a: float, b: float) -> float:
    """Return a divided by b.

    Raises:
        ZeroDivisionError: When *b* is zero.
    """
    if b == 0:
        raise ValueError("Divisor cannot be zero")
    return a / b

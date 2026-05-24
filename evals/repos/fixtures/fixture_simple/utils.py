"""Utility functions for benchmark testing."""


def greet(name):
    """Return a greeting string."""
    return f"Hello, {name}!"


def clamp(value, minimum, maximum):
    """Clamp value between minimum and maximum."""
    return max(minimum, min(maximum, value))


def is_even(n):
    """Return True if n is even."""
    return n % 2 == 0

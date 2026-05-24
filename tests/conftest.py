"""Root pytest configuration for local-sage tests.

Provides the ``integration`` marker and a fixture that skips integration
tests unless the ``SAGE_INTEGRATION=true`` environment variable is set.
"""

from __future__ import annotations

import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register the ``integration`` marker to avoid PytestUnknownMarkWarning."""
    config.addinivalue_line(
        "markers",
        "integration: mark test as an integration test (skipped by default).",
    )


@pytest.fixture(autouse=False)
def require_integration() -> None:
    """Skip the test unless SAGE_INTEGRATION=true is set in the environment.

    Apply this fixture to any integration test that requires a real
    filesystem, real subprocess calls, or real network access.

    Example::

        def test_full_start(require_integration, tmp_path):
            ...
    """
    if os.environ.get("SAGE_INTEGRATION", "").lower() not in {"1", "true", "yes"}:
        pytest.skip("Set SAGE_INTEGRATION=true to run integration tests")

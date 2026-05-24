"""Integration tests for local-sage.

These tests require ``SAGE_INTEGRATION=true`` to be set in the environment.
They exercise real filesystem operations, real subprocess calls (pytest,
mypy, ruff), and the full agent loop with a mocked OllamaClient.
"""

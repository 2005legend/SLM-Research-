"""Entry point for the local-sage CLI.

Invoked by the ``sage`` console script defined in ``pyproject.toml``, or
directly via ``python -m local_sage``.
"""

from local_sage.cli import app


def main() -> None:
    """Launch the Typer CLI application.

    This is the sole entry point registered in ``pyproject.toml`` as
    ``sage = "local_sage.__main__:main"``.
    """
    app()


if __name__ == "__main__":
    main()

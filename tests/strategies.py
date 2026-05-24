"""Custom Hypothesis strategies for local-sage property-based tests.

Provides reusable generators for domain types used across the test suite.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from hypothesis import strategies as st

from local_sage.repo_graph.graph import SymbolInfo


def symbol_info_strategy() -> st.SearchStrategy[SymbolInfo]:
    """Generate arbitrary SymbolInfo instances with internally consistent fields.

    Returns:
        A Hypothesis strategy that produces valid SymbolInfo dataclass instances.
        start_byte <= end_byte and start_line <= end_line are guaranteed.
    """
    kind_strategy: st.SearchStrategy[Literal["function", "class", "import"]] = st.sampled_from(
        ["function", "class", "import"]
    )

    # Build a relative file path like "pkg/module.py"
    path_strategy = st.builds(
        lambda parts: Path("/".join(parts) + ".py"),
        st.lists(
            st.from_regex(r"[a-z][a-z0-9_]{0,8}", fullmatch=True),
            min_size=1,
            max_size=3,
        ),
    )

    @st.composite
    def _build(draw: st.DrawFn) -> SymbolInfo:
        name = draw(st.from_regex(r"[a-zA-Z_][a-zA-Z0-9_]{0,30}", fullmatch=True))
        kind = draw(kind_strategy)
        file_path = draw(path_strategy)
        start_byte = draw(st.integers(min_value=0, max_value=10_000))
        end_byte = draw(st.integers(min_value=start_byte, max_value=start_byte + 5_000))
        start_line = draw(st.integers(min_value=1, max_value=1_000))
        end_line = draw(st.integers(min_value=start_line, max_value=start_line + 200))
        source = draw(st.text(min_size=0, max_size=200))
        return SymbolInfo(
            name=name,
            kind=kind,
            file_path=file_path,
            start_byte=start_byte,
            end_byte=end_byte,
            start_line=start_line,
            end_line=end_line,
            source=source,
        )

    return _build()


def python_source_strategy() -> st.SearchStrategy[str]:
    """Generate syntactically valid Python source strings from fixed templates.

    Uses a small set of templates (function defs, class defs, assignments) to
    guarantee syntactic validity without attempting arbitrary Python generation.

    Returns:
        A Hypothesis strategy that produces valid Python source strings.
    """
    name_st = st.from_regex(r"[a-z][a-z0-9_]{0,15}", fullmatch=True)
    value_st = st.one_of(
        st.integers().map(str),
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10).map(
            lambda s: f'"{s}"'
        ),
    )

    func_template = st.builds(
        lambda name, arg, val: f"def {name}({arg}):\n    return {val}\n",
        name=name_st,
        arg=name_st,
        val=value_st,
    )
    class_template = st.builds(
        lambda cls_name, method_name: (
            f"class {cls_name}:\n    def {method_name}(self) -> None:\n        pass\n"
        ),
        cls_name=st.from_regex(r"[A-Z][a-zA-Z0-9]{0,15}", fullmatch=True),
        method_name=name_st,
    )
    assign_template = st.builds(
        lambda name, val: f"{name} = {val}\n",
        name=name_st,
        val=value_st,
    )

    return st.one_of(func_template, class_template, assign_template)


def patch_strategy() -> st.SearchStrategy[str]:
    """Generate unified diff patch strings using a fixed template.

    The generated patches follow the standard unified diff format:
    ``--- a/file\\n+++ b/file\\n@@ -L,1 +L,1 @@\\n-old\\n+new\\n``

    Returns:
        A Hypothesis strategy that produces unified diff strings.
    """
    filename_st = st.from_regex(r"[a-z][a-z0-9_]{0,15}\.py", fullmatch=True)
    line_no_st = st.integers(min_value=1, max_value=9_999)
    content_st = st.from_regex(r"[a-zA-Z0-9_= ]{1,40}", fullmatch=True)

    return st.builds(
        lambda fname, lineno, old, new: (
            f"--- a/{fname}\n+++ b/{fname}\n@@ -{lineno},1 +{lineno},1 @@\n-{old}\n+{new}\n"
        ),
        fname=filename_st,
        lineno=line_no_st,
        old=content_st,
        new=content_st,
    )


def http_status_strategy() -> st.SearchStrategy[int]:
    """Generate HTTP error status codes in the range 400–599 inclusive.

    Returns:
        A Hypothesis strategy that produces integers between 400 and 599.
    """
    return st.integers(min_value=400, max_value=599)


def ollama_response_strategy() -> st.SearchStrategy[dict]:
    """Generate valid Ollama /api/generate response dicts.

    The generated dicts contain all fields consumed by OllamaClient._parse_response():
    ``response``, ``eval_count``, ``prompt_eval_count``, ``done_reason``,
    and ``total_duration``.

    Returns:
        A Hypothesis strategy that produces Ollama API response dictionaries.
    """
    return st.fixed_dictionaries(
        {
            "response": st.text(min_size=0, max_size=500),
            "eval_count": st.integers(min_value=0, max_value=100_000),
            "prompt_eval_count": st.integers(min_value=0, max_value=100_000),
            "done_reason": st.sampled_from(["stop", "length", "error"]),
            "total_duration": st.integers(min_value=0, max_value=10**12),
        }
    )

# Changelog

## [Unreleased] — 2026-06-02

### Summary
Full setup, bug-fix, and validation pass on a fresh Python 3.14.5 environment.
All 276 unit tests now pass. The CLI is fully operational end-to-end.

---

### New

#### `local_sage/wiki/` — module created from scratch
The entire wiki layer was missing from the repository. All orchestration,
CLI, and test code referenced it but it did not exist, causing
`ModuleNotFoundError` on every import.

Added:
- `local_sage/wiki/__init__.py` — re-exports `WikiEntry` and `WikiManager`
- `local_sage/wiki/manager.py` — `WikiEntry` dataclass + `WikiManager` with
  `write_entry`, `read_entry`, `list_entries`, and `search_entries`
- `local_sage/wiki/exceptions.py` — `WikiError` (domain base), `WikiReadError`,
  `WikiWriteError` with `entry_title`, `file_path`, `os_error` keyword args

---

### Fixed

#### `pyproject.toml`
- Build backend changed from `setuptools.backends.legacy:build` (does not
  exist in setuptools 68+) to `setuptools.build_meta`.
- `typer==0.12.*` bumped to `typer>=0.13`. Typer 0.12.5 + Click 8.4.1 +
  Python 3.14 causes `Path`-typed CLI options to be treated as boolean flags
  ("Got unexpected extra argument"), breaking the `validate` and `benchmark`
  commands entirely.

#### `local_sage/cli.py`
- Removed `from __future__ import annotations`. With PEP 563 active, Typer
  cannot evaluate stringified annotations at runtime, causing option-type
  misdetection.
- Moved `ValidationRunner` import to module top level so
  `local_sage.cli.ValidationRunner` is a stable mock target in tests.
- Changed `validate` and `benchmark` `Path`-typed options to `str` with
  explicit `Path()` conversion inside the function body — more robust across
  Typer/Click version combinations.
- Added `SageConfig` to top-level imports; removed redundant local imports of
  `SageConfig` inside `_get_index_info` and `_get_session_info`.

#### `local_sage/repo_graph/__init__.py`
- `RepoIndexer` and `ContextSelector` were listed in `__all__` but never
  imported, causing `ImportError` on `from local_sage.repo_graph import
  RepoIndexer`. Added the two missing imports.

#### `local_sage/orchestration/__init__.py`
- `build_graph` was listed in `__all__` but never imported. Added import.

#### `local_sage/validation/patcher.py`
- **Null header guard** — added `if diff.header is None: continue` before
  accessing `diff.header.new_path`, preventing `AttributeError` on patches
  with unparseable headers (e.g. patches written via PowerShell `Out-File`
  which prepends a BOM or blank line).
- **Quoted type annotation** — `diff: "whatthepatch.patch.diffobj"` changed
  to unquoted (ruff UP037).
- **`lstrip` bug** — `raw_path.lstrip("ab/")` treated `"ab/"` as a character
  set, corrupting paths like `"bar.py"` → `"ar.py"`. Changed to
  `raw_path.removeprefix("a/").removeprefix("b/")`.
- **Path resolution fallback** — added `_find_file_in_tree()` helper. When
  the model generates patch paths prefixed with the repo folder name (e.g.
  `SLM-Research--main/local_sage/config.py`), the direct `target_dir / path`
  join fails. The helper strips leading components one at a time until it
  finds a match inside the temp directory.
- **Ruff formatting** — auto-formatted `contracts.py` and `runner.py` to
  satisfy `ruff format` check (was blocking every agent validation run).

#### `tests/test_cli.py`
- Fixed mock target for `ValidationRunner` from
  `"local_sage.validation.runner.ValidationRunner"` to
  `"local_sage.cli.ValidationRunner"` in all four `TestValidateCommand` tests
  and the Property 1 hypothesis test. Since `ValidationRunner` is now imported
  at the top of `cli.py`, patching the runner module has no effect on calls
  made through the CLI module's namespace.

---

### Known issue (open)
`sage task` — the agent loop runs end-to-end but the model (`qwen2.5-coder:7b`)
occasionally generates patch paths prefixed with the repo folder name
(e.g. `SLM-Research--main/local_sage/config.py` instead of
`local_sage/config.py`). The `_find_file_in_tree` fallback handles this at
the patcher level. However when the model generates a syntactically valid but
semantically empty patch, validation still fails (ruff FORMAT on the temp
copy). This is a model output quality issue, not a code bug — the retry loop
handles it up to `max_retries` (default 3).

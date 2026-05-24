# Implementation Tasks — local-sage

## Project Setup

- [x] 1. Initialize project structure and configuration
  - [x] 1.1 Create `pyproject.toml` with all dependencies (langgraph>=0.3,<0.4, tree-sitter==0.23.x, networkx==3.3, mem0ai==0.1.x, rich==13.x, typer==0.12.x, httpx==0.27.x, sentence-transformers==3.x, qdrant-client>=1.9,<2.0, whatthepatch>=1.0.4)
  - [x] 1.2 Create package structure: `local_sage/` with subdirectories for model/, orchestration/, repo_graph/, memory/, wiki/, validation/
  - [x] 1.3 Create `tests/` directory mirroring `local_sage/` structure
  - [x] 1.4 Create `local_sage/__init__.py` and layer-specific `__init__.py` files
  - [x] 1.5 Create `README.md` with project overview and setup instructions
  - [x] 1.6 Create `local_sage/config.py` with SageConfig dataclass
  - [x] 1.7 Implement config loading from environment variables and sage.toml

## Test Infrastructure

- [x] 2. Create Hypothesis strategies
  - [x] 2.1 Create `tests/strategies.py` with custom Hypothesis strategies
  - [x] 2.2 Implement symbol_info_strategy()
  - [x] 2.3 Implement python_source_strategy()
  - [x] 2.4 Implement patch_strategy()
  - [x] 2.5 Implement http_status_strategy()
  - [x] 2.6 Implement ollama_response_strategy()

## Layer 1 — Model (OllamaClient)

- [x] 3. Implement OllamaClient and exception hierarchy
  - [x] 3.1 Create `local_sage/model/exceptions.py` with OllamaError, OllamaConnectionError, OllamaRequestError, OllamaTimeoutError
  - [x] 3.2 Create `local_sage/model/client.py` with ModelResponse dataclass and OllamaClient class
  - [x] 3.3 Implement `OllamaClient.generate()` async method with httpx, targeting localhost:11434
  - [x] 3.4 Implement `OllamaClient.health_check()` async method
  - [x] 3.5 Implement `OllamaClient._parse_response()` to convert Ollama JSON to ModelResponse
  - [x] 3.6 Add error handling for connection errors, HTTP errors, and timeouts

- [x] 4. Write tests for Layer 1 (Model)
- [ ] 4. Write tests for Layer 1 (Model)
  - [x] 4.1 Create `tests/model/test_client.py` with unit tests for OllamaClient
  - [x] 4.2 Write property test for Property 3: OllamaClient only sends requests to localhost:11434
  - [x] 4.3 Write property test for Property 4: ModelResponse round-trip from Ollama API response
  - [x] 4.4 Write property test for Property 5: OllamaRequestError preserves HTTP status code
  - [x] 4.5 Write property test for Property 6: OllamaClient always uses correct model name
  - [x] 4.6 Create `tests/model/test_exceptions.py` with exception hierarchy tests

## Layer 3 — Repo Graph (tree-sitter + NetworkX)

- [-] 5. Implement SymbolGraph and SymbolInfo
- [ ] 5. Implement SymbolGraph and SymbolInfo
  - [x] 5.1 Create `local_sage/repo_graph/graph.py` with SymbolInfo dataclass
  - [x] 5.2 Implement SymbolGraph class with NetworkX DiGraph backend
  - [x] 5.3 Implement `SymbolGraph.add_symbol()`, `add_edge()`, `get_symbol()`, `neighbors()`
  - [x] 5.4 Implement `SymbolGraph.to_dict()` and `from_dict()` for serialization
  - [x] 5.5 Create `local_sage/repo_graph/exceptions.py` with RepoGraphError, IndexLoadError, ParseError

- [x] 6. Implement RepoIndexer with tree-sitter
  - [x] 6.1 Create `local_sage/repo_graph/indexer.py` with RepoIndexer class
  - [x] 6.2 Implement `RepoIndexer.index_repo()` to walk directory and parse .py files
  - [x] 6.3 Implement tree-sitter queries for function_definition, class_definition, import_statement, call nodes
  - [x] 6.4 Implement `RepoIndexer.update_file()` for incremental updates
  - [x] 6.5 Implement `RepoIndexer.save_index()` to persist to .sage/index.json
  - [x] 6.6 Implement `RepoIndexer.load_index()` to load from cache with mtime checking
  - [x] 6.7 Add error handling for syntax errors (log and skip file)

- [x] 7. Implement ContextSelector with Personalized PageRank
  - [x] 7.1 Create `local_sage/repo_graph/selector.py` with ContextSelector class
  - [x] 7.2 Implement `ContextSelector._compute_personalization()` to match task tokens against symbols
  - [x] 7.3 Implement `ContextSelector.select()` using nx.pagerank with personalization vector
  - [x] 7.4 Add recency boost for recently modified symbols
  - [x] 7.5 Implement top-K selection and return SymbolInfo list

- [x] 8. Implement ImpactAnalyzer
  - [x] 8.1 Create `local_sage/repo_graph/impact.py` with ImpactReport dataclass and ImpactAnalyzer class
  - [x] 8.2 Implement patch parsing to extract modified symbol names
  - [x] 8.3 Implement reverse BFS on SymbolGraph to find transitive callers
  - [x] 8.4 Return ImpactReport with directly_modified, transitively_affected, affected_files

- [x] 9. Write tests for Layer 3 (Repo Graph)
  - [x] 9.1 Create `tests/repo_graph/test_graph.py` with SymbolGraph unit tests
  - [x] 9.2 Write property test for Property 8: SymbolGraph correctly classifies symbol kinds
  - [x] 9.3 Write property test for Property 9: SymbolGraph index round-trip (save → load)
  - [x] 9.4 Create `tests/repo_graph/test_indexer.py` with RepoIndexer unit tests
  - [x] 9.5 Write property test for Property 7: RepoIndexer covers all .py files
  - [x] 9.6 Write property test for Property 10: Incremental update does not affect unmodified files
  - [x] 9.7 Write property test for Property 13: RepoIndexer skips syntax-error files without raising
  - [x] 9.8 Create `tests/repo_graph/test_selector.py` with ContextSelector unit tests
  - [x] 9.9 Write property test for Property 11: ContextSelector returns at most top-K results
  - [x] 9.10 Create `tests/repo_graph/test_impact.py` with ImpactAnalyzer unit tests
  - [x] 9.11 Write property test for Property 12: ImpactAnalyzer includes transitive callers

## Layer 4 — Session Memory (SQLite + Mem0)

- [x] 10. Implement SessionManager with SQLite
- [ ] 10. Implement SessionManager with SQLite
  - [x] 10.1 Create `local_sage/memory/exceptions.py` with SessionError, DatabaseCorruptError, SessionNotFoundError
  - [x] 10.2 Create `local_sage/memory/schema.sql` with all table definitions
  - [x] 10.3 Create `local_sage/memory/session.py` with Session and SessionSummary dataclasses
  - [x] 10.4 Implement SessionManager class with sqlite3 connection management
  - [x] 10.5 Implement `SessionManager.create_session()` to generate session_id and insert into DB
  - [x] 10.6 Implement `SessionManager.load_latest_session()` to query most recent session
  - [x] 10.7 Implement `SessionManager.record_task()` to insert into file_changes and test_results tables
  - [x] 10.8 Implement `SessionManager.record_observation()` for decisions and todos tables
  - [x] 10.9 Implement `SessionManager.get_session_summary()` to aggregate session data
  - [x] 10.10 Add error handling for missing/corrupt database (rename to .corrupt, create new)

- [x] 11. Implement SemanticMemory with Mem0
  - [x] 11.1 Create `local_sage/memory/semantic.py` with MEM0_CONFIG dict
  - [x] 11.2 Configure Mem0 with embedder.provider="huggingface", model="multi-qa-MiniLM-L6-cos-v1"
  - [x] 11.3 Configure Mem0 with llm.provider="ollama", ollama_base_url="http://localhost:11434"
  - [x] 11.4 Configure Mem0 with vector_store.provider="qdrant", path=".sage/vectors"
  - [x] 11.5 Implement SemanticMemory class with repo_root-based user_id generation
  - [x] 11.6 Implement `SemanticMemory.add_observation()` method
  - [x] 11.7 Implement `SemanticMemory.search()` method with top_k parameter

- [x] 12. Write tests for Layer 4 (Session Memory)
  - [x] 12.1 Create `tests/memory/test_session.py` with SessionManager unit tests
  - [x] 12.2 Write property test for Property 14: Session task persistence round-trip
  - [x] 12.3 Add unit tests for database corruption recovery
  - [x] 12.4 Create `tests/memory/test_semantic.py` with SemanticMemory unit tests
  - [x] 12.5 Write property test for Property 15: Semantic memory add-then-search round-trip (with localhost:11434 verification)

## Layer 5 — Wiki (Markdown files)

- [x] 13. Implement WikiManager
- [ ] 13. Implement WikiManager
  - [x] 13.1 Create `local_sage/wiki/exceptions.py` with WikiError and WikiReadError
  - [x] 13.2 Create `local_sage/wiki/manager.py` with WikiEntry dataclass
  - [x] 13.3 Implement WikiManager class with wiki_dir Path initialization
  - [x] 13.4 Implement `WikiManager.write_entry()` to create/update markdown files with slug naming
  - [x] 13.5 Implement `WikiManager.read_entry()` to load markdown content
  - [x] 13.6 Implement `WikiManager.list_entries()` to return all entries with last_modified timestamps
  - [x] 13.7 Implement `WikiManager.search_entries()` with token overlap matching
  - [x] 13.8 Add error handling for filesystem errors (raise WikiReadError)

- [x] 14. Write tests for Layer 5 (Wiki)
  - [x] 14.1 Create `tests/wiki/test_manager.py` with WikiManager unit tests
  - [x] 14.2 Write property test for Property 16: Wiki entry round-trip (write → read)
  - [x] 14.3 Write property test for Property 17: Wiki search returns entries containing query keywords
  - [x] 14.4 Write property test for Property 18: Wiki list completeness
  - [x] 14.5 Add unit tests for WikiReadError on filesystem failures

## Layer 6 — Validation (pytest + mypy + ruff + contracts)

- [x] 15. Implement ValidationResult and related dataclasses
- [ ] 15. Implement ValidationResult and related dataclasses
  - [x] 15.1 Create `local_sage/validation/exceptions.py` with ValidationError, ValidationTimeoutError, ContractParseError
  - [x] 15.2 Create `local_sage/validation/result.py` with ValidationResult, PytestCounts, MypyError, RuffViolation, ContractFailure dataclasses
  - [x] 15.3 Implement `ValidationResult.to_retry_prompt()` method to format failures for code generator

- [x] 16. Implement Patcher with whatthepatch
  - [x] 16.1 Create `local_sage/validation/patcher.py` with Patcher class
  - [x] 16.2 Implement `Patcher.apply_to_temp()` using shutil.copytree and whatthepatch
  - [x] 16.3 Implement `Patcher.apply_to_repo()` to apply patch to real repository
  - [x] 16.4 Implement `Patcher.revert()` to clean up temp directory with finally block guarantee

- [x] 17. Implement subprocess-based validators
  - [x] 17.1 Create `local_sage/validation/pytest_runner.py` with PytestRunner class
  - [x] 17.2 Implement `PytestRunner.run()` with subprocess call to pytest --json-report
  - [x] 17.3 Parse JSON report and return PytestCounts
  - [x] 17.4 Create `local_sage/validation/mypy_runner.py` with MypyRunner class
  - [x] 17.5 Implement `MypyRunner.run()` with subprocess call to mypy --show-column-numbers
  - [x] 17.6 Parse stdout lines and return list of MypyError objects
  - [x] 17.7 Create `local_sage/validation/ruff_runner.py` with RuffRunner class
  - [x] 17.8 Implement `RuffRunner.run()` with subprocess calls to ruff check and ruff format --check
  - [x] 17.9 Parse JSON output and return list of RuffViolation objects
  - [x] 17.10 Add timeout handling for all subprocess calls (raise ValidationTimeoutError)

- [x] 18. Implement ContractChecker (REQUIRES MANUAL REVIEW)
  - [x] 18.1 Create `local_sage/validation/contracts.py` with Contract dataclass
  - [x] 18.2 Implement `ContractChecker.load_contracts()` to parse YAML files from contracts/ directory
  - [x] 18.3 Add YAML parsing error handling (raise ContractParseError)
  - [x] 18.4 Implement `ContractChecker.check()` for exception_types validation using ast.parse and AST walking
  - [x] 18.5 Implement return_shape validation using typing.get_type_hints()
  - [x] 18.6 Log preconditions as informational (documentation only in v1)
  - [x] 18.7 Return list of ContractFailure objects for violations
  - [x] 18.8 Create contracts/ directory with working YAML contract files for OllamaClient.generate() and ValidationRunner.validate_and_apply() as test fixtures

- [x] 19. Implement ValidationRunner orchestrator
  - [x] 19.1 Create `local_sage/validation/runner.py` with ValidationRunner class
  - [x] 19.2 Implement `ValidationRunner.__init__()` with configurable timeouts and manual_review flag
  - [x] 19.3 Implement `ValidationRunner._run_all_checks()` to call all four validators on temp_dir
  - [x] 19.4 Collect results from all four validators regardless of individual failures. Only skip a validator if the previous one raised ValidationTimeoutError, not a normal failure
  - [x] 19.5 Implement `ValidationRunner._prompt_manual_review()` for user confirmation
  - [x] 19.6 Implement `ValidationRunner.validate_and_apply()` to run checks, prompt if needed, and apply patch
  - [x] 19.7 Implement `ValidationRunner.validate_only()` to run checks without applying
  - [x] 19.8 Ensure temp directory cleanup in finally block

- [x] 20. Write tests for Layer 6 (Validation) — REQUIRES MANUAL REVIEW
- [ ] 20. Write tests for Layer 6 (Validation) — REQUIRES MANUAL REVIEW
  - [x] 20.1 Create `tests/validation/test_result.py` with ValidationResult unit tests
  - [x] 20.2 Create `tests/validation/test_patcher.py` with Patcher unit tests
  - [x] 20.3 Create `tests/validation/test_pytest_runner.py` with PytestRunner unit tests
  - [x] 20.4 Write property test for Property 20 (pytest portion): Validator output parsing round-trip
  - [x] 20.5 Create `tests/validation/test_mypy_runner.py` with MypyRunner unit tests
  - [x] 20.6 Write property test for Property 20 (mypy portion): Validator output parsing round-trip
  - [x] 20.7 Create `tests/validation/test_ruff_runner.py` with RuffRunner unit tests
  - [x] 20.8 Write property test for Property 20 (ruff portion): Validator output parsing round-trip
  - [x] 20.9 Create `tests/validation/test_contracts.py` with ContractChecker unit tests
  - [x] 20.10 Write property test for Property 22: ContractChecker detects exception type violations
  - [x] 20.11 Create `tests/validation/test_runner.py` with ValidationRunner unit tests
  - [x] 20.12 Write property test for Property 19: All four validators are called before patch application
  - [x] 20.13 Write property test for Property 21: ValidationTimeoutError identifies the timed-out tool
  - [x] 20.14 Write property test for Property 23: Manual review gate prevents patch application without confirmation

## Layer 2 — Orchestration (LangGraph)

- [x] 21. Implement AgentState
  - [x] 21.1 Create `local_sage/orchestration/state.py` with AgentState dataclass
  - [x] 21.2 Import SymbolInfo, WikiEntry, ValidationResult into AgentState

- [x] 22. Implement LangGraph nodes
- [ ] 22. Implement LangGraph nodes
  - [x] 22.1 Create `local_sage/orchestration/nodes.py` with all node functions
  - [x] 22.2 Implement `planner_node()` to generate plan from task
  - [x] 22.3 Implement `context_retriever_node()` to call ContextSelector and WikiManager
  - [x] 22.4 Implement `code_generator_node()` to call OllamaClient with context and retry diagnostics
  - [x] 22.5 Implement `validator_node()` to call ValidationRunner
  - [x] 22.6 Implement `memory_writer_node()` to call SessionManager and WikiManager

- [x] 23. Implement LangGraph StateGraph
  - [x] 23.1 Create `local_sage/orchestration/graph.py` with build_graph() function
  - [x] 23.2 Add all five nodes to StateGraph
  - [x] 23.3 Add edges: planner → context_retriever → code_generator → validator
  - [x] 23.4 Implement `route_after_validation()` conditional edge function
  - [x] 23.5 Add conditional edge from validator to code_generator (retry) or memory_writer (success) or END (max retries)
  - [x] 23.6 Add edge from memory_writer to END
  - [x] 23.7 Compile and return CompiledGraph

- [x] 24. Implement LangGraph tools
  - [x] 24.1 Create `local_sage/orchestration/tools.py` with @tool decorators
  - [x] 24.2 Implement read_file tool
  - [x] 24.3 Implement write_wiki tool
  - [x] 24.4 Implement run_tests tool

- [x] 25. Write tests for Layer 2 (Orchestration)
  - [x] 25.1 Create `tests/orchestration/test_state.py` with AgentState unit tests
  - [x] 25.2 Create `tests/orchestration/test_nodes.py` with node function unit tests
  - [x] 25.3 Create `tests/orchestration/test_graph.py` with StateGraph unit tests
  - [x] 25.4 Write property test for Property 24: Agent node execution order
  - [x] 25.5 Write property test for Property 25: Retry loop calls code_generator once per failure
  - [x] 25.6 Write property test for Property 26: Max retries exhausted → no patch applied
  - [x] 25.7 Write property test for Property 27: memory_writer updates both SessionManager and WikiManager
  - [x] 25.8 Create `tests/orchestration/test_tools.py` with tool unit tests

## Layer 0 — CLI (Typer + Rich)

- [x] 26. Implement CLI subcommands
- [ ] 26. Implement CLI subcommands
  - [x] 26.1 Create `local_sage/__main__.py` with main() entry point
  - [x] 26.2 Create `local_sage/cli.py` with Typer app
  - [x] 26.3 Implement `sage start` command to boot agent, index repo, load session
  - [x] 26.4 Implement `sage task` command to run full agent loop with Rich progress display
  - [x] 26.5 Implement `sage validate` command to run ValidationRunner.validate_only()
  - [x] 26.6 Implement `sage benchmark` command for eval suite
  - [x] 26.7 Implement `sage memory show` command with Rich table formatting
  - [x] 26.8 Implement `sage wiki list` command with Rich formatting
  - [x] 26.9 Implement `sage wiki show` command to display entry content
  - [x] 26.10 Implement `sage status` command with Rich Panel showing model/repo/session status

- [x] 27. Write tests for Layer 0 (CLI)
  - [x] 27.1 Create `tests/test_cli.py` with CLI command unit tests
  - [x] 27.2 Write property test for Property 1: Validate-only mode never modifies the repository
  - [x] 27.3 Write property test for Property 2: Unrecognized subcommands exit with non-zero status

## Code Quality and Property Tests

- [x] 28. Implement code quality verification tests
  - [x] 28.1 Create `tests/test_code_quality.py` with introspection-based tests
  - [x] 28.2 Write test for Property 28: All public functions have complete type annotations
  - [x] 28.3 Write test for Property 29: All public classes and methods have docstrings
  - [x] 28.4 Write test for Property 30: All file I/O uses pathlib.Path
  - [x] 28.5 Write test for Property 31: All custom exceptions subclass a domain-specific base
  - [x] 28.6 Write test for Property 32: All functions are 40 lines or fewer

## Integration and End-to-End Testing

- [x] 29. Create integration test suite
  - [x] 29.1 Create `tests/integration/` directory and `tests/conftest.py` with pytest fixture that skips integration tests unless SAGE_INTEGRATION=true env var is set
  - [x] 29.2 Create fixture repository for testing
  - [x] 29.3 Write integration test for full sage start on fixture repo (requires --run-integration flag and SAGE_INTEGRATION=true, mocks OllamaClient)
  - [x] 29.4 Write integration test for full sage task with mocked OllamaClient (requires --run-integration flag and SAGE_INTEGRATION=true)
  - [x] 29.5 Write integration test for ValidationRunner end-to-end with real pytest/mypy/ruff (requires --run-integration flag and SAGE_INTEGRATION=true)
  - [x] 29.6 Write integration test for memory_writer calling both SessionManager and WikiManager (requires --run-integration flag and SAGE_INTEGRATION=true)

## Documentation and Packaging

- [x] 30. Complete documentation
  - [x] 30.1 Write comprehensive README.md with installation, usage, and examples
  - [x] 30.2 Add docstrings to all public classes and methods (Google style)
  - [x] 30.3 Create CONTRIBUTING.md with development setup instructions
  - [x] 30.4 Document Mem0 configuration requirements (HuggingFace embedder, no OpenAI)

- [x] 31. Verify packaging and installation
  - [x] 31.1 Verify pyproject.toml has all required fields and dependencies
  - [x] 31.2 Test pip install in clean virtual environment
  - [x] 31.3 Verify sage command is available after installation
  - [x] 31.4 Run full test suite with pytest
  - [x] 31.5 Run mypy in strict mode on entire codebase
  - [x] 31.6 Run ruff check and ruff format on entire codebase
  - [x] 31.7 Verify pytest-cov reports ≥90% line coverage

## Performance and Benchmarking

- [x] 32. Implement and run benchmarks
  - [x] 32.1 Create benchmark suite structure: evals/tasks/ (task YAML files with id, category, description, repo, expected_files_changed, pass_condition), evals/repos/fixtures/ (small Python repos), evals/runner.py (runs all tasks, measures pass rate per category). Categories: contract_violation, edge_case, multi_file, context_drift
  - [x] 32.2 Verify sage start completes within 30 seconds on warm repo
  - [x] 32.3 Verify ValidationRunner completes within 60 seconds per attempt
  - [x] 32.4 Verify cold repo indexing completes within 120 seconds for 100k LOC
  - [x] 32.5 Verify memory usage stays within 8GB VRAM and 16GB system RAM
  - [x] 32.6 Measure and document pass rate on benchmark suite (target >60%)

---

## Notes

- **Validation layer (Tasks 15-20) requires manual review before marking complete**
- All property tests use Hypothesis with @settings(max_examples=100)
- Each property test includes a comment referencing the design property number
- All file I/O must use pathlib.Path
- All functions must be ≤40 lines
- All public functions must have type hints and docstrings
- Patcher must use whatthepatch, not system patch utility
- Mem0 must use embedder.provider="huggingface", never OpenAI
- LangGraph version must be >=0.3,<0.4
- Integration tests require --run-integration flag and SAGE_INTEGRATION=true env var

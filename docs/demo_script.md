# local-sage Demo Recording Script

This guide walks through recording a terminal demo of local-sage using [asciinema](https://asciinema.org/).

## Prerequisites

- Ollama running with `qwen2.5-coder:7b` pulled
- local-sage installed: `pip install -e ".[dev]"`
- asciinema installed: `pip install asciinema`

## Recording Steps

### 1. Start Ollama

```bash
ollama serve
```

In a separate terminal, verify the model is available:

```bash
ollama list
```

### 2. Initialise the agent

```bash
cd /path/to/your/project
sage start
```

Observe the repo index being built and a session being created.

### 3. Run a representative task

```bash
sage task "fix the divide-by-zero bug in the calculator module"
```

Watch the orchestration loop:

- Planner generates steps
- Context retriever selects relevant symbols
- Code generator produces a unified diff
- Validator runs pytest, mypy, ruff, and contract checks
- On failure, the agent retries with diagnostic feedback
- On success, the patch is applied and recorded in session memory

### 4. Inspect session status

```bash
sage status
```

Note the token counts and estimated cost fields.

### 5. View session memory

```bash
sage memory show
```

## Recommended asciinema Command

```bash
asciinema rec \
  --title "local-sage demo" \
  --cols 120 \
  --rows 30 \
  local-sage-demo.cast
```

Recommended terminal dimensions: **120 columns × 30 rows**.

After recording, upload with:

```bash
asciinema upload local-sage-demo.cast
```

## What to Highlight

1. The validation loop rejecting a malformed patch and retrying
2. The final applied patch passing all four validators
3. Session memory recording the completed task with token counts

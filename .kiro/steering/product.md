# local-sage

A repo-aware coding agent that makes Qwen2.5 Coder 7B production-reliable, running fully on consumer hardware (RTX 3060 / 8GB VRAM).

## Core Thesis

Small local models fail in predictable, structural ways. local-sage catches those failures deterministically via a validation gate instead of relying on a bigger or smarter model.

## Target User

A developer who wants production-quality AI coding assistance without paying for cloud APIs or owning expensive hardware.

## Entry Point

CLI tool with Rich terminal UI. Users run `sage start`, point it at any Python repo, and interact via natural language commands. Every code change goes through the validation loop before being applied.

## Hardware Target

- GPU: RTX 3060 or equivalent, 8GB VRAM
- RAM: 16GB system RAM
- Storage: ~10GB for model + index

## Key Constraints

- No external API calls — only the localhost Ollama endpoint (localhost:11434)
- Validation layer is the core novel contribution — treat it with extra care
- Do not auto-accept generated code for the validation layer without a manual review flag

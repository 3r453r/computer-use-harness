# Computer-Use Harness

## Skills

This repo includes a skill for Claude Code at `skills/computer-use-harness/SKILL.md`.
Use it when starting, running, or debugging the harness.

## Quick Start

1. `python -m venv .venv && .venv\Scripts\activate && pip install -e .`
2. Copy `.env.example` to `.env` and set `OPENAI_API_KEY`
3. `computer-use-harness tools` to list tools
4. `computer-use-harness run "your task"` to run

## Key Conventions

- Python control plane at `src/computer_use_harness/`
- .NET sidecar at `dotnet-sidecar/LocalWindowsSidecar/`
- Set `AUTO_APPROVE_ALL=true` in `.env` for non-interactive use
- Runtime artifacts (`.artifacts/`, `.traces/`, `.logs/`) are gitignored

---
name: computer-use-harness
description: Use when needing to start, run, test, or execute commands on the local Windows computer-use harness, including the Python CLI and .NET sidecar
---

# Computer-Use Harness

## Overview

Local Windows automation harness with a Python control plane and .NET sidecar. The Python CLI orchestrates tools via an OpenAI-backed agent loop, while the .NET sidecar provides Windows-native UI operations over localhost HTTP.

## Project Location

`C:\Users\aswie\source\repos\3r453r\computer-use-harness`

## Quick Reference

| Component | Path | Purpose |
|-----------|------|---------|
| Python CLI | `src/computer_use_harness/cli.py` | Entry point (`run`, `tools` commands) |
| Agent harness | `src/computer_use_harness/agent/harness.py` | Main agent loop |
| Planner client | `src/computer_use_harness/agent/openai_client.py` | OpenAI Responses API adapter |
| Settings | `src/computer_use_harness/config/settings.py` | Pydantic settings from `.env` |
| Tool registry | `src/computer_use_harness/tools/registry.py` | Tool lookup |
| Local tools | `src/computer_use_harness/tools/local_tools.py` | All tool implementations |
| Safety policy | `src/computer_use_harness/safety/policy.py` | Approval/deny logic |
| .NET sidecar | `dotnet-sidecar/LocalWindowsSidecar/Program.cs` | Window ops HTTP API |
| Tests | `tests/test_policy.py` | Approval policy tests |

## Starting the Harness

### 1. Activate the Python venv (required)

```bash
# From repo root
cd /c/Users/aswie/source/repos/3r453r/computer-use-harness

# Bash
source .venv/Scripts/activate

# PowerShell
.venv\Scripts\Activate.ps1
```

Without activation, `computer-use-harness` won't be on PATH. Alternative: call directly with `.venv/Scripts/computer-use-harness`.

### 2. Ensure `.env` exists

```bash
cp .env.example .env
# Set OPENAI_API_KEY in .env
```

### 3. CLI Commands

```bash
# List available tools
computer-use-harness tools

# Run a task
computer-use-harness run "your task description here"

# Direct invocation without venv activation
.venv/Scripts/computer-use-harness tools
.venv/Scripts/computer-use-harness run "restart my dev server"
```

### 4. Start the .NET sidecar (optional, for window operations)

```bash
cd dotnet-sidecar/LocalWindowsSidecar
dotnet run
# Listens on http://127.0.0.1:47901
```

Health check: `curl http://127.0.0.1:47901/health`

### 5. Run tests

```bash
cd /c/Users/aswie/source/repos/3r453r/computer-use-harness
.venv/Scripts/python -m pytest tests/
```

## Available Tools

| Tool | Dangerous | Description |
|------|-----------|-------------|
| `screen.capture` | No | Screenshot capture |
| `mouse.*` | No | move, click, double_click, right_click, scroll |
| `keyboard.*` | No | type, hotkey |
| `terminal.exec` | Yes | Execute shell command |
| `fs.*` | No | read, write, list files |
| `process.*` | No/Yes | list, find, kill processes |
| `browser.*` | No | Playwright browser automation |
| `sidecar.call` | Yes | Call .NET sidecar endpoint |

## Settings (`.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | (empty) | Required for agent mode |
| `OPENAI_MODEL` | `gpt-5.4` | Model for planner |
| `DRY_RUN` | `false` | Block all tool execution |
| `AUTO_APPROVE_SAFE` | `true` | Auto-approve non-dangerous tools |
| `MAX_STEPS` | `15` | Agent loop step limit |
| `SIDECAR_BASE_URL` | `http://127.0.0.1:47901` | Sidecar address |

## Common Issues

| Problem | Fix |
|---------|-----|
| `computer-use-harness` not recognized | Activate venv or use `.venv/Scripts/computer-use-harness` directly |
| `dotnet run` fails with Swagger error | Ensure `Program.cs` does NOT have `AddSwaggerGen`/`UseSwagger`/`UseSwaggerUI` (removed in bugfix) |
| Sidecar connection refused | Start sidecar first: `cd dotnet-sidecar/LocalWindowsSidecar && dotnet run` |
| Missing OPENAI_API_KEY | Copy `.env.example` to `.env` and fill in the key |

## Sidecar API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/window/list` | List visible windows |
| POST | `/window/get_active` | Get foreground window info |
| POST | `/window/focus` | Focus window by title regex |
| POST | `/ui/inspect_active_window` | Active window metadata |
| POST | `/ui/find_element` | Stub - not yet implemented |
| POST | `/ui/invoke` | Stub - not yet implemented |
| POST | `/ui/set_text` | Stub - not yet implemented |
| POST | `/ui/click_element` | Stub - not yet implemented |

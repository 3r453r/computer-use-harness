# Local Windows Computer-Use Harness (Python + .NET Sidecar)

Production-minded MVP for local-only automation on Windows 11.

## Chosen stack
- **Python 3.12+** control plane
  - Typer CLI
  - Pydantic/Pydantic Settings schemas + config
  - OpenAI Python SDK (`responses.create`) with model default `gpt-5.4`
  - `mss` + Pillow screenshot capture
  - `pyautogui` keyboard/mouse fallback
  - `psutil` process tools
  - `requests` sidecar client
  - `structlog` structured logs + JSON execution traces
- **.NET 8 (ASP.NET Core, windows target)** sidecar
  - Localhost HTTP API (`127.0.0.1:47901`)
  - Windows APIs (`user32`) for real window enumeration/focus/active window metadata
  - UI Automation endpoints stubbed for extension in-place

## Why Python + .NET split
- Python is ideal for fast orchestration, model/tool looping, retries, logging, policies, and broad automation ecosystem.
- .NET offers more reliable Windows-native integration (window metadata, focus, future UIA control tree interactions) with strong compatibility for desktop apps.
- A clear IPC boundary lets sidecar evolve independently without destabilizing planner/runtime logic.

## IPC choice
**Local HTTP on localhost**:
- Simple, debuggable contract
- Language-agnostic, stable for future clients
- Easy health checks and timeout handling
- Lower friction than named pipes for initial MVP while remaining local-only

## Architecture summary
1. CLI receives task
2. Agent harness gathers lightweight state + tool specs
3. Planner (GPT-5.4 via OpenAI Responses API) returns `tool_call` or `final`
4. Approval policy evaluates dangerous actions
5. Tool executes locally (terminal/fs/process/browser/screen/input/sidecar)
6. Result appended to action history
7. Loop continues until final answer or step cap reached
8. JSON trace persisted for replay/debugging

## Python/.NET responsibility split
### Python
- Main orchestration loop
- OpenAI integration and tool routing
- Safety/approval policy and dry-run support
- Logging + JSON traces
- Deterministic tools: terminal/fs/process
- Browser wrapper hooks and screenshot/input fallback
- Sidecar invocation adapter

### .NET
- Window list/focus/active-window endpoints (implemented)
- UI inspection/action endpoints (MVP stubs with stable contract)
- Foundation for advanced UI Automation extension

## Milestones
1. Scaffold project + config + CLI
2. Implement agent/planner loop + tool registry
3. Add safety policy, traces, retries/step limits
4. Implement local tool adapters
5. Integrate .NET sidecar + local HTTP contract
6. Add docs, demos, basic tests

## Project tree
```text
.
├── .env.example
├── pyproject.toml
├── README.md
├── src/computer_use_harness
│   ├── agent/
│   ├── cli.py
│   ├── config/
│   ├── demos/tasks.md
│   ├── logging/
│   ├── models/
│   ├── safety/
│   ├── sidecar/
│   └── tools/
├── tests/test_policy.py
└── dotnet-sidecar/LocalWindowsSidecar
    ├── LocalWindowsSidecar.csproj
    ├── Models/WindowModels.cs
    └── Program.cs
```

## Setup (Windows)
### Python harness
1. `python -m venv .venv`
2. `.venv\\Scripts\\activate`
3. `pip install -e .`
4. `copy .env.example .env`
5. Set `OPENAI_API_KEY` in `.env`

### .NET sidecar
1. Install .NET 8 SDK on Windows
2. `cd dotnet-sidecar/LocalWindowsSidecar`
3. `dotnet run`

## Run
From repo root:
- List tools: `computer-use-harness tools`
- Run task: `computer-use-harness run "restart my Next.js dev server in the current repo"`

## Safety model
- `dry_run` blocks execution
- Dangerous tools require approval prompt
- Command denylist hook for obvious high-risk shell commands
- Allowlist directories via `ALLOWED_PATHS`
- Treats on-screen content as untrusted; deterministic paths preferred first

## Demo tasks
See `src/computer_use_harness/demos/tasks.md`.

## Known limitations (MVP)
- Browser automation is minimal wrapper (full Playwright scripts should be added next)
- UIA endpoints in sidecar are placeholders except window operations
- Current screenshot mode uses full-monitor first; active-window capture is basic
- Multi-monitor and DPI edge-cases documented but not fully normalized yet

## Next improvements
- Implement full UIA traversal/actions in sidecar (`AutomationElement`)
- Add robust Playwright action schema + browser session lifecycle manager
- Add richer planner response schema with strict JSON mode validation
- Persist run artifacts (screenshots/log chunks) per-step with correlation IDs
- Add policy profiles and non-interactive approval backends

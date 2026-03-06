from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer

from computer_use_harness.agent.harness import AgentHarness
from computer_use_harness.config.settings import Settings
from computer_use_harness.logging.logger import configure_logging
from computer_use_harness.tools.local_tools import (
    AliasTool,
    BrowserTool,
    FileSystemTool,
    KeyboardTool,
    MouseTool,
    ProcessTool,
    ScreenCaptureTool,
    SidecarTool,
    SystemInstallTool,
    TerminalExecTool,
)
from computer_use_harness.tools.registry import ToolRegistry

app = typer.Typer(
    help="Local Windows computer-use harness — an AI agent that autonomously operates your PC.",
    epilog=(
        "Environment variables (also settable via .env file):\n\n"
        "  OPENAI_API_KEY        Required. Your OpenAI API key.\n"
        "  OPENAI_MODEL          Model to use (default: gpt-5.4)\n"
        "  MAX_STEPS             Max agent loop iterations (default: 15)\n"
        "  AUTO_APPROVE_ALL      Skip interactive approval prompts (default: false)\n"
        "  FULLY_AUTOMATED       Enable full automation incl. system.install (default: false)\n"
        "  INSTALL_TIMEOUT_S     Timeout for install operations in seconds (default: 300)\n"
        "  DRY_RUN               Plan without executing tools (default: false)\n"
        "  SIDECAR_BASE_URL      .NET sidecar URL (default: http://127.0.0.1:47901)\n"
        "  PRICE_INPUT_PER_M     Input token price per 1M (default: 2.50)\n"
        "  PRICE_OUTPUT_PER_M    Output token price per 1M (default: 10.00)\n"
        "  WORKSPACE_ROOT        Working directory for tools (default: cwd)\n"
        "  TOOL_TIMEOUT_S        Per-tool execution timeout in seconds (default: 20)\n"
        "  GUI_ACTION_DELAY_S    Pause after GUI actions in seconds (default: 1.5)\n"
    ),
    rich_markup_mode="rich",
)


def build_registry(settings: Settings) -> ToolRegistry:
    screen = ScreenCaptureTool(settings)
    mouse = MouseTool()
    keyboard = KeyboardTool()
    terminal = TerminalExecTool(settings)
    fs = FileSystemTool()
    proc = ProcessTool()
    browser = BrowserTool()
    sidecar = SidecarTool(settings)
    tools = {
        "screen.capture": screen,
        "mouse.move": AliasTool("mouse.move", mouse, "move"),
        "mouse.click": AliasTool("mouse.click", mouse, "click"),
        "mouse.double_click": AliasTool("mouse.double_click", mouse, "double_click"),
        "mouse.right_click": AliasTool("mouse.right_click", mouse, "right_click"),
        "mouse.scroll": AliasTool("mouse.scroll", mouse, "scroll"),
        "keyboard.type": AliasTool("keyboard.type", keyboard, "type"),
        "keyboard.hotkey": AliasTool("keyboard.hotkey", keyboard, "hotkey"),
        "terminal.exec": terminal,
        "fs.read": AliasTool("fs.read", fs, "read"),
        "fs.write": AliasTool("fs.write", fs, "write"),
        "fs.list": AliasTool("fs.list", fs, "list"),
        "process.list": AliasTool("process.list", proc, "list"),
        "process.kill": AliasTool("process.kill", proc, "kill"),
        "process.find": AliasTool("process.find", proc, "find"),
        "browser.open": browser,
        "browser.playwright": browser,
        "sidecar.call": sidecar,
    }
    if settings.fully_automated:
        tools["system.install"] = SystemInstallTool(settings)
    return ToolRegistry(tools=tools)


@app.command(help="Run a task autonomously. Example: computer-use-harness run \"open notepad and type hello\"")
def run(
    task: str = typer.Argument(help="Natural language description of the task to perform"),
    max_steps: Optional[int] = typer.Option(None, "--max-steps", "-n", help="Max agent loop iterations (env: MAX_STEPS)"),
    auto_approve: bool = typer.Option(False, "--auto-approve", "-y", help="Skip all interactive approval prompts"),
    fully_automated: bool = typer.Option(False, "--fully-automated", help="Enable full automation including system.install tool"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Plan without executing any tools"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="OpenAI model to use (env: OPENAI_MODEL)"),
) -> None:
    settings = Settings()
    if max_steps is not None:
        settings.max_steps = max_steps
    if auto_approve:
        settings.auto_approve_all = True
    if fully_automated:
        settings.fully_automated = True
        settings.auto_approve_all = True
    if dry_run:
        settings.dry_run = True
    if model is not None:
        settings.openai_model = model
    configure_logging(settings.logs_dir)
    harness = AgentHarness(settings=settings, registry=build_registry(settings))
    result = harness.run_task(task)
    result["task"] = task
    typer.echo(json.dumps(result, indent=2))

    # Save run result to .runs/
    runs_dir = Path(".runs")
    runs_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", task)[:40].rstrip("_")
    run_path = runs_dir / f"run-{stamp}-{slug}.json"
    run_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    _print_usage_summary(result.get("usage"))


@app.command(help="List all registered tools and their schemas.")
def tools() -> None:
    settings = Settings()
    registry = build_registry(settings)
    typer.echo(json.dumps([s.model_dump() for s in registry.specs()], indent=2))


@app.command(help="Show current configuration (from env + .env file).")
def config() -> None:
    settings = Settings()
    masked = settings.model_dump()
    if masked.get("openai_api_key"):
        key = masked["openai_api_key"]
        masked["openai_api_key"] = key[:8] + "..." + key[-4:] if len(key) > 12 else "***"
    for k, v in masked.items():
        if isinstance(v, Path):
            masked[k] = str(v)
    typer.echo(json.dumps(masked, indent=2, default=str))


def _print_usage_summary(usage: dict | None) -> None:
    if not usage:
        return
    steps = usage.get("steps", [])
    if not steps:
        return
    w = sys.stderr.write
    w("\n")
    w("Token Usage Summary\n")
    w("─" * 52 + "\n")
    for s in steps:
        w(f"  Step {s['step']:>2}:  {s['input_tokens']:>8,} in / {s['output_tokens']:>7,} out   ${s['cost']:.4f}\n")
    w("─" * 52 + "\n")
    w(f"  Total:   {usage['total_input_tokens']:>8,} in / {usage['total_output_tokens']:>7,} out   ${usage['total_cost']:.4f}\n")
    w("\n")


if __name__ == "__main__":
    app()

from __future__ import annotations

import json
import sys

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
    TerminalExecTool,
)
from computer_use_harness.tools.registry import ToolRegistry

app = typer.Typer(help="Local Windows computer-use harness")


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
    return ToolRegistry(tools=tools)


@app.command()
def run(task: str) -> None:
    settings = Settings()
    configure_logging(settings.logs_dir)
    harness = AgentHarness(settings=settings, registry=build_registry(settings))
    result = harness.run_task(task)
    typer.echo(json.dumps(result, indent=2))
    _print_usage_summary(result.get("usage"))


@app.command()
def tools() -> None:
    settings = Settings()
    registry = build_registry(settings)
    typer.echo(json.dumps([s.model_dump() for s in registry.specs()], indent=2))


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

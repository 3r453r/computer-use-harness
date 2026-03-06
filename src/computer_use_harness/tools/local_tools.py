from __future__ import annotations

import base64
import io
import json
import re
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil
import pyautogui
import requests
from mss import mss
from PIL import Image

from computer_use_harness.config.settings import Settings
from computer_use_harness.models.schemas import ActionResult, ToolSpec
from computer_use_harness.tools.base import Tool

pyautogui.FAILSAFE = True


def _result(tool: str, ok: bool, output: Any = None, error: str | None = None) -> ActionResult:
    now = datetime.now(tz=UTC)
    return ActionResult(tool=tool, ok=ok, output=output, error=error, started_at=now, ended_at=now)


class ScreenCaptureTool(Tool):
    spec = ToolSpec(name="screen.capture", description="Capture full monitor screenshot", input_schema={"type": "object", "properties": {"mode": {"type": "string"}}, "required": ["mode"]})

    def __init__(self, settings: Settings):
        self.settings = settings
        self.settings.screenshots_dir.mkdir(parents=True, exist_ok=True)

    def run(self, arguments: dict[str, Any]) -> ActionResult:
        mode = arguments.get("mode", "full")
        target = self.settings.screenshots_dir / f"shot-{int(time.time()*1000)}.png"
        with mss() as sct:
            monitor = sct.monitors[0]
            if mode == "active_window":
                monitor = sct.monitors[1]
            shot = sct.grab(monitor)
            img = Image.frombytes("RGB", shot.size, shot.rgb)
            img.save(target)

        w, h = img.size
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        return _result(self.spec.name, True, {
            "path": str(target),
            "mode": mode,
            "width": w,
            "height": h,
            "image_base64": b64,
        })


class MouseTool(Tool):
    spec = ToolSpec(name="mouse.dispatch", description="Mouse operations", input_schema={"type": "object"})

    def run(self, arguments: dict[str, Any]) -> ActionResult:
        action = arguments.get("action")
        x, y = arguments.get("x"), arguments.get("y")
        if action == "move":
            pyautogui.moveTo(x, y)
        elif action == "click":
            pyautogui.click(x=x, y=y, button=arguments.get("button", "left"))
        elif action == "double_click":
            pyautogui.doubleClick(x=x, y=y)
        elif action == "right_click":
            pyautogui.rightClick(x=x, y=y)
        elif action == "scroll":
            pyautogui.scroll(int(arguments.get("delta", 0)))
        else:
            return _result(self.spec.name, False, error=f"unknown action {action}")
        return _result(self.spec.name, True, {"action": action})


class KeyboardTool(Tool):
    spec = ToolSpec(name="keyboard.dispatch", description="Keyboard operations", input_schema={"type": "object"})

    def run(self, arguments: dict[str, Any]) -> ActionResult:
        action = arguments.get("action")
        if action == "type":
            pyautogui.write(arguments.get("text", ""), interval=0.01)
        elif action == "hotkey":
            pyautogui.hotkey(*arguments.get("keys", []))
        else:
            return _result(self.spec.name, False, error=f"unknown action {action}")
        return _result(self.spec.name, True, {"action": action})


class TerminalExecTool(Tool):
    spec = ToolSpec(name="terminal.exec", description="Execute local shell command", input_schema={"type": "object", "required": ["command"]}, dangerous=True)

    def __init__(self, settings: Settings):
        self.settings = settings

    def run(self, arguments: dict[str, Any]) -> ActionResult:
        cmd = arguments.get("command")
        if not cmd:
            return _result(self.spec.name, False, error="Missing required 'command' argument")
        cwd = arguments.get("cwd") or str(self.settings.workspace_root)
        timeout = int(arguments.get("timeout", self.settings.tool_timeout_s))
        try:
            proc = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, timeout=timeout)
            return _result(self.spec.name, proc.returncode == 0, {"stdout": proc.stdout, "stderr": proc.stderr, "returncode": proc.returncode})
        except subprocess.TimeoutExpired:
            return _result(self.spec.name, False, error=f"Command timed out after {timeout}s")
        except Exception as exc:  # noqa: BLE001
            return _result(self.spec.name, False, error=str(exc))


class FileSystemTool(Tool):
    spec = ToolSpec(name="fs.dispatch", description="Filesystem operations", input_schema={"type": "object"})

    def run(self, arguments: dict[str, Any]) -> ActionResult:
        action = arguments.get("action")
        path = Path(arguments.get("path", "."))
        if action == "read":
            try:
                return _result(self.spec.name, True, path.read_text(encoding="utf-8"))
            except UnicodeDecodeError:
                size = path.stat().st_size
                return _result(self.spec.name, False, error=f"Binary file ({path.suffix}, {size} bytes) — cannot read as text. Use screen.capture for images.")
            except FileNotFoundError:
                return _result(self.spec.name, False, error=f"File not found: {path}")
        if action == "write":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(arguments.get("content", ""), encoding="utf-8")
            return _result(self.spec.name, True, {"path": str(path)})
        if action == "list":
            try:
                return _result(self.spec.name, True, sorted([p.name for p in path.iterdir()]))
            except FileNotFoundError:
                return _result(self.spec.name, False, error=f"Directory not found: {path}")
        return _result(self.spec.name, False, error=f"unknown action {action}")


class ProcessTool(Tool):
    spec = ToolSpec(name="process.dispatch", description="Process operations", input_schema={"type": "object"})

    def run(self, arguments: dict[str, Any]) -> ActionResult:
        action = arguments.get("action")
        if action == "list":
            procs = [{"pid": p.pid, "name": p.name()} for p in psutil.process_iter(attrs=["name"])]
            return _result(self.spec.name, True, procs[:200])
        if action == "kill":
            psutil.Process(int(arguments["pid"])).kill()
            return _result(self.spec.name, True, {"pid": arguments["pid"]})
        if action == "find":
            pattern = arguments.get("pattern", ".*")
            matched = []
            for p in psutil.process_iter(attrs=["name"]):
                if re.search(pattern, p.info.get("name") or "", re.IGNORECASE):
                    matched.append({"pid": p.pid, "name": p.info.get("name")})
            return _result(self.spec.name, True, matched)
        return _result(self.spec.name, False, error=f"unknown action {action}")


class BrowserTool(Tool):
    spec = ToolSpec(name="browser.playwright", description="Browser automation wrapper", input_schema={"type": "object"})

    def run(self, arguments: dict[str, Any]) -> ActionResult:
        return _result(self.spec.name, True, {"note": "Use dedicated playwright runner integration; wrapper wired for future extension.", "request": arguments})


class SidecarTool(Tool):
    spec = ToolSpec(name="sidecar.call", description="Call local .NET sidecar endpoint", input_schema={"type": "object", "required": ["operation"]}, dangerous=True)

    def __init__(self, settings: Settings):
        self.settings = settings

    def run(self, arguments: dict[str, Any]) -> ActionResult:
        if "operation" not in arguments:
            return _result(self.spec.name, False, error="Missing required 'operation' argument. Usage: sidecar.call with operation='endpoint/path' and optional payload={...}")
        operation = arguments["operation"].strip("/")
        payload = arguments.get("payload", {})
        try:
            resp = requests.post(
                f"{self.settings.sidecar_base_url}/{operation}",
                json=payload,
                timeout=self.settings.sidecar_timeout_s,
            )
            try:
                body = resp.json() if resp.text else {}
            except Exception:  # noqa: BLE001
                body = {"raw": resp.text}
            if not resp.ok:
                return _result(self.spec.name, False, error=f"Sidecar HTTP {resp.status_code} for /{operation}. Available endpoints: window/get_active, window/list, window/focus, ui/inspect_active_window, ui/find_element, ui/click_element, ui/set_text, ui/invoke")
            return _result(self.spec.name, True, {"status": resp.status_code, "body": body})
        except Exception as exc:  # noqa: BLE001
            return _result(self.spec.name, False, error=str(exc))


class AliasTool(Tool):
    def __init__(self, alias: str, delegate: Tool, action: str | None = None):
        self.spec = ToolSpec(name=alias, description=f"Alias to {delegate.spec.name}", input_schema={"type": "object"}, dangerous=delegate.spec.dangerous)
        self.delegate = delegate
        self.action = action

    def run(self, arguments: dict[str, Any]) -> ActionResult:
        args = dict(arguments)
        if self.action is not None:
            args["action"] = self.action
        result = self.delegate.run(args)
        result.tool = self.spec.name
        return result

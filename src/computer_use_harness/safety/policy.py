from __future__ import annotations

from pathlib import Path

from computer_use_harness.config.settings import Settings
from computer_use_harness.models.schemas import ToolCall

DANGEROUS_TOOL_NAMES = {
    "process.kill",
    "fs.write",
    "terminal.exec",
    "sidecar.call",
}
DENY_COMMAND_SUBSTRINGS = ["git push", "rm -rf", "shutdown", "format", "pip install", "npm install -g"]


class ApprovalPolicy:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def requires_approval(self, call: ToolCall) -> bool:
        if call.tool in DANGEROUS_TOOL_NAMES:
            return True
        if call.tool == "terminal.exec":
            cmd = str(call.arguments.get("command", "")).lower()
            return any(token in cmd for token in DENY_COMMAND_SUBSTRINGS)
        return False

    def path_allowed(self, raw_path: str) -> bool:
        resolved = Path(raw_path).resolve()
        return any(str(resolved).startswith(str(base)) for base in self.settings.allowed_path_list)

    def approve(self, call: ToolCall) -> bool:
        if self.settings.dry_run:
            return False
        if self.settings.auto_approve_all:
            return True
        if not self.requires_approval(call) and self.settings.auto_approve_safe:
            return True
        response = input(f"Approve tool '{call.tool}' with args {call.arguments}? [y/N]: ").strip().lower()
        return response in {"y", "yes"}

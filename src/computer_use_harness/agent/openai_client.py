from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from computer_use_harness.config.settings import Settings
from computer_use_harness.models.schemas import AgentDecision, ToolCall, ToolSpec


SYSTEM_PROMPT = """You are a local Windows computer-use planner. Prefer deterministic tools first (terminal/fs/process/browser/sidecar) and screenshot pixel actions only as fallback. Return either a tool call or final answer in JSON."""


class PlannerClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    def plan(self, task: str, state: dict[str, Any], tools: list[ToolSpec], history: list[dict[str, Any]]) -> AgentDecision:
        if not self.client:
            return self._heuristic(task)

        payload = {
            "task": task,
            "state": state,
            "tools": [t.model_dump() for t in tools],
            "history": history,
            "format": {"kind": "tool_call|final", "message": "string", "tool_call": {"tool": "name", "arguments": {}}},
        }
        response = self.client.responses.create(
            model=self.settings.openai_model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload)},
            ],
            temperature=0.1,
        )
        text = getattr(response, "output_text", "") or ""
        try:
            data = json.loads(text)
            return AgentDecision.model_validate(data)
        except Exception:  # noqa: BLE001
            return AgentDecision(kind="final", message=text or "No valid planner output.")

    def _heuristic(self, task: str) -> AgentDecision:
        lower = task.lower()
        if "restart" in lower and "next" in lower:
            return AgentDecision(kind="tool_call", tool_call=ToolCall(tool="terminal.exec", arguments={"command": "npm run dev", "cwd": "."}, reason="deterministic restart"))
        return AgentDecision(kind="final", message="OPENAI_API_KEY missing; heuristic planner did not find a deterministic action.")

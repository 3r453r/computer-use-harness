from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from computer_use_harness.config.settings import Settings
from computer_use_harness.models.schemas import AgentDecision, ToolCall, ToolSpec


SYSTEM_PROMPT = """You are a local Windows computer-use planner. Prefer deterministic tools (terminal/fs/process/browser/sidecar) over screenshot/pixel actions.

Your response is structured JSON with these rules:
- To execute a tool: set "kind" to "tool_call", set "tool_call" to an object with "tool", "arguments_json" (a JSON string of the arguments), and "reason". Set "message" to null.
- To give a final answer: set "kind" to "final", set "message" to your answer string. Set "tool_call" to null.

IMPORTANT: When you want to call a tool, you MUST set kind to "tool_call" and populate the tool_call field. Do NOT put tool call JSON inside the message field."""

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
        return self._parse_response(text)

    @staticmethod
    def _parse_response(text: str) -> AgentDecision:
        """Parse model output that may contain one or more concatenated JSON objects.

        Extracts all JSON objects via a streaming decoder and returns the first
        tool_call decision found, falling back to the first final decision.
        """
        objects: list[dict[str, Any]] = []
        decoder = json.JSONDecoder()
        idx = 0
        while idx < len(text):
            # skip whitespace
            while idx < len(text) and text[idx] in " \t\n\r":
                idx += 1
            if idx >= len(text):
                break
            try:
                obj, end = decoder.raw_decode(text, idx)
                objects.append(obj)
                idx = end
            except json.JSONDecodeError:
                break

        if not objects:
            return AgentDecision(kind="final", message=text or "No valid planner output.")

        # Normalize tool_call arguments across different field names
        for obj in objects:
            tc = obj.get("tool_call")
            if tc and isinstance(tc, dict):
                if "arguments_json" in tc:
                    try:
                        tc["arguments"] = json.loads(tc.pop("arguments_json"))
                    except (json.JSONDecodeError, TypeError):
                        pass

        # Prefer the first tool_call decision
        for obj in objects:
            if obj.get("kind") == "tool_call" and obj.get("tool_call"):
                try:
                    return AgentDecision.model_validate(obj)
                except Exception:  # noqa: BLE001
                    continue

        # Fall back to first parseable decision
        for obj in objects:
            try:
                return AgentDecision.model_validate(obj)
            except Exception:  # noqa: BLE001
                continue

        return AgentDecision(kind="final", message=text or "No valid planner output.")

    def _heuristic(self, task: str) -> AgentDecision:
        lower = task.lower()
        if "restart" in lower and "next" in lower:
            return AgentDecision(kind="tool_call", tool_call=ToolCall(tool="terminal.exec", arguments={"command": "npm run dev", "cwd": "."}, reason="deterministic restart"))
        return AgentDecision(kind="final", message="OPENAI_API_KEY missing; heuristic planner did not find a deterministic action.")

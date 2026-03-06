from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

from computer_use_harness.config.settings import Settings
from computer_use_harness.models.schemas import AgentDecision, ToolCall, ToolSpec


SYSTEM_PROMPT = """You are a local Windows computer-use planner on a Windows 11 machine.

## Tool Selection Strategy (cost-optimized)
1. **Deterministic first**: terminal.exec, fs.read/write, process.list/find/kill — fastest and cheapest.
2. **Sidecar UI Automation second**: When interacting with GUI apps, use sidecar.call to discover and interact with UI elements programmatically. This is MUCH cheaper than screenshots.
   - sidecar.call operation="window/get_active" → returns active window title, handle, pid.
   - sidecar.call operation="window/list" → lists all visible windows.
   - sidecar.call operation="window/focus" payload={"titlePattern":"regex"} → focuses a window by title regex.
   - sidecar.call operation="ui/inspect_active_window" → returns UI element tree of the active window (names, types, bounding boxes).
   - sidecar.call operation="ui/find_element" payload={"name":"...", "controlType":"...", "automationId":"..."} → finds elements matching criteria (at least one field required).
   - sidecar.call operation="ui/click_element" payload={"name":"...", "automationId":"...", "index":0} → clicks an element by name or automationId, no pixel coordinates needed.
   - sidecar.call operation="ui/set_text" payload={"name":"...", "automationId":"...", "text":"...", "index":0} → types text into a field.
   - sidecar.call operation="ui/invoke" payload={"name":"...", "automationId":"...", "index":0} → invokes a button or control.
   - Try sidecar first for any GUI interaction. Fall back to screenshot+mouse only if sidecar cannot find the element.
3. **Screenshot + mouse/keyboard last**: Use screen.capture only when sidecar cannot help (e.g., custom-rendered UI, images, or when you need visual context).

## Screenshot Best Practices
- After performing a GUI action (click, type, scroll), the harness automatically waits before allowing the next step. No need to add delays yourself.
- Do NOT take back-to-back screenshots without an action in between.
- Each screenshot result includes "ui_changed" (true/false) and "change_magnitude" (0-1). USE THIS FEEDBACK:
  - ui_changed=true → your last action worked, continue your plan
  - ui_changed=false → your last action had NO EFFECT, you MUST try something different

## Click Escalation (when ui_changed is false)
1. First attempt: single click on the element
2. If ui_changed=false → double click on the same element
3. If still false → click 20-30px offset from original coordinates
4. If still false → try keyboard navigation (Tab to focus, Enter to activate)
5. If still false → try a completely different approach (sidecar, terminal, different UI path)

Never repeat the exact same action more than twice. The harness will warn you if you're stuck.

- The screenshot is at full screen resolution — x,y coordinates map directly to mouse coordinates with no scaling needed.

## Verification Rules
- After any important GUI action (opening an app, creating a new tab, saving a file), ALWAYS take a screenshot to verify it worked before continuing.
- Before declaring "final", verify the outcome: if you wrote a file, confirm it exists with fs.read or fs.list. If you changed an app state, take a screenshot to confirm.
- If you need to create a directory before saving, use terminal.exec: "mkdir -p <path>" or "powershell New-Item -ItemType Directory -Force -Path '<path>'"
- keyboard.type automatically uses clipboard (Ctrl+V) for paths, long strings, and non-ASCII text. You do not need to handle this yourself.

## Response Format
Your response is structured JSON:
- To execute a tool: {"kind": "tool_call", "tool_call": {"tool": "<name>", "arguments_json": "<json string>", "reason": "<why>"}, "message": null}
- To give a final answer: {"kind": "final", "message": "<answer>", "tool_call": null}

IMPORTANT: When you want to call a tool, you MUST set kind to "tool_call" and populate the tool_call field. Do NOT put tool call JSON inside the message field."""

class PlannerClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

    def plan(
        self,
        task: str,
        state: dict[str, Any],
        tools: list[ToolSpec],
        history: list[dict[str, Any]],
        screenshot_base64: str | None = None,
    ) -> tuple[AgentDecision, dict[str, int]]:
        if not self.client:
            return self._heuristic(task), {"input_tokens": 0, "output_tokens": 0}

        payload = {
            "task": task,
            "state": state,
            "tools": [t.model_dump() for t in tools],
            "history": history,
        }

        # Build user message — multimodal if screenshot available
        if screenshot_base64:
            user_content: str | list[dict[str, Any]] = [
                {"type": "input_text", "text": json.dumps(payload)},
                {"type": "input_image", "image_url": f"data:image/jpeg;base64,{screenshot_base64}"},
            ]
        else:
            user_content = json.dumps(payload)

        response = self.client.responses.create(
            model=self.settings.openai_model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
        )
        text = getattr(response, "output_text", "") or ""
        usage = {"input_tokens": 0, "output_tokens": 0}
        if response.usage:
            usage["input_tokens"] = response.usage.input_tokens
            usage["output_tokens"] = response.usage.output_tokens
        return self._parse_response(text), usage

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

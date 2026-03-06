from __future__ import annotations

import base64
import io
import time
import uuid
from pathlib import Path
from typing import Any

import structlog
from PIL import Image

from computer_use_harness.agent.openai_client import PlannerClient
from computer_use_harness.agent.screenshot_diff import compute_diff
from computer_use_harness.agent.stuck_detector import StuckDetector
from computer_use_harness.config.settings import Settings
from computer_use_harness.logging.trace import TraceRecorder
from computer_use_harness.models.schemas import ActionResult, AgentDecision, RunUsage, StepUsage, TraceEntry
from computer_use_harness.safety.policy import ApprovalPolicy
from computer_use_harness.tools.registry import ToolRegistry


class AgentHarness:
    def __init__(self, settings: Settings, registry: ToolRegistry):
        self.settings = settings
        self.registry = registry
        self.planner = PlannerClient(settings)
        self.policy = ApprovalPolicy(settings)
        self.trace = TraceRecorder(settings.traces_dir)
        self.log = structlog.get_logger("harness")
        self.stuck_detector = StuckDetector()

    def run_task(self, task: str) -> dict[str, Any]:
        run_id = str(uuid.uuid4())
        history: list[dict[str, Any]] = []
        state = {"cwd": str(Path.cwd()), "dry_run": self.settings.dry_run}
        run_usage = RunUsage()
        latest_screenshot: str | None = None
        prev_screenshot_img: Image.Image | None = None
        self.stuck_detector.reset()

        for step in range(1, self.settings.max_steps + 1):
            # Inject stuck warning if needed
            if self.stuck_detector.is_stuck():
                warning = self.stuck_detector.warning_message()
                history.append({"system_warning": warning})
                self.log.warning("stuck_detected", step=step, warning=warning)

            decision, usage = self.planner.plan(
                task, state=state, tools=self.registry.specs(),
                history=history, screenshot_base64=latest_screenshot,
            )
            latest_screenshot = None  # consumed
            self._record_usage(run_usage, step, usage)
            self.log.info("decision", step=step, decision=decision.model_dump())

            if decision.kind == "final":
                self.trace.append(TraceEntry(step=step, task=task, decision=decision))
                trace_path = self.trace.write(run_id)
                return {"status": "completed", "message": decision.message, "trace": str(trace_path), "usage": run_usage.model_dump()}

            result = self._execute(decision)
            self.trace.append(TraceEntry(step=step, task=task, decision=decision, result=result))

            # Record action for stuck detection
            if decision.tool_call:
                self.stuck_detector.record(decision.tool_call.tool, decision.tool_call.arguments)

            # Auto-delay after GUI actions
            if decision.tool_call and self._is_gui_tool(decision.tool_call.tool):
                time.sleep(self.settings.gui_action_delay_s)

            # Extract screenshot base64 for next planner call (don't store in history)
            result_dump = result.model_dump(mode="json")
            if result.ok and isinstance(result.output, dict) and "image_base64" in result.output:
                latest_screenshot = result.output["image_base64"]
                # Screenshot diff
                img_bytes = base64.b64decode(latest_screenshot)
                current_img = Image.open(io.BytesIO(img_bytes))
                diff_info = compute_diff(prev_screenshot_img, current_img)
                prev_screenshot_img = current_img
                if diff_info["ui_changed"]:
                    self.stuck_detector.notify_ui_changed()
                # Add diff info and strip base64 from history
                output_for_history = {k: v for k, v in result.output.items() if k != "image_base64"}
                output_for_history.update(diff_info)
                result_dump["output"] = output_for_history
            elif result.ok and isinstance(result.output, dict):
                result_dump["output"] = result.output

            history.append({"decision": decision.model_dump(), "result": result_dump})

            if not result.ok:
                self.log.warning("tool_failed", tool=result.tool, error=result.error)

        trace_path = self.trace.write(run_id)
        return {"status": "max_steps_exceeded", "trace": str(trace_path), "usage": run_usage.model_dump()}

    def _record_usage(self, run_usage: RunUsage, step: int, usage: dict[str, int]) -> None:
        input_t = usage.get("input_tokens", 0)
        output_t = usage.get("output_tokens", 0)
        cost = (input_t * self.settings.price_input_per_m + output_t * self.settings.price_output_per_m) / 1_000_000
        run_usage.steps.append(StepUsage(step=step, input_tokens=input_t, output_tokens=output_t, cost=cost))
        run_usage.total_input_tokens += input_t
        run_usage.total_output_tokens += output_t
        run_usage.total_cost += cost

    def _execute(self, decision: AgentDecision) -> ActionResult:
        call = decision.tool_call
        if call is None:
            return ActionResult(tool="none", ok=False, error="Missing tool call")

        if not self.policy.approve(call):
            return ActionResult(tool=call.tool, ok=False, error="Approval denied or dry-run")

        tool = self.registry.get(call.tool)
        return tool.run(call.arguments)

    @staticmethod
    def _is_gui_tool(tool_name: str) -> bool:
        return tool_name.startswith("mouse.") or tool_name.startswith("keyboard.")

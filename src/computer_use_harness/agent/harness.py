from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import structlog

from computer_use_harness.agent.openai_client import PlannerClient
from computer_use_harness.config.settings import Settings
from computer_use_harness.logging.trace import TraceRecorder
from computer_use_harness.models.schemas import ActionResult, AgentDecision, TraceEntry
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

    def run_task(self, task: str) -> dict[str, Any]:
        run_id = str(uuid.uuid4())
        history: list[dict[str, Any]] = []
        state = {"cwd": str(Path.cwd()), "dry_run": self.settings.dry_run}

        for step in range(1, self.settings.max_steps + 1):
            decision = self.planner.plan(task, state=state, tools=self.registry.specs(), history=history)
            self.log.info("decision", step=step, decision=decision.model_dump())

            if decision.kind == "final":
                self.trace.append(TraceEntry(step=step, task=task, decision=decision))
                trace_path = self.trace.write(run_id)
                return {"status": "completed", "message": decision.message, "trace": str(trace_path)}

            result = self._execute(decision)
            self.trace.append(TraceEntry(step=step, task=task, decision=decision, result=result))
            history.append({"decision": decision.model_dump(), "result": result.model_dump(mode="json")})

            if not result.ok:
                self.log.warning("tool_failed", tool=result.tool, error=result.error)

        trace_path = self.trace.write(run_id)
        return {"status": "max_steps_exceeded", "trace": str(trace_path)}

    def _execute(self, decision: AgentDecision) -> ActionResult:
        call = decision.tool_call
        if call is None:
            return ActionResult(tool="none", ok=False, error="Missing tool call")

        if not self.policy.approve(call):
            return ActionResult(tool=call.tool, ok=False, error="Approval denied or dry-run")

        tool = self.registry.get(call.tool)
        return tool.run(call.arguments)

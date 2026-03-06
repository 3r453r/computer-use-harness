from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from datetime import UTC, datetime
from typing import Any

from computer_use_harness.agent.harness import AgentHarness
from computer_use_harness.config.settings import Settings
from computer_use_harness.models.schemas import ActionResult, AgentDecision, ToolCall, ToolSpec
from computer_use_harness.tools.base import Tool
from computer_use_harness.tools.registry import ToolRegistry


class FakeTool(Tool):
    spec = ToolSpec(name="mouse.click", description="fake", input_schema={"type": "object"})

    def run(self, arguments: dict[str, Any]) -> ActionResult:
        now = datetime.now(tz=UTC)
        return ActionResult(tool="mouse.click", ok=True, output={"action": "click"}, started_at=now, ended_at=now)


def test_stuck_warning_injected_into_history():
    """After 3 identical mouse clicks, a system_warning should appear in history."""
    settings = Settings(
        openai_api_key="test",
        max_steps=5,
        dry_run=False,
        auto_approve_all=True,
        gui_action_delay_s=0,
    )
    registry = ToolRegistry(tools={"mouse.click": FakeTool()})
    harness = AgentHarness(settings=settings, registry=registry)

    click_decision = AgentDecision(
        kind="tool_call",
        tool_call=ToolCall(tool="mouse.click", arguments={"x": 100, "y": 200}, reason="test"),
    )
    final_decision = AgentDecision(kind="final", message="done")

    # Track history snapshots passed to plan() so we can verify the warning injection
    history_snapshots: list[list[dict[str, Any]]] = []

    call_count = 0

    def fake_plan(task, state, tools, history, screenshot_base64=None):
        nonlocal call_count
        call_count += 1
        # Capture a copy of history at each call
        history_snapshots.append([dict(h) for h in history])
        if call_count <= 4:
            return click_decision, {"input_tokens": 0, "output_tokens": 0}
        return final_decision, {"input_tokens": 0, "output_tokens": 0}

    harness.planner.plan = fake_plan
    result = harness.run_task("test task")

    assert result["status"] == "completed"

    # After 3 identical clicks (recorded at end of steps 1-3), the stuck detector
    # fires at the start of step 4.  So the 4th plan call (call_count=4) should
    # see a system_warning in its history.
    assert any("system_warning" in entry for entry in history_snapshots[3]), (
        "Expected a system_warning in history by the 4th plan call"
    )

    # The first 3 plan calls should NOT have a stuck warning
    for i in range(3):
        assert not any("system_warning" in entry for entry in history_snapshots[i]), (
            f"Did not expect a system_warning in history at plan call {i + 1}"
        )

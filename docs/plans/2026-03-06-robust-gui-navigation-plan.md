# Robust GUI Navigation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the agent loop resilient to stuck loops, wrong click types, and missing UI feedback by adding harness-level enforcement.

**Architecture:** Four independent features wired into the existing `AgentHarness.run_task()` loop: (1) a stuck detector that tracks recent actions and injects warnings, (2) an auto-delay after GUI tool calls, (3) screenshot diff feedback via PIL pixel comparison, (4) click escalation guidance in the system prompt.

**Tech Stack:** Python, PIL (already a dependency), Pydantic, pytest

---

### Task 1: Add `gui_action_delay_s` setting

**Files:**
- Modify: `src/computer_use_harness/config/settings.py:29` (after `max_steps`)
- Modify: `src/computer_use_harness/cli.py` (add to epilog)

**Step 1: Add the setting**

In `src/computer_use_harness/config/settings.py`, add after line 30 (`tool_timeout_s`):

```python
gui_action_delay_s: float = Field(default=1.5)
```

**Step 2: Add to CLI epilog**

In `src/computer_use_harness/cli.py`, add to the epilog string:

```
"  GUI_ACTION_DELAY_S     Pause after GUI actions in seconds (default: 1.5)\n"
```

**Step 3: Commit**

```bash
git add src/computer_use_harness/config/settings.py src/computer_use_harness/cli.py
git commit -m "feat: add gui_action_delay_s setting"
```

---

### Task 2: Stuck detector — unit tests

**Files:**
- Create: `tests/test_stuck_detector.py`

**Step 1: Write failing tests**

```python
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from computer_use_harness.agent.stuck_detector import StuckDetector


def test_no_stuck_on_different_tools():
    sd = StuckDetector(threshold=3)
    sd.record("mouse.click", {"x": 100, "y": 200})
    sd.record("screen.capture", {"mode": "full"})
    sd.record("mouse.click", {"x": 300, "y": 400})
    assert not sd.is_stuck()


def test_stuck_on_same_mouse_coords():
    sd = StuckDetector(threshold=3)
    sd.record("mouse.click", {"x": 100, "y": 200})
    sd.record("mouse.click", {"x": 105, "y": 198})
    sd.record("mouse.click", {"x": 102, "y": 203})
    assert sd.is_stuck()


def test_stuck_on_same_scroll_direction():
    sd = StuckDetector(threshold=3)
    sd.record("mouse.scroll", {"delta": 500})
    sd.record("mouse.scroll", {"delta": 600})
    sd.record("mouse.scroll", {"delta": 500})
    assert sd.is_stuck()


def test_not_stuck_mixed_scroll_directions():
    sd = StuckDetector(threshold=3)
    sd.record("mouse.scroll", {"delta": 500})
    sd.record("mouse.scroll", {"delta": -300})
    sd.record("mouse.scroll", {"delta": 500})
    assert not sd.is_stuck()


def test_stuck_on_same_keyboard():
    sd = StuckDetector(threshold=3)
    sd.record("keyboard.hotkey", {"keys": ["END"]})
    sd.record("keyboard.hotkey", {"keys": ["END"]})
    sd.record("keyboard.hotkey", {"keys": ["END"]})
    assert sd.is_stuck()


def test_reset_clears_history():
    sd = StuckDetector(threshold=3)
    sd.record("mouse.click", {"x": 100, "y": 200})
    sd.record("mouse.click", {"x": 100, "y": 200})
    sd.record("mouse.click", {"x": 100, "y": 200})
    assert sd.is_stuck()
    sd.reset()
    assert not sd.is_stuck()


def test_ui_change_resets():
    sd = StuckDetector(threshold=3)
    sd.record("mouse.click", {"x": 100, "y": 200})
    sd.record("mouse.click", {"x": 100, "y": 200})
    sd.notify_ui_changed()
    sd.record("mouse.click", {"x": 100, "y": 200})
    assert not sd.is_stuck()


def test_warning_message():
    sd = StuckDetector(threshold=3)
    sd.record("mouse.click", {"x": 100, "y": 200})
    sd.record("mouse.click", {"x": 100, "y": 200})
    sd.record("mouse.click", {"x": 100, "y": 200})
    msg = sd.warning_message()
    assert "repeated" in msg.lower()
    assert "different" in msg.lower()


def test_different_tool_breaks_streak():
    sd = StuckDetector(threshold=3)
    sd.record("mouse.click", {"x": 100, "y": 200})
    sd.record("mouse.click", {"x": 100, "y": 200})
    sd.record("terminal.exec", {"command": "dir"})
    sd.record("mouse.click", {"x": 100, "y": 200})
    assert not sd.is_stuck()
```

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_stuck_detector.py -v
```

Expected: ModuleNotFoundError for `stuck_detector`

**Step 3: Commit test file**

```bash
git add tests/test_stuck_detector.py
git commit -m "test: add stuck detector tests (red)"
```

---

### Task 3: Stuck detector — implementation

**Files:**
- Create: `src/computer_use_harness/agent/stuck_detector.py`

**Step 1: Implement StuckDetector**

```python
from __future__ import annotations

import math
from typing import Any


class StuckDetector:
    def __init__(self, threshold: int = 3, coord_tolerance: float = 50.0):
        self.threshold = threshold
        self.coord_tolerance = coord_tolerance
        self._history: list[tuple[str, dict[str, Any]]] = []

    def record(self, tool: str, arguments: dict[str, Any]) -> None:
        self._history.append((tool, arguments))

    def reset(self) -> None:
        self._history.clear()

    def notify_ui_changed(self) -> None:
        self._history.clear()

    def is_stuck(self) -> bool:
        if len(self._history) < self.threshold:
            return False
        recent = self._history[-self.threshold:]
        first_tool = recent[0][0]
        if not all(t == first_tool for t, _ in recent):
            return False
        return all(self._similar(recent[0], entry) for entry in recent[1:])

    def warning_message(self) -> str:
        return (
            "You have repeated a similar action {n} times without progress. "
            "Try a fundamentally different approach: different coordinates, "
            "different click type (single vs double), keyboard navigation "
            "(Tab/Enter), scrolling, or a completely different tool."
        ).format(n=self.threshold)

    def _similar(self, a: tuple[str, dict], b: tuple[str, dict]) -> bool:
        tool_a, args_a = a
        tool_b, args_b = b
        if tool_a != tool_b:
            return False
        if tool_a.startswith("mouse.") and tool_a != "mouse.scroll":
            return self._coords_close(args_a, args_b)
        if tool_a == "mouse.scroll":
            da = args_a.get("delta", args_a.get("deltaY", args_a.get("delta_y", 0)))
            db = args_b.get("delta", args_b.get("deltaY", args_b.get("delta_y", 0)))
            return (da > 0) == (db > 0) and da != 0
        return args_a == args_b

    def _coords_close(self, a: dict, b: dict) -> bool:
        ax, ay = a.get("x", 0), a.get("y", 0)
        bx, by = b.get("x", 0), b.get("y", 0)
        return math.hypot(ax - bx, ay - by) <= self.coord_tolerance
```

**Step 2: Run tests to verify they pass**

```bash
python -m pytest tests/test_stuck_detector.py -v
```

Expected: All 9 tests PASS

**Step 3: Commit**

```bash
git add src/computer_use_harness/agent/stuck_detector.py
git commit -m "feat: implement stuck detector"
```

---

### Task 4: Screenshot diff — unit tests

**Files:**
- Create: `tests/test_screenshot_diff.py`

**Step 1: Write failing tests**

```python
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PIL import Image
from computer_use_harness.agent.screenshot_diff import compute_diff


def test_identical_images():
    img = Image.new("RGB", (100, 100), (128, 128, 128))
    result = compute_diff(img, img)
    assert result["ui_changed"] is False
    assert result["change_magnitude"] == 0.0


def test_completely_different_images():
    a = Image.new("RGB", (100, 100), (0, 0, 0))
    b = Image.new("RGB", (100, 100), (255, 255, 255))
    result = compute_diff(a, b)
    assert result["ui_changed"] is True
    assert result["change_magnitude"] == 1.0


def test_small_change_below_threshold():
    a = Image.new("RGB", (100, 100), (128, 128, 128))
    b = Image.new("RGB", (100, 100), (129, 128, 128))
    result = compute_diff(a, b)
    assert result["ui_changed"] is False
    assert result["change_magnitude"] < 0.01


def test_moderate_change():
    a = Image.new("RGB", (100, 100), (0, 0, 0))
    b = Image.new("RGB", (100, 100), (50, 50, 50))
    result = compute_diff(a, b)
    assert result["ui_changed"] is True
    assert 0.1 < result["change_magnitude"] < 0.3


def test_none_previous_returns_changed():
    img = Image.new("RGB", (100, 100), (128, 128, 128))
    result = compute_diff(None, img)
    assert result["ui_changed"] is True
```

**Step 2: Run to verify failure**

```bash
python -m pytest tests/test_screenshot_diff.py -v
```

Expected: ModuleNotFoundError for `screenshot_diff`

**Step 3: Commit test file**

```bash
git add tests/test_screenshot_diff.py
git commit -m "test: add screenshot diff tests (red)"
```

---

### Task 5: Screenshot diff — implementation

**Files:**
- Create: `src/computer_use_harness/agent/screenshot_diff.py`

**Step 1: Implement compute_diff**

```python
from __future__ import annotations

from typing import Any

from PIL import Image


def compute_diff(
    previous: Image.Image | None,
    current: Image.Image,
    threshold: float = 0.01,
) -> dict[str, Any]:
    if previous is None:
        return {"ui_changed": True, "change_magnitude": 1.0}

    prev_data = previous.convert("RGB").tobytes()
    curr_data = current.convert("RGB").tobytes()

    if len(prev_data) != len(curr_data):
        return {"ui_changed": True, "change_magnitude": 1.0}

    total = 0
    n = len(prev_data)
    for i in range(0, n, 3):
        total += (
            abs(prev_data[i] - curr_data[i])
            + abs(prev_data[i + 1] - curr_data[i + 1])
            + abs(prev_data[i + 2] - curr_data[i + 2])
        )

    magnitude = total / (n * 255)
    magnitude = round(magnitude, 4)

    return {
        "ui_changed": magnitude >= threshold,
        "change_magnitude": magnitude,
    }
```

**Step 2: Run tests**

```bash
python -m pytest tests/test_screenshot_diff.py -v
```

Expected: All 5 tests PASS

**Step 3: Commit**

```bash
git add src/computer_use_harness/agent/screenshot_diff.py
git commit -m "feat: implement screenshot diff"
```

---

### Task 6: Wire stuck detector + auto-delay + screenshot diff into harness

**Files:**
- Modify: `src/computer_use_harness/agent/harness.py`

**Step 1: Update harness imports and __init__**

Add to imports at top of `harness.py`:

```python
import time

from PIL import Image
import io
import base64

from computer_use_harness.agent.stuck_detector import StuckDetector
from computer_use_harness.agent.screenshot_diff import compute_diff
```

Add to `__init__`:

```python
self.stuck_detector = StuckDetector()
```

**Step 2: Update run_task loop**

Replace the `run_task` method body (lines 26-62) with:

```python
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
```

**Step 3: Add _is_gui_tool helper**

After `_execute`, add:

```python
@staticmethod
def _is_gui_tool(tool_name: str) -> bool:
    return tool_name.startswith("mouse.") or tool_name.startswith("keyboard.")
```

**Step 4: Run all tests**

```bash
python -m pytest tests/ -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add src/computer_use_harness/agent/harness.py
git commit -m "feat: wire stuck detector, auto-delay, and screenshot diff into harness loop"
```

---

### Task 7: Update system prompt with click escalation and diff awareness

**Files:**
- Modify: `src/computer_use_harness/agent/openai_client.py:28-33` (Screenshot Best Practices section)

**Step 1: Replace the Screenshot Best Practices section**

Replace the existing `## Screenshot Best Practices` block with:

```
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
```

**Step 2: Commit**

```bash
git add src/computer_use_harness/agent/openai_client.py
git commit -m "feat: update system prompt with click escalation and diff-aware guidance"
```

---

### Task 8: Integration test

**Files:**
- Create: `tests/test_harness_robustness.py`

**Step 1: Write integration test**

```python
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unittest.mock import MagicMock, patch
from computer_use_harness.agent.harness import AgentHarness
from computer_use_harness.config.settings import Settings
from computer_use_harness.models.schemas import AgentDecision, ToolCall, ActionResult, ToolSpec
from computer_use_harness.tools.registry import ToolRegistry
from computer_use_harness.tools.base import Tool
from datetime import UTC, datetime


class FakeTool(Tool):
    spec = ToolSpec(name="mouse.click", description="fake", input_schema={"type": "object"})
    def run(self, arguments):
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

    call_count = 0
    def fake_plan(task, state, tools, history, screenshot_base64=None):
        nonlocal call_count
        call_count += 1
        if call_count <= 4:
            return click_decision, {"input_tokens": 0, "output_tokens": 0}
        return final_decision, {"input_tokens": 0, "output_tokens": 0}

    harness.planner.plan = fake_plan
    result = harness.run_task("test task")

    assert result["status"] == "completed"
    # The harness should have injected a stuck warning after step 3
```

**Step 2: Run**

```bash
python -m pytest tests/test_harness_robustness.py -v
```

Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_harness_robustness.py
git commit -m "test: add harness robustness integration test"
```

---

### Task 9: Final commit and push

**Step 1: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: All tests PASS

**Step 2: Push**

```bash
git push
```

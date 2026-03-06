from __future__ import annotations

import math
from typing import Any


class StuckDetector:
    """Detects when the agent is stuck repeating ineffective actions.

    Three detection modes:
    1. Tool-level: same tool with similar args repeated N times in a row.
    2. UI-level: N consecutive screenshots show ui_changed=false after
       action steps were taken between them. This catches the common
       pattern where the agent varies tools/args but nothing actually
       changes on screen.
    3. Result-level: N consecutive tool calls return empty/failed results.
       Catches the pattern where the agent searches with different terms
       but always gets zero results.
    """

    def __init__(
        self,
        tool_threshold: int = 3,
        ui_no_change_threshold: int = 3,
        ineffective_threshold: int = 5,
        coord_tolerance: float = 50.0,
    ):
        self.tool_threshold = tool_threshold
        self.ui_no_change_threshold = ui_no_change_threshold
        self.ineffective_threshold = ineffective_threshold
        self.coord_tolerance = coord_tolerance
        self._history: list[tuple[str, dict[str, Any]]] = []
        self._consecutive_no_change: int = 0
        self._actions_since_last_screenshot: int = 0
        self._consecutive_ineffective: int = 0

    def record(self, tool: str, arguments: dict[str, Any]) -> None:
        self._history.append((tool, arguments))
        if tool != "screen.capture":
            self._actions_since_last_screenshot += 1

    def record_result(self, ok: bool, is_empty: bool) -> None:
        """Called after each tool execution with result info.

        Args:
            ok: whether the tool call succeeded
            is_empty: whether the result was effectively empty (e.g. find_element count=0)
        """
        if not ok or is_empty:
            self._consecutive_ineffective += 1
        else:
            self._consecutive_ineffective = 0

    def reset(self) -> None:
        self._history.clear()
        self._consecutive_no_change = 0
        self._actions_since_last_screenshot = 0
        self._consecutive_ineffective = 0

    def notify_ui_changed(self) -> None:
        """Called when a screenshot shows the UI actually changed."""
        self._history.clear()
        self._consecutive_no_change = 0
        self._actions_since_last_screenshot = 0
        self._consecutive_ineffective = 0

    def notify_ui_unchanged(self) -> None:
        """Called when a screenshot shows the UI did NOT change."""
        if self._actions_since_last_screenshot > 0:
            self._consecutive_no_change += 1
        self._actions_since_last_screenshot = 0

    def is_stuck(self) -> bool:
        return self._is_tool_stuck() or self._is_ui_stuck() or self._is_ineffective_stuck()

    def warning_message(self) -> str:
        if self._is_ui_stuck():
            return (
                f"WARNING: The last {self._consecutive_no_change} screenshots show NO UI change "
                f"despite actions taken between them. Your actions are having NO EFFECT. "
                f"You MUST try a fundamentally different approach NOW: "
                f"use a completely different tool, navigate to a different part of the app, "
                f"use keyboard shortcuts (Escape, Alt+Left, Tab+Enter), "
                f"or abandon this approach and find an alternative path to your goal."
            )
        if self._is_ineffective_stuck():
            return (
                f"WARNING: The last {self._consecutive_ineffective} tool calls returned empty or failed results. "
                f"Your current search/interaction strategy is NOT WORKING. "
                f"STOP searching with variations of the same approach. Instead: "
                f"take a screenshot to see what's actually on screen, "
                f"try clicking visible elements by coordinates, "
                f"use keyboard navigation (Tab, Enter, arrow keys), "
                f"or navigate to a completely different page/view."
            )
        return (
            "You have repeated a similar action {n} times without progress. "
            "Try a fundamentally different approach: different coordinates, "
            "different click type (single vs double), keyboard navigation "
            "(Tab/Enter), scrolling, or a completely different tool."
        ).format(n=self.tool_threshold)

    def _is_tool_stuck(self) -> bool:
        if len(self._history) < self.tool_threshold:
            return False
        recent = self._history[-self.tool_threshold:]
        first_tool = recent[0][0]
        if not all(t == first_tool for t, _ in recent):
            return False
        return all(self._similar(recent[0], entry) for entry in recent[1:])

    def _is_ui_stuck(self) -> bool:
        return self._consecutive_no_change >= self.ui_no_change_threshold

    def _is_ineffective_stuck(self) -> bool:
        return self._consecutive_ineffective >= self.ineffective_threshold

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

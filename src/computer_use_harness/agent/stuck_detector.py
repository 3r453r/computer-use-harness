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

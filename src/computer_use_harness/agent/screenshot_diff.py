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

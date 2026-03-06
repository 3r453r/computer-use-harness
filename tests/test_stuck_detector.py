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

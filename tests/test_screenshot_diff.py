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

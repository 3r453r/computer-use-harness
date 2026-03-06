from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from computer_use_harness.config.settings import Settings
from computer_use_harness.tools.local_tools import SystemInstallTool


def _tool() -> SystemInstallTool:
    return SystemInstallTool(Settings())


def test_spec_is_dangerous() -> None:
    assert _tool().spec.dangerous is True


def test_invalid_action() -> None:
    result = _tool().run({"action": "nope"})
    assert not result.ok
    assert "Invalid action" in result.error


def test_missing_manager() -> None:
    result = _tool().run({"action": "package", "package": "requests"})
    assert not result.ok
    assert "manager" in result.error


def test_missing_package() -> None:
    result = _tool().run({"action": "package", "manager": "pip"})
    assert not result.ok
    assert "package" in result.error


def test_unsupported_manager() -> None:
    result = _tool().run({"action": "package", "manager": "cargo", "package": "foo"})
    assert not result.ok
    assert "Unsupported manager" in result.error


def test_missing_script_path() -> None:
    result = _tool().run({"action": "script"})
    assert not result.ok
    assert "script_path" in result.error


def test_script_not_found() -> None:
    result = _tool().run({"action": "script", "script_path": "/nonexistent/setup.ps1"})
    assert not result.ok
    assert "not found" in result.error


def test_bad_script_extension() -> None:
    with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
        f.write(b"data")
        tmp = f.name
    try:
        result = _tool().run({"action": "script", "script_path": tmp})
        assert not result.ok
        assert "Unsupported script extension" in result.error
    finally:
        Path(tmp).unlink(missing_ok=True)

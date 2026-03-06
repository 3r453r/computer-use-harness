from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from computer_use_harness.config.settings import Settings


def test_fully_automated_implies_auto_approve() -> None:
    settings = Settings(fully_automated=True)
    assert settings.auto_approve_all is True


def test_fully_automated_false_by_default() -> None:
    settings = Settings()
    assert settings.fully_automated is False


def test_system_install_registered_when_fully_automated() -> None:
    from computer_use_harness.cli import build_registry

    settings = Settings(fully_automated=True)
    registry = build_registry(settings)
    names = [s.name for s in registry.specs()]
    assert "system.install" in names


def test_system_install_not_registered_by_default() -> None:
    from computer_use_harness.cli import build_registry

    settings = Settings()
    registry = build_registry(settings)
    names = [s.name for s in registry.specs()]
    assert "system.install" not in names


def test_existing_tools_unaffected_by_fully_automated() -> None:
    from computer_use_harness.cli import build_registry

    default_registry = build_registry(Settings())
    automated_registry = build_registry(Settings(fully_automated=True))
    default_names = {s.name for s in default_registry.specs()}
    automated_names = {s.name for s in automated_registry.specs()}
    assert default_names.issubset(automated_names)

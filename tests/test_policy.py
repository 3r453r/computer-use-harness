from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from computer_use_harness.config.settings import Settings
from computer_use_harness.models.schemas import ToolCall
from computer_use_harness.safety.policy import ApprovalPolicy


def test_terminal_exec_requires_approval() -> None:
    settings = Settings(auto_approve_safe=False)
    policy = ApprovalPolicy(settings)
    assert policy.requires_approval(ToolCall(tool="terminal.exec", arguments={"command": "dir"}))


def test_path_allowlist() -> None:
    settings = Settings(workspace_root='.', allowed_paths='.')
    policy = ApprovalPolicy(settings)
    assert policy.path_allowed('.')

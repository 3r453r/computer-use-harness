from __future__ import annotations

from dataclasses import dataclass

from computer_use_harness.models.schemas import ToolSpec
from computer_use_harness.tools.base import Tool


@dataclass
class ToolRegistry:
    tools: dict[str, Tool]

    def get(self, name: str) -> Tool:
        return self.tools[name]

    def specs(self) -> list[ToolSpec]:
        return [t.spec for t in self.tools.values()]

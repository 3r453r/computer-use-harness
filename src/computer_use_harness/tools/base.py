from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from computer_use_harness.models.schemas import ActionResult, ToolSpec


class Tool(ABC):
    spec: ToolSpec

    @abstractmethod
    def run(self, arguments: dict[str, Any]) -> ActionResult:
        raise NotImplementedError

from __future__ import annotations

import json
from pathlib import Path

from computer_use_harness.models.schemas import TraceEntry


class TraceRecorder:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._entries: list[TraceEntry] = []

    def append(self, entry: TraceEntry) -> None:
        self._entries.append(entry)

    def write(self, run_id: str) -> Path:
        output = self.output_dir / f"{run_id}.json"
        output.write_text(json.dumps([e.model_dump(mode="json") for e in self._entries], indent=2), encoding="utf-8")
        return output

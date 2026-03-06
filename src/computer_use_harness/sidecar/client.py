from __future__ import annotations

from typing import Any

import requests


class SidecarClient:
    def __init__(self, base_url: str, timeout_s: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def post(self, operation: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        response = requests.post(f"{self.base_url}/{operation.strip('/')}", json=payload or {}, timeout=self.timeout_s)
        response.raise_for_status()
        return response.json() if response.text else {}

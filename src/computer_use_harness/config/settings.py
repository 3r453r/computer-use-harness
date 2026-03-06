from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str = Field(default="")
    openai_model: str = Field(default="gpt-5.4")

    workspace_root: Path = Field(default=Path.cwd())
    allowed_paths: str = Field(default=".")

    traces_dir: Path = Field(default=Path(".traces"))
    logs_dir: Path = Field(default=Path(".logs"))
    screenshots_dir: Path = Field(default=Path(".artifacts/screenshots"))

    dry_run: bool = Field(default=False)
    auto_approve_safe: bool = Field(default=True)
    auto_approve_all: bool = Field(default=False)

    sidecar_base_url: str = Field(default="http://127.0.0.1:47901")
    sidecar_timeout_s: float = Field(default=5.0)

    max_steps: int = Field(default=15)
    tool_timeout_s: float = Field(default=20.0)
    gui_action_delay_s: float = Field(default=1.5)

    price_input_per_m: float = Field(default=2.50)
    price_output_per_m: float = Field(default=10.00)

    @property
    def allowed_path_list(self) -> list[Path]:
        return [(self.workspace_root / raw.strip()).resolve() for raw in self.allowed_paths.split(",") if raw.strip()]

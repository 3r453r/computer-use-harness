from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolSpec(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any]
    dangerous: bool = False


class ToolCall(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None


class ActionResult(BaseModel):
    tool: str
    ok: bool
    output: Any = None
    error: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    ended_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class AgentDecision(BaseModel):
    kind: Literal["tool_call", "final"]
    message: str | None = None
    tool_call: ToolCall | None = None


class StepUsage(BaseModel):
    step: int
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float = 0.0


class RunUsage(BaseModel):
    steps: list[StepUsage] = Field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cost: float = 0.0


class TraceEntry(BaseModel):
    step: int
    task: str
    decision: AgentDecision
    result: ActionResult | None = None
    ts: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))

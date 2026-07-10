"""Typed models for planning, execution, and traces."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class PlanStep:
    """One planned action inside an emote execution."""

    action_name: str
    actor: str
    params: dict[str, Any]
    verification_hint: str


@dataclass(frozen=True)
class EmotePlan:
    """High-level plan for a single emote execution."""

    emote_name: str
    canonical_name: str
    steps: list[PlanStep]


@dataclass
class StepTrace:
    """Execution record for one step."""

    action_name: str
    params: dict[str, Any]
    status: str
    duration_ms: int
    snapshot: dict[str, Any]
    verification: dict[str, Any]
    error: str | None = None
    actor: str = ""
    attempt: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionTrace:
    """Whole-run execution trace."""

    run_id: str
    emote_name: str
    canonical_name: str
    dry_run: bool
    intensity: str
    repeat: int
    steps: list[StepTrace] = field(default_factory=list)
    final_status: str = "pending"
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["steps"] = [step.to_dict() for step in self.steps]
        return data


@dataclass(frozen=True)
class ActionResult:
    """Result returned by adapters and function-layer actions."""

    success: bool
    status: str
    snapshot: dict[str, Any]
    verification: dict[str, Any]
    error: str | None = None


@dataclass(frozen=True)
class RunResult:
    """Top-level service return value."""

    success: bool
    status: str
    trace_path: str
    trace: dict[str, Any]
    error: str | None = None

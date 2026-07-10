"""Deterministic local agent loop."""

from __future__ import annotations

import time
from typing import Callable

from .models import ExecutionTrace, StepTrace
from .trace import TraceRecorder
from ..motions.emote_library import build_plan


class AgentLoop:
    """Runs interpret -> plan -> act -> verify for one emote request."""

    def __init__(
        self,
        body_executor: Callable[[str, str], object],
        hand_executor: Callable[[str, str, str], object],
        go_idle: Callable[[], object],
        stop_motion: Callable[[], None],
        max_retries: int = 1,
    ) -> None:
        self.body_executor = body_executor
        self.hand_executor = hand_executor
        self.go_idle = go_idle
        self.stop_motion = stop_motion
        self.max_retries = max_retries

    def run(
        self,
        emote_name: str,
        intensity: str,
        repeat: int,
        dry_run: bool,
        recorder: TraceRecorder,
    ) -> tuple[bool, str | None]:
        """Execute the plan and stream structured trace data."""

        plan = build_plan(emote_name, intensity)
        recorder.trace.canonical_name = plan.canonical_name
        for _ in range(repeat):
            for step in plan.steps:
                if dry_run:
                    recorder.add_step(
                        StepTrace(
                            action_name=step.action_name,
                            actor=step.actor,
                            params=step.params,
                            status="dry_run",
                            duration_ms=0,
                            snapshot={"planned": True},
                            verification={"hint": step.verification_hint, "dry_run": True},
                        )
                    )
                    continue
                last_error = None
                for attempt in range(1, self.max_retries + 2):
                    started_at = time.perf_counter()
                    if step.actor == "body":
                        result = self.body_executor(step.params["body_action"], step.params["intensity"])
                    else:
                        combined = []
                        child_success = True
                        child_error = None
                        for hand in step.params["hands"]:
                            child = self.hand_executor(hand, step.params["gesture"], step.params["intensity"])
                            combined.append(child)
                            if not child.success and child_error is None:
                                child_success = False
                                child_error = child.error
                        result = _merge_hand_results(step, combined, child_success, child_error)
                    duration_ms = int((time.perf_counter() - started_at) * 1000)
                    recorder.add_step(
                        StepTrace(
                            action_name=step.action_name,
                            actor=step.actor,
                            params=step.params,
                            status=result.status,
                            duration_ms=duration_ms,
                            snapshot=result.snapshot,
                            verification=result.verification,
                            error=result.error,
                            attempt=attempt,
                        )
                    )
                    if result.success:
                        break
                    last_error = result.error or f"{step.action_name} failed"
                else:
                    last_error = last_error or f"{step.action_name} failed"
                if last_error and recorder.trace.steps[-1].status != "success":
                    self.stop_motion()
                    idle_result = self.go_idle()
                    recorder.add_step(
                        StepTrace(
                            action_name="body_idle",
                            actor="body",
                            params={"recovery": True},
                            status=idle_result.status,
                            duration_ms=0,
                            snapshot=idle_result.snapshot,
                            verification=idle_result.verification,
                            error=idle_result.error,
                        )
                    )
                    return False, last_error
        return True, None


def _merge_hand_results(step, results, success: bool, error: str | None):
    """Combine per-hand results into one action result-like object."""

    from .models import ActionResult

    snapshot = {
        "gesture_name": step.params["gesture"],
        "hands": [item.snapshot for item in results],
    }
    verification = {
        "hand_enabled": any(item.verification.get("hand_enabled", False) for item in results),
        "state_available": all(item.verification.get("state_available", False) for item in results if item.status != "skipped"),
    }
    status = "success" if success else "failed"
    return ActionResult(
        success=success,
        status=status,
        snapshot=snapshot,
        verification=verification,
        error=error,
    )

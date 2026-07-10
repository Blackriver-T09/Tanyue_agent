"""Trace capture and persistence."""

from __future__ import annotations

import json
from pathlib import Path

from .models import ExecutionTrace, StepTrace


class TraceRecorder:
    """Accumulates step traces and persists them as JSON."""

    def __init__(self, trace: ExecutionTrace, output_dir: Path) -> None:
        self.trace = trace
        self.output_dir = output_dir

    def add_step(self, step: StepTrace) -> None:
        self.trace.steps.append(step)

    def finish(self, status: str, error: str | None = None) -> str:
        self.trace.final_status = status
        self.trace.error = error
        self.output_dir.mkdir(parents=True, exist_ok=True)
        trace_path = self.output_dir / f"{self.trace.run_id}.json"
        trace_path.write_text(
            json.dumps(self.trace.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(trace_path)

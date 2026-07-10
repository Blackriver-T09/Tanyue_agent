from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Protocol


class EvidenceLevel(str, Enum):
    MOCK = "mock"
    SIMULATED = "simulated"
    REAL_SOFTWARE = "real_software"
    REAL_EXTERNAL = "real_external"
    REAL_ROBOT = "real_robot"
    PRODUCTION = "production"


@dataclass(frozen=True)
class ObservationEvent:
    event_id: str
    trace_id: str
    timestamp: str
    stage: str
    evidence_level: EvidenceLevel
    payload: dict[str, Any]

    @classmethod
    def create(
        cls,
        *,
        trace_id: str,
        stage: str,
        evidence_level: EvidenceLevel,
        payload: dict[str, Any],
    ) -> "ObservationEvent":
        return cls(
            event_id=str(uuid.uuid4()),
            trace_id=trace_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            stage=stage,
            evidence_level=evidence_level,
            payload=dict(payload),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "trace_id": self.trace_id,
            "timestamp": self.timestamp,
            "stage": self.stage,
            "evidence_level": self.evidence_level.value,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ObservationEvent":
        return cls(
            event_id=str(payload["event_id"]),
            trace_id=str(payload["trace_id"]),
            timestamp=str(payload["timestamp"]),
            stage=str(payload["stage"]),
            evidence_level=EvidenceLevel(payload["evidence_level"]),
            payload=dict(payload.get("payload") or {}),
        )


class ObservationRecorder(Protocol):
    def record(self, event: ObservationEvent) -> None: ...

    def list_events(self, trace_id: str | None = None) -> list[ObservationEvent]: ...


class InMemoryObservationRecorder:
    def __init__(self) -> None:
        self._events: list[ObservationEvent] = []
        self._lock = threading.Lock()

    def record(self, event: ObservationEvent) -> None:
        with self._lock:
            self._events.append(event)

    def list_events(self, trace_id: str | None = None) -> list[ObservationEvent]:
        with self._lock:
            events = list(self._events)
        if trace_id is None:
            return events
        return [event for event in events if event.trace_id == trace_id]


class JsonlObservationRecorder:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def record(self, event: ObservationEvent) -> None:
        line = json.dumps(event.to_dict(), ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    def list_events(self, trace_id: str | None = None) -> list[ObservationEvent]:
        if not self.path.is_file():
            return []
        with self._lock:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        events = [ObservationEvent.from_dict(json.loads(line)) for line in lines if line]
        if trace_id is None:
            return events
        return [event for event in events if event.trace_id == trace_id]

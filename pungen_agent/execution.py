from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Protocol

from .action_library import load_action_library
from .hardware_adapter import HardwareAdapterError, build_hardware_command
from .observation import (
    EvidenceLevel,
    InMemoryObservationRecorder,
    ObservationEvent,
    ObservationRecorder,
)


class ExecutionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExecutionRequest:
    action_id: str
    intensity: float
    duration_s: float
    idempotency_key: str
    trace_id: str
    targets: tuple[str, ...] = ("unitree_body", "robot_arm", "dexterous_hand")


class ExecutionAdapter(Protocol):
    name: str
    evidence_level: EvidenceLevel

    def execute(self, command: dict[str, Any]) -> dict[str, Any]: ...


class ExecutionModule:
    def __init__(
        self,
        *,
        adapters: list[ExecutionAdapter],
        recorder: ObservationRecorder | None = None,
        action_library: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._adapters = {adapter.name: adapter for adapter in adapters}
        if len(self._adapters) != len(adapters):
            raise ValueError("Execution adapter names must be unique.")
        self._recorder = recorder or InMemoryObservationRecorder()
        self._action_library = action_library or load_action_library()
        self._results: dict[tuple[str, str], dict[str, Any]] = {}
        self._request_fingerprints: dict[tuple[str, str], tuple[Any, ...]] = {}
        self._lock = threading.Lock()

    @property
    def recorder(self) -> ObservationRecorder:
        return self._recorder

    def describe_adapters(self) -> list[dict[str, str]]:
        return [
            {
                "name": name,
                "evidence_level": EvidenceLevel(adapter.evidence_level).value,
            }
            for name, adapter in sorted(self._adapters.items())
        ]

    def execute(
        self,
        request: ExecutionRequest,
        *,
        adapter_name: str,
    ) -> dict[str, Any]:
        cache_key = (adapter_name, request.idempotency_key)
        fingerprint = (
            request.action_id,
            request.intensity,
            request.duration_s,
            request.targets,
        )
        with self._lock:
            cached = self._results.get(cache_key)
            if cached is not None:
                if self._request_fingerprints[cache_key] != fingerprint:
                    self._reject(
                        request,
                        "Idempotency conflict: key was already used for a different request.",
                    )
                return dict(cached)

            adapter = self._adapters.get(adapter_name)
            if adapter is None:
                self._reject(request, f"Unknown execution adapter: {adapter_name}")
            if request.action_id not in self._action_library:
                self._reject(request, f"Unknown action_id: {request.action_id}")

            evidence_level = EvidenceLevel(adapter.evidence_level)
            action_spec = self._action_library[request.action_id]
            action_payload = {
                "action_id": request.action_id,
                "intensity": request.intensity,
                "duration_s": request.duration_s,
                "safety": action_spec.get("safety"),
            }
            try:
                command = build_hardware_command(
                    action_payload,
                    targets=list(request.targets),
                )
            except HardwareAdapterError as exc:
                self._reject(request, str(exc))

            self._record(
                request,
                "execution_requested",
                evidence_level,
                {
                    "adapter": adapter_name,
                    "action_id": request.action_id,
                    "idempotency_key": request.idempotency_key,
                },
            )
            try:
                adapter_result = adapter.execute(command)
            except Exception as exc:
                self._record(
                    request,
                    "execution_failed",
                    evidence_level,
                    {"adapter": adapter_name, "error_type": type(exc).__name__},
                )
                raise ExecutionError(f"Execution adapter failed: {type(exc).__name__}") from exc

            result = {
                **adapter_result,
                "command": command,
                "trace_id": request.trace_id,
                "idempotency_key": request.idempotency_key,
                "evidence_level": evidence_level.value,
            }
            self._record(request, "execution_result", evidence_level, result)
            self._results[cache_key] = dict(result)
            self._request_fingerprints[cache_key] = fingerprint
            return result

    def _reject(self, request: ExecutionRequest, message: str) -> None:
        self._record(
            request,
            "execution_rejected",
            EvidenceLevel.REAL_SOFTWARE,
            {"action_id": request.action_id, "reason": message},
        )
        raise ExecutionError(message)

    def _record(
        self,
        request: ExecutionRequest,
        stage: str,
        evidence_level: EvidenceLevel,
        payload: dict[str, Any],
    ) -> None:
        self._recorder.record(
            ObservationEvent.create(
                trace_id=request.trace_id,
                stage=stage,
                evidence_level=evidence_level,
                payload=payload,
            )
        )

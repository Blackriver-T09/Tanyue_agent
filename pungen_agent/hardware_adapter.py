from __future__ import annotations

from typing import Any

from .action_library import load_action_library


DEFAULT_TARGETS = ("unitree_body", "robot_arm", "dexterous_hand")


class HardwareAdapterError(ValueError):
    pass


def build_hardware_command(
    action_payload: dict[str, Any],
    targets: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    if not isinstance(action_payload, dict):
        raise HardwareAdapterError("action payload must be an object.")

    action_id = action_payload.get("action_id") or action_payload.get("arm_action")
    if not isinstance(action_id, str) or not action_id.strip():
        raise HardwareAdapterError("action payload must include action_id or arm_action.")
    action_id = action_id.strip()

    action_spec = load_action_library().get(action_id, {})
    safety = action_payload.get("safety") or action_spec.get("safety")
    if safety != "safe_no_contact":
        raise HardwareAdapterError(
            "Only safe_no_contact actions can be sent to the hardware bridge."
        )
    if not action_spec:
        raise HardwareAdapterError(f"Unknown action_id: {action_id}")

    intensity = _bounded_float(
        action_payload.get("intensity", action_spec.get("recommended_intensity", 0.2)),
        minimum=0.0,
        maximum=1.0,
    )
    duration_s = _bounded_float(
        action_payload.get("duration_s", action_spec.get("duration_s", 1.0)),
        minimum=0.1,
        maximum=30.0,
    )
    parameters = dict(action_spec.get("parameters") or {})
    supplied_parameters = action_payload.get("parameters")
    if isinstance(supplied_parameters, dict):
        parameters.update(supplied_parameters)

    selected_targets = tuple(targets or DEFAULT_TARGETS)
    return {
        "protocol_version": "pungen-hardware/v0",
        "action_id": action_id,
        "safety": safety,
        "execution_mode": "validated_ready",
        "motion": {
            "primitive": action_id,
            "label": action_spec.get("label", action_id),
            "workspace": action_payload.get("target") or "performer_space",
            "intensity": intensity,
            "duration_s": duration_s,
            "line": action_payload.get("line") or "",
            "parameters": parameters,
        },
        "targets": [
            _target_command(device, action_id, intensity, duration_s, parameters)
            for device in selected_targets
        ],
    }


def _target_command(
    device: str,
    action_id: str,
    intensity: float,
    duration_s: float,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    common = {
        "device": device,
        "enabled": True,
        "duration_s": duration_s,
    }
    if device == "unitree_body":
        return {
            **common,
            "mode": "hold_position",
            "safety_envelope": "no_locomotion",
        }
    if device == "robot_arm":
        return {
            **common,
            "mode": "named_primitive",
            "primitive": action_id,
            "intensity": intensity,
            "parameters": parameters,
        }
    if device == "dexterous_hand":
        return {
            **common,
            "mode": "expressive_pose",
            "pose": parameters.get("end_pose", "neutral"),
            "intensity": intensity,
        }
    return {
        **common,
        "mode": "custom_bridge",
        "primitive": action_id,
        "intensity": intensity,
    }


def _bounded_float(value: Any, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise HardwareAdapterError("motion values must be numeric.") from exc
    return round(max(minimum, min(maximum, number)), 3)


class DryRunHardwareAdapter:
    name = "dry_run"

    @property
    def evidence_level(self):
        from .observation import EvidenceLevel

        return EvidenceLevel.SIMULATED

    def execute(self, command: dict[str, Any]) -> dict[str, Any]:
        if command.get("protocol_version") != "pungen-hardware/v0":
            raise HardwareAdapterError("command must use pungen-hardware/v0.")
        return {
            "protocol_version": "pungen-hardware-result/v0",
            "adapter": self.name,
            "status": "accepted",
            "executed": False,
            "action_id": command.get("action_id"),
            "target_count": len(command.get("targets") or []),
        }

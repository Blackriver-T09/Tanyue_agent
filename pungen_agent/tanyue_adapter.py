from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable
from urllib import request

from .hardware_adapter import HardwareAdapterError
from .observation import EvidenceLevel


@dataclass(frozen=True)
class TanyueMotionMapping:
    motion: str
    fidelity: str
    note: str = ""


_MOTION_MAP = {
    "cover_face_then_turn_away": TanyueMotionMapping(
        "talking_on_phone",
        "approximate",
        "当前 Tanyue 清单没有精确捂脸动作；该动作仅让手靠近脸，转身仍需新增 FBX。",
    ),
    "slow_point_then_retreat": TanyueMotionMapping("pointing", "approximate", "不包含后退段。"),
    "rhythm_shake_then_pose": TanyueMotionMapping("dancing", "approximate"),
    "sharp_point_then_pause": TanyueMotionMapping("pointing_forward", "exact"),
    "dramatic_stop": TanyueMotionMapping("standing", "approximate"),
    "recoil_then_salute": TanyueMotionMapping("salute", "approximate", "不包含后仰段。"),
    "dramatic_retreat": TanyueMotionMapping("catwalk_idle_to_twist_r", "approximate"),
    "ward_off_push": TanyueMotionMapping("waving", "approximate"),
    "confused_scan": TanyueMotionMapping("standing", "approximate"),
    "salute_hold": TanyueMotionMapping("salute", "exact"),
    "shrug_then_wave": TanyueMotionMapping("waving", "approximate"),
    "elegant_penguin_pose": TanyueMotionMapping("dancing", "approximate"),
    "imperial_small_wave": TanyueMotionMapping("waving", "exact"),
    "voice_only_nod": TanyueMotionMapping("standing", "approximate"),
    "accordion_gesture": TanyueMotionMapping("dancing", "approximate"),
    "idle_listen": TanyueMotionMapping("standing", "exact"),
}


def map_pungen_action_to_tanyue(action_id: str) -> TanyueMotionMapping:
    return _MOTION_MAP.get(
        action_id,
        TanyueMotionMapping("standing", "fallback", f"Tanyue 尚无 {action_id} 的动作映射。"),
    )


Transport = Callable[[str, dict[str, Any], float], dict[str, Any]]


def _http_transport(url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    http_request = request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with request.urlopen(http_request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


class TanyueCharacterAdapter:
    """Deliver canonical PunGen actions to Tanyue's local Character Bridge.

    A bridge acknowledgement proves external software delivery only. It does not
    prove that the browser loaded the VRM/FBX asset or that a robot moved.
    """

    name = "tanyue_character"
    evidence_level = EvidenceLevel.REAL_EXTERNAL

    def __init__(
        self,
        *,
        base_url: str = "http://127.0.0.1:8893",
        timeout: float = 5.0,
        transport: Transport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._transport = transport or _http_transport

    def execute(self, command: dict[str, Any]) -> dict[str, Any]:
        if command.get("protocol_version") != "pungen-hardware/v0":
            raise HardwareAdapterError("command must use pungen-hardware/v0.")
        action_id = str(command.get("action_id") or "")
        mapping = map_pungen_action_to_tanyue(action_id)
        motion = command.get("motion") or {}
        intensity = float(motion.get("intensity", 0.5))
        bridge_command = {
            "type": "batch",
            "commands": [
                {
                    "type": "setState",
                    "payload": {
                        "motionLoop": False,
                        "motionSpeed": round(0.8 + intensity * 0.4, 2),
                        "energy": intensity,
                    },
                },
                {"type": "playMotion", "motion": mapping.motion},
            ],
            "source": "pungen-agent",
            "pungenActionId": action_id,
            "motionFidelity": mapping.fidelity,
        }
        response = self._transport(
            f"{self.base_url}/api/command?wait=1",
            bridge_command,
            self.timeout,
        )
        if not response.get("ok"):
            raise HardwareAdapterError("Tanyue Character Bridge rejected the command.")
        acknowledgement = response.get("ack")
        browser_applied = bool(
            isinstance(acknowledgement, dict)
            and acknowledgement.get("ok")
            and acknowledgement.get("status") == "browser_applied"
        )
        return {
            "protocol_version": "pungen-hardware-result/v0",
            "adapter": self.name,
            "status": "browser_applied" if browser_applied else "bridge_queued_no_browser_ack",
            "executed": browser_applied,
            "action_id": action_id,
            "tanyue_motion": mapping.motion,
            "motion_fidelity": mapping.fidelity,
            "motion_note": mapping.note,
            "bridge_event_id": response.get("id"),
            "browser_ack": acknowledgement,
        }

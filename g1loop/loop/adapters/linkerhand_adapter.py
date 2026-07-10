"""LinkerHand adapter and offline fake implementation."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..agent.models import ActionResult
from ..config import DEFAULT_HAND_JOINT
from ..motions.hand_gestures import HandGesture, make_hand_library


@dataclass(frozen=True)
class LinkerHandConfig:
    """Settings for both real and fake hand adapters."""

    hand_joint: str = DEFAULT_HAND_JOINT
    can: str = "can0"
    modbus: str = "None"
    enabled: bool = True
    tolerate_missing: bool = True


class BaseLinkerHandAdapter:
    """Shared interface for hand gestures."""

    def __init__(self, config: LinkerHandConfig | None = None) -> None:
        self.config = config or LinkerHandConfig()
        self.gestures = make_hand_library()

    def initialize(self) -> None:
        raise NotImplementedError

    def shutdown(self) -> None:
        raise NotImplementedError

    def stop_motion(self) -> None:
        raise NotImplementedError

    def perform_gesture(self, hand: str, gesture_name: str, intensity: str = "medium") -> ActionResult:
        raise NotImplementedError


class FakeLinkerHandAdapter(BaseLinkerHandAdapter):
    """Offline fake hand adapter."""

    def __init__(
        self,
        enabled: bool = True,
        fail_hands: set[str] | None = None,
        config: LinkerHandConfig | None = None,
    ) -> None:
        merged = config or LinkerHandConfig(enabled=enabled)
        super().__init__(config=merged)
        self.enabled = enabled
        self.fail_hands = fail_hands or set()
        self.calls: list[dict[str, Any]] = []
        self.states: dict[str, list[int]] = {}

    def initialize(self) -> None:
        return None

    def shutdown(self) -> None:
        return None

    def stop_motion(self) -> None:
        self.calls.append({"kind": "stop_motion"})

    def perform_gesture(self, hand: str, gesture_name: str, intensity: str = "medium") -> ActionResult:
        self.calls.append({"kind": "perform_gesture", "hand": hand, "gesture_name": gesture_name, "intensity": intensity})
        if not self.enabled:
            return ActionResult(
                success=True,
                status="skipped",
                snapshot={"hand": hand, "gesture_name": gesture_name},
                verification={"hand_enabled": False, "state_available": False},
            )
        if hand in self.fail_hands:
            return ActionResult(
                success=False,
                status="failed",
                snapshot={"hand": hand, "gesture_name": gesture_name},
                verification={"hand_enabled": True, "state_available": False},
                error=f"Fake hand failure for {hand}",
            )
        gesture = self.gestures[gesture_name]
        self.states[hand] = list(gesture.pose)
        return ActionResult(
            success=True,
            status="success",
            snapshot={"hand": hand, "gesture_name": gesture_name, "state": list(gesture.pose)},
            verification={"hand_enabled": True, "state_available": True},
        )


class LinkerHandAdapter(BaseLinkerHandAdapter):
    """Thin wrapper around the LinkerHand Python SDK."""

    def __init__(self, config: LinkerHandConfig | None = None) -> None:
        super().__init__(config=config)
        self.enabled = self.config.enabled
        self._apis: dict[str, Any] = {}
        if self.enabled:
            sdk_root = Path(r"D:\Projects\tanyue\linkerhand-python-sdk")
            if str(sdk_root) not in sys.path:
                sys.path.append(str(sdk_root))
            try:
                from LinkerHand.linker_hand_api import LinkerHandApi
            except ImportError as exc:
                raise RuntimeError("LinkerHand SDK is not available") from exc
            self._api_cls = LinkerHandApi
        else:
            self._api_cls = None

    def initialize(self) -> None:
        if not self.enabled:
            return
        for hand in ("left", "right"):
            self._apis[hand] = self._api_cls(
                hand_type=hand,
                hand_joint=self.config.hand_joint,
                modbus=self.config.modbus,
                can=self.config.can,
            )

    def shutdown(self) -> None:
        self._apis.clear()

    def stop_motion(self) -> None:
        if not self.enabled:
            return
        neutral = self.gestures["neutral"]
        for hand in list(self._apis):
            try:
                api = self._apis[hand]
                api.set_speed(list(neutral.speed))
                api.finger_move(list(neutral.pose))
            except Exception:
                pass

    def perform_gesture(self, hand: str, gesture_name: str, intensity: str = "medium") -> ActionResult:
        if not self.enabled:
            return ActionResult(
                success=True,
                status="skipped",
                snapshot={"hand": hand, "gesture_name": gesture_name},
                verification={"hand_enabled": False, "state_available": False},
            )
        api = self._apis.get(hand)
        if api is None:
            raise RuntimeError(f"Hand adapter for {hand} is not initialized")
        gesture: HandGesture = self.gestures[gesture_name]
        try:
            api.set_speed(list(gesture.speed))
            api.finger_move(list(gesture.pose))
            time.sleep(gesture.hold_s)
            state = api.get_state()
            fault = api.get_fault() if hasattr(api, "get_fault") else None
        except Exception as exc:
            return ActionResult(
                success=False,
                status="failed",
                snapshot={"hand": hand, "gesture_name": gesture_name},
                verification={"hand_enabled": True, "state_available": False},
                error=str(exc),
            )
        return ActionResult(
            success=bool(state),
            status="success" if state else "failed",
            snapshot={"hand": hand, "gesture_name": gesture_name, "state": list(state) if state else [], "fault": fault},
            verification={"hand_enabled": True, "state_available": bool(state)},
            error=None if state else "empty hand state",
        )

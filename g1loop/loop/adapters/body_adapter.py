"""Body adapter implementations for fake and Unitree G1 live control."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..agent.models import ActionResult
from ..config import JOINT_GROUPS
from ..motions.body_actions import IDLE_FULL, make_body_library


def pose_distance(a: list[float], b: list[float]) -> float:
    """Return the largest absolute joint delta."""

    return max(abs(x - y) for x, y in zip(a, b))


def intensity_scales(intensity: str) -> tuple[float, float]:
    """Translate symbolic intensity into speed/hold scales."""

    mapping = {
        "low": (0.85, 1.15),
        "medium": (1.0, 1.0),
        "high": (1.15, 0.9),
    }
    return mapping.get(intensity, mapping["medium"])


@dataclass(frozen=True)
class BodyConfig:
    """Settings shared by fake and live body adapters."""

    network_interface: str = ""
    startup_wait_s: float = 1.5
    retry_count: int = 1


class BaseBodyAdapter:
    """Shared interface used by the motion layer and tests."""

    def __init__(self, config: BodyConfig | None = None) -> None:
        self.config = config or BodyConfig()
        self.body_actions = make_body_library()

    def initialize(self) -> None:
        raise NotImplementedError

    def shutdown(self) -> None:
        raise NotImplementedError

    def stop_motion(self) -> None:
        raise NotImplementedError

    def body_action(self, action_name: str, intensity: str = "medium") -> ActionResult:
        raise NotImplementedError

    def go_idle(self) -> ActionResult:
        return self.body_action("idle", intensity="medium")


class FakeBodyAdapter(BaseBodyAdapter):
    """Offline fake adapter for tests and dry runs."""

    def __init__(
        self,
        fail_actions: set[str] | None = None,
        config: BodyConfig | None = None,
    ) -> None:
        super().__init__(config=config)
        self.initialized = False
        self.fail_actions = fail_actions or set()
        self.current_joint_positions = list(IDLE_FULL)
        self.calls: list[dict[str, Any]] = []

    def initialize(self) -> None:
        self.initialized = True

    def shutdown(self) -> None:
        self.initialized = False

    def stop_motion(self) -> None:
        self.calls.append({"kind": "stop_motion"})

    def body_action(self, action_name: str, intensity: str = "medium") -> ActionResult:
        self.calls.append({"kind": "body_action", "action_name": action_name, "intensity": intensity})
        if action_name in self.fail_actions:
            return ActionResult(
                success=False,
                status="failed",
                snapshot={"target_action": action_name, "joint_positions": list(self.current_joint_positions)},
                verification={"reached_target": False, "max_error_rad": None},
                error=f"Fake failure for {action_name}",
            )
        action = self.body_actions[action_name]
        _, hold_scale = intensity_scales(intensity)
        target_positions = list(self.current_joint_positions)
        for keyframe in action.keyframes:
            target_positions = list(keyframe.positions)
            time.sleep(min((keyframe.hold_s or 0.0) * hold_scale, 0.01))
        if action.return_to_idle:
            target_positions = list(IDLE_FULL)
        self.current_joint_positions = target_positions
        return ActionResult(
            success=True,
            status="success",
            snapshot={"target_action": action_name, "joint_positions": list(self.current_joint_positions)},
            verification={"reached_target": True, "max_error_rad": 0.0},
        )


class UnitreeG1Adapter(BaseBodyAdapter):
    """Thin wrapper around Unitree G1 high-level Python SDK clients."""

    _ACTION_MAP = {
        "idle": "release arm",
        "gasp": "hands up",
        "beg": "two-hand kiss",
        "dismiss": "reject",
    }

    def __init__(self, config: BodyConfig | None = None) -> None:
        super().__init__(config=config)
        sdk_root = Path(__file__).resolve().parents[3] / "unitree_sdk2_python"
        if str(sdk_root) not in sys.path:
            sys.path.append(str(sdk_root))
        try:
            from unitree_sdk2py.core.channel import ChannelFactoryInitialize
            from unitree_sdk2py.g1.arm.g1_arm_action_client import G1ArmActionClient, action_map
            from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient
        except ImportError as exc:
            raise RuntimeError("unitree_sdk2py is not available") from exc

        self._channel_factory_initialize = ChannelFactoryInitialize
        self._arm_client_cls = G1ArmActionClient
        self._loco_client_cls = LocoClient
        self._action_map = dict(action_map)
        self._channel_ready = False
        self.arm_client = None
        self.loco_client = None

    def initialize(self) -> None:
        if not self._channel_ready:
            if self.config.network_interface:
                self._channel_factory_initialize(0, self.config.network_interface)
            else:
                self._channel_factory_initialize(0)
            self._channel_ready = True
        self.arm_client = self._arm_client_cls()
        self.arm_client.Init()
        self.loco_client = self._loco_client_cls()
        self.loco_client.Init()
        time.sleep(self.config.startup_wait_s)

    def shutdown(self) -> None:
        self.arm_client = None
        self.loco_client = None

    def stop_motion(self) -> None:
        if self.loco_client is not None:
            try:
                self.loco_client.StopMove()
            except Exception:
                pass

    def body_action(self, action_name: str, intensity: str = "medium") -> ActionResult:
        if self.arm_client is None:
            raise RuntimeError("Unitree G1 adapter is not initialized")
        mapped_action = self._ACTION_MAP.get(action_name)
        if mapped_action is None:
            return ActionResult(
                success=False,
                status="unsupported",
                snapshot={"target_action": action_name},
                verification={"sdk_status_ok": False, "mapped_action": None},
                error=f"unsupported body action: {action_name}",
            )
        action_id = self._action_map.get(mapped_action)
        if action_id is None:
            return ActionResult(
                success=False,
                status="unsupported",
                snapshot={"target_action": action_name, "mapped_action": mapped_action},
                verification={"sdk_status_ok": False, "mapped_action": mapped_action},
                error=f"Unitree action is unavailable: {mapped_action}",
            )

        speed_scale, hold_scale = intensity_scales(intensity)
        last_code: int | None = None
        for attempt in range(self.config.retry_count + 1):
            last_code = int(self.arm_client.ExecuteAction(action_id))
            if last_code == 0:
                break
            if attempt < self.config.retry_count:
                time.sleep(0.2)
        if last_code == 0 and self.loco_client is not None:
            try:
                self.loco_client.StopMove()
            except Exception:
                pass
        time.sleep(max(0.05, 0.1 * speed_scale) * hold_scale)
        return ActionResult(
            success=last_code == 0,
            status="success" if last_code == 0 else f"sdk_error:{last_code}",
            snapshot={
                "target_action": action_name,
                "mapped_action": mapped_action,
                "action_id": action_id,
                "network_interface": self.config.network_interface,
            },
            verification={"sdk_status_ok": last_code == 0, "sdk_return_code": last_code},
            error=None if last_code == 0 else f"ExecuteAction failed with code {last_code}",
        )

    def go_idle(self) -> ActionResult:
        result = self.body_action("idle", intensity="medium")
        if self.loco_client is not None:
            try:
                self.loco_client.Damp()
            except Exception:
                pass
        return result

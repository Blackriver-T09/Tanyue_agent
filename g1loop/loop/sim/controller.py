"""Group-based MuJoCo controller for Unitree G1."""

from __future__ import annotations

from dataclasses import dataclass

from .model import GROUPS, HOME_POSE, actuator_names_for_group, load_actuator_metadata, supported_groups_for_model
from .runtime import G1MujocoRuntime


@dataclass(frozen=True)
class ControlResult:
    """Result for a control command."""

    success: bool
    target: dict[str, list[float]]
    actual: dict[str, list[float]]
    supported: bool = True
    error: str | None = None


class G1MujocoController:
    """High-level controller over G1 MuJoCo actuators."""

    def __init__(self, runtime: G1MujocoRuntime) -> None:
        self.runtime = runtime
        self._mujoco = runtime._mujoco
        self.actuator_meta = load_actuator_metadata(model_path=runtime.model_path)
        self.supported_groups = supported_groups_for_model(model_path=runtime.model_path)
        self.group_to_indices: dict[str, list[int]] = {}
        self.group_to_qpos: dict[str, list[int]] = {}
        self._build_indices()

    def _build_indices(self) -> None:
        for group, actuators in self.supported_groups.items():
            actuator_indices: list[int] = []
            qpos_indices: list[int] = []
            for actuator_name in actuators:
                actuator_id = self._mujoco.mj_name2id(
                    self.runtime.model,
                    self._mujoco.mjtObj.mjOBJ_ACTUATOR,
                    actuator_name,
                )
                if actuator_id < 0:
                    raise ValueError(f"Actuator {actuator_name} not found in model")
                joint_name = self.actuator_meta[actuator_name].joint
                joint_id = self._mujoco.mj_name2id(
                    self.runtime.model,
                    self._mujoco.mjtObj.mjOBJ_JOINT,
                    joint_name,
                )
                if joint_id < 0:
                    raise ValueError(f"Joint {joint_name} not found in model")
                actuator_indices.append(actuator_id)
                qpos_indices.append(int(self.runtime.model.jnt_qposadr[joint_id]))
            self.group_to_indices[group] = actuator_indices
            self.group_to_qpos[group] = qpos_indices

    def _validate_targets(self, group: str, values: list[float]) -> list[float]:
        if group not in GROUPS:
            raise KeyError(f"Unknown group: {group}")
        if group not in self.supported_groups:
            raise ValueError(f"{group} is not supported by model {self.runtime.model_path}")
        expected = len(GROUPS[group])
        if len(values) != expected:
            raise ValueError(f"{group} expects {expected} values, got {len(values)}")
        clamped: list[float] = []
        for actuator_name, value in zip(actuator_names_for_group(group), values):
            meta = self.actuator_meta[actuator_name]
            if value < meta.ctrl_min or value > meta.ctrl_max:
                raise ValueError(
                    f"{actuator_name} target {value} outside range [{meta.ctrl_min}, {meta.ctrl_max}]"
                )
            clamped.append(float(value))
        return clamped

    def _set_group(self, group: str, values: list[float]) -> ControlResult:
        target = self._validate_targets(group, values)
        for actuator_id, value in zip(self.group_to_indices[group], target):
            self.runtime.data.ctrl[actuator_id] = value
        actual = self.get_joint_positions(group)
        return ControlResult(success=True, target={group: target}, actual={group: actual})

    def set_waist(self, joints: list[float]) -> ControlResult:
        return self._set_group("waist", joints)

    def set_left_arm(self, joints: list[float]) -> ControlResult:
        return self._set_group("left_arm", joints)

    def set_right_arm(self, joints: list[float]) -> ControlResult:
        return self._set_group("right_arm", joints)

    def get_joint_positions(self, group: str | None = None) -> dict[str, list[float]] | list[float]:
        if group is None:
            return {name: self._group_qpos(name) for name in self.supported_groups}
        return self._group_qpos(group)

    def _group_qpos(self, group: str) -> list[float]:
        if group not in self.group_to_qpos:
            raise KeyError(f"Unknown group: {group}")
        return [float(self.runtime.data.qpos[idx]) for idx in self.group_to_qpos[group]]

    def step(self, n: int = 1) -> None:
        self.runtime.step(n=n)

    def move_to_home_pose(self, step_count: int = 180) -> ControlResult:
        for group, values in HOME_POSE.items():
            if group not in self.supported_groups:
                continue
            self._set_group(group, list(values))
        self.step(step_count)
        return ControlResult(
            success=True,
            target={group: list(values) for group, values in HOME_POSE.items() if group in self.supported_groups},
            actual={group: self._group_qpos(group) for group in self.supported_groups},
        )

    def wave_left_arm(self, step_count: int = 170) -> list[ControlResult]:
        poses = [
            [1.10, 0.35, -0.25, 1.45, -0.15],
            [1.30, 0.55, -0.55, 1.70, 0.55],
            [1.30, 0.55, -0.55, 1.70, -0.55],
            [1.30, 0.55, -0.55, 1.70, 0.55],
            [1.10, 0.35, -0.25, 1.45, -0.15],
        ]
        results: list[ControlResult] = []
        for pose in poses:
            results.append(self.set_left_arm(pose))
            results.append(self._advance_and_snapshot("left_arm", step_count))
        return results

    def twist_waist(self, step_count: int = 140) -> list[ControlResult]:
        results = [
            self.set_waist([0.45]),
            self._advance_and_snapshot("waist", step_count),
            self.set_waist([-0.45]),
            self._advance_and_snapshot("waist", step_count),
            self.set_waist([0.0]),
            self._advance_and_snapshot("waist", step_count),
        ]
        return results

    def arms_open(self, step_count: int = 190) -> list[ControlResult]:
        left_target = [1.15, 0.35, -0.25, 1.25, 0.0]
        right_target = [-1.15, -0.35, 0.25, 1.25, 0.0]
        results = [
            self.set_left_arm(left_target),
            self.set_right_arm(right_target),
        ]
        self.step(step_count)
        results.append(
            ControlResult(
                success=True,
                target={"left_arm": left_target, "right_arm": right_target},
                actual={
                    "left_arm": self._group_qpos("left_arm"),
                    "right_arm": self._group_qpos("right_arm"),
                },
            )
        )
        return results

    def _advance_and_snapshot(self, group: str, step_count: int) -> ControlResult:
        self.step(step_count)
        actual = self._group_qpos(group)
        return ControlResult(success=True, target={group: actual}, actual={group: actual})

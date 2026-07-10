"""Body keyframes adapted from the G1 emote demo."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..config import JOINT_GROUPS, UPPER_BODY_GROUPS


def expand_group_positions(
    group_names: Sequence[str],
    grouped_values: dict[str, Sequence[float]],
) -> list[float]:
    flat: list[float] = []
    for group_name in group_names:
        flat.extend(grouped_values[group_name])
    return flat


@dataclass(frozen=True)
class BodyKeyframe:
    """One body motion keyframe."""

    positions: list[float]
    duration_s: float
    max_speed: float
    timeout_s: float
    hold_s: float = 0.0
    joint_groups: Sequence[str] = tuple(UPPER_BODY_GROUPS)


@dataclass(frozen=True)
class BodyAction:
    """Named body action composed of keyframes."""

    name: str
    keyframes: tuple[BodyKeyframe, ...]
    return_to_idle: bool = True


IDLE_FULL = expand_group_positions(
    JOINT_GROUPS,
    {
        "leg": [0.45, 1.18, 0.62, 0.0, 0.0],
        "head": [0.0, 0.0],
        "left_arm": [0.55, 0.35, -1.25, -1.05, 0.0, -0.55, 0.0],
        "right_arm": [-0.55, -0.35, 1.25, 1.05, 0.0, 0.55, 0.0],
    },
)
SHRINK_UPPER = expand_group_positions(
    UPPER_BODY_GROUPS,
    {
        "head": [0.05, -0.12],
        "left_arm": [0.25, 0.72, -1.70, -1.72, 0.0, -0.40, 0.0],
        "right_arm": [-0.25, -0.72, 1.70, 1.72, 0.0, 0.40, 0.0],
    },
)
GASP_UPPER = expand_group_positions(
    UPPER_BODY_GROUPS,
    {
        "head": [0.0, -0.26],
        "left_arm": [0.50, 0.48, -1.44, -1.22, 0.0, -0.18, 0.22],
        "right_arm": [-0.56, -0.60, 1.62, 1.18, 0.0, 0.12, -0.05],
    },
)
BEG_A = expand_group_positions(
    UPPER_BODY_GROUPS,
    {
        "head": [0.0, 0.22],
        "left_arm": [0.22, 0.48, -1.62, -1.50, 0.0, -0.32, 0.0],
        "right_arm": [-0.22, -0.48, 1.62, 1.50, 0.0, 0.32, 0.0],
    },
)
BEG_B = expand_group_positions(
    UPPER_BODY_GROUPS,
    {
        "head": [0.0, 0.28],
        "left_arm": [0.20, 0.54, -1.70, -1.58, 0.0, -0.28, 0.0],
        "right_arm": [-0.20, -0.54, 1.70, 1.58, 0.0, 0.28, 0.0],
    },
)
DISMISS_A = expand_group_positions(
    UPPER_BODY_GROUPS,
    {
        "head": [0.12, -0.02],
        "left_arm": [0.88, 0.08, -1.12, -0.18, 0.0, -0.95, 0.38],
        "right_arm": IDLE_FULL[14:21],
    },
)
DISMISS_B = expand_group_positions(
    UPPER_BODY_GROUPS,
    {
        "head": [0.18, -0.02],
        "left_arm": [0.68, -0.20, -0.98, -0.10, 0.0, -0.35, -0.40],
        "right_arm": IDLE_FULL[14:21],
    },
)


def make_body_library() -> dict[str, BodyAction]:
    """Return the supported first-version body actions."""

    return {
        "idle": BodyAction(
            name="idle",
            keyframes=(
                BodyKeyframe(
                    positions=IDLE_FULL,
                    duration_s=0.30,
                    max_speed=0.30,
                    timeout_s=12.0,
                    hold_s=0.0,
                    joint_groups=tuple(JOINT_GROUPS),
                ),
            ),
            return_to_idle=False,
        ),
        "gasp": BodyAction(
            name="gasp",
            keyframes=(
                BodyKeyframe(SHRINK_UPPER, 0.30, 0.80, 4.0, 0.05),
                BodyKeyframe(GASP_UPPER, 0.35, 0.95, 4.0, 1.2),
            ),
        ),
        "beg": BodyAction(
            name="beg",
            keyframes=(
                BodyKeyframe(BEG_A, 0.55, 0.55, 6.0, 0.18),
                BodyKeyframe(BEG_B, 0.20, 0.40, 4.0, 0.18),
                BodyKeyframe(BEG_A, 0.20, 0.40, 4.0, 1.0),
            ),
        ),
        "dismiss": BodyAction(
            name="dismiss",
            keyframes=(
                BodyKeyframe(DISMISS_A, 0.50, 0.60, 6.0, 0.10),
                BodyKeyframe(DISMISS_B, 0.25, 0.90, 4.0, 0.05),
                BodyKeyframe(DISMISS_A, 0.25, 0.90, 4.0, 0.05),
                BodyKeyframe(DISMISS_B, 0.25, 0.90, 4.0, 0.05),
                BodyKeyframe(DISMISS_A, 0.25, 0.90, 4.0, 0.20),
            ),
        ),
    }

"""LinkerHand gesture presets."""

from __future__ import annotations

from dataclasses import dataclass

from ..config import DEFAULT_HAND_SPEED, DEFAULT_NEUTRAL_POSE, DEFAULT_OPEN_PALM_POSE


@dataclass(frozen=True)
class HandGesture:
    """Named hand gesture preset."""

    name: str
    speed: list[int]
    pose: list[int]
    hold_s: float = 0.2


def make_hand_library() -> dict[str, HandGesture]:
    """Return first-version gesture presets."""

    return {
        "open_palm": HandGesture(
            name="open_palm",
            speed=list(DEFAULT_HAND_SPEED),
            pose=list(DEFAULT_OPEN_PALM_POSE),
            hold_s=0.2,
        ),
        "neutral": HandGesture(
            name="neutral",
            speed=list(DEFAULT_HAND_SPEED),
            pose=list(DEFAULT_NEUTRAL_POSE),
            hold_s=0.1,
        ),
    }

"""Static mapping from abstract emotes to executable steps."""

from __future__ import annotations

from ..agent.models import EmotePlan, PlanStep

ALIASES: dict[str, str] = {
    "惊讶": "惊讶",
    "gasp": "惊讶",
    "surprised": "惊讶",
    "求饶": "求饶",
    "beg": "求饶",
    "plead": "求饶",
    "轻蔑": "轻蔑",
    "dismiss": "轻蔑",
    "disdain": "轻蔑",
}


def normalize_emote(name: str) -> str:
    """Map user input into one canonical supported emote."""

    key = name.strip().lower()
    if name.strip() in ALIASES:
        return ALIASES[name.strip()]
    if key in ALIASES:
        return ALIASES[key]
    raise KeyError(f"Unsupported emote: {name}")


def list_emotes() -> list[str]:
    """List the canonical emotes supported by v1."""

    return ["惊讶", "求饶", "轻蔑"]


def build_plan(name: str, intensity: str) -> EmotePlan:
    """Build a fixed emote plan from the canonical name."""

    canonical = normalize_emote(name)
    if canonical == "惊讶":
        steps = [
            PlanStep(
                action_name="body_gasp",
                actor="body",
                params={"body_action": "gasp", "intensity": intensity},
                verification_hint="upper body reaches gasp keyframes",
            ),
            PlanStep(
                action_name="hand_open_palm",
                actor="hand",
                params={"gesture": "open_palm", "hands": ["left", "right"], "intensity": intensity},
                verification_hint="hand state available after open palm",
            ),
        ]
    elif canonical == "求饶":
        steps = [
            PlanStep(
                action_name="body_beg",
                actor="body",
                params={"body_action": "beg", "intensity": intensity},
                verification_hint="upper body reaches beg keyframes",
            ),
            PlanStep(
                action_name="hand_open_palm",
                actor="hand",
                params={"gesture": "open_palm", "hands": ["left", "right"], "intensity": intensity},
                verification_hint="hand state available after open palm",
            ),
        ]
    else:
        steps = [
            PlanStep(
                action_name="body_dismiss",
                actor="body",
                params={"body_action": "dismiss", "intensity": intensity},
                verification_hint="upper body reaches dismiss keyframes",
            ),
            PlanStep(
                action_name="hand_open_palm",
                actor="hand",
                params={"gesture": "open_palm", "hands": ["left"], "intensity": intensity},
                verification_hint="left hand state available after open palm",
            ),
        ]
    return EmotePlan(emote_name=name, canonical_name=canonical, steps=steps)

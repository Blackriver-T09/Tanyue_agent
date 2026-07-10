from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Meme:
    id: str
    name: str
    aliases: tuple[str, ...]
    symbols: tuple[str, ...]
    contexts: tuple[str, ...]
    emotion_deltas: dict[str, float]
    actions: tuple[str, ...]
    lines: tuple[str, ...]
    explanation: str
    response_mode: str = "small_motion"
    asset_id: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Meme":
        return cls(
            id=str(payload["id"]),
            name=str(payload["name"]),
            aliases=tuple(payload.get("aliases", [])),
            symbols=tuple(payload.get("symbols", [])),
            contexts=tuple(payload.get("contexts", [])),
            emotion_deltas={
                str(key): float(value)
                for key, value in payload.get("emotion_deltas", {}).items()
            },
            actions=tuple(payload.get("actions", [])),
            lines=tuple(payload.get("lines", [])),
            explanation=str(payload.get("explanation", "")),
            response_mode=str(payload.get("response_mode", "small_motion")),
            asset_id=str(payload.get("asset_id", "")),
        )

from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_DIMENSIONS = {
    "fake_grievance": 0.0,
    "jealousy": 0.0,
    "mocking": 0.0,
    "fake_angry": 0.0,
    "playful": 0.0,
    "dramatic": 0.0,
    "affection": 0.0,
}


class EmotionStateMachine:
    def __init__(self, decay: float = 0.85):
        self.decay = decay
        self.heart_value = 50.0
        self.dimensions = deepcopy(DEFAULT_DIMENSIONS)

    def apply(self, deltas: dict[str, float] | None) -> dict[str, Any]:
        deltas = deltas or {}
        for key in self.dimensions:
            self.dimensions[key] = self._clamp(self.dimensions[key] * self.decay)

        for key, value in deltas.items():
            if key == "heart":
                self.heart_value = max(0.0, min(100.0, self.heart_value + value * 20))
                continue
            self.dimensions.setdefault(key, 0.0)
            self.dimensions[key] = self._clamp(self.dimensions[key] + value)

        return self.to_dict()

    def to_dict(self) -> dict[str, Any]:
        dominant_state = max(self.dimensions, key=self.dimensions.get)
        if self.dimensions[dominant_state] < 0.15:
            dominant_state = "neutral"
        return {
            "dominant_state": dominant_state,
            "heart_value": round(self.heart_value, 1),
            "dimensions": {key: round(value, 3) for key, value in self.dimensions.items()},
        }

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

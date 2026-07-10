from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from .action_planner import ActionPlanner
from .emotion import EmotionStateMachine
from .recognizer import MemeRecognizer, load_meme_library


LLMInference = Callable[[str, str], str]


class PunGenAgent:
    def __init__(
        self,
        recognizer: MemeRecognizer,
        emotion_machine: EmotionStateMachine | None = None,
        action_planner: ActionPlanner | None = None,
        llm_inference: LLMInference | None = None,
    ):
        self.recognizer = recognizer
        self.emotion_machine = emotion_machine or EmotionStateMachine()
        self.action_planner = action_planner or ActionPlanner()
        self.llm_inference = llm_inference

    @classmethod
    def from_default_library(
        cls,
        llm_inference: LLMInference | None = None,
    ) -> "PunGenAgent":
        return cls(MemeRecognizer(load_meme_library()), llm_inference=llm_inference)

    def respond(self, text: str, scene: str | None = None) -> dict[str, Any]:
        recognition = self.recognizer.recognize(text, scene=scene)
        emotion = self.emotion_machine.apply(recognition.get("emotion_deltas"))
        action = self.action_planner.plan(recognition, emotion)
        payload = {
            "protocol_version": "pungen-agent/v0",
            "input": {
                "text": text,
                "scene": scene or "",
            },
            "recognition": recognition,
            "emotion": emotion,
            "action": action,
        }
        if self.llm_inference:
            payload["llm_annotation"] = self._llm_annotation(payload)
        return payload

    def _llm_annotation(self, payload: dict[str, Any]) -> dict[str, str]:
        system_prompt = (
            "You annotate meme recognition for an embodied demo. "
            "Return a concise Chinese explanation of why the meme fits the scene "
            "and how the robot should perform it. Do not mention secrets or APIs."
        )
        user_input = json.dumps(
            {
                "input": payload["input"],
                "recognition": {
                    "meme_id": payload["recognition"].get("meme_id"),
                    "meme_name": payload["recognition"].get("meme_name"),
                    "match_type": payload["recognition"].get("match_type"),
                    "matched_symbols": payload["recognition"].get("matched_symbols"),
                    "matched_aliases": payload["recognition"].get("matched_aliases"),
                    "reason": payload["recognition"].get("reason"),
                },
                "emotion": {
                    "dominant_state": payload["emotion"].get("dominant_state"),
                    "heart_value": payload["emotion"].get("heart_value"),
                },
                "action": payload["action"],
            },
            ensure_ascii=False,
        )
        try:
            content = self.llm_inference(system_prompt, user_input)
        except Exception as exc:
            return {"status": "error", "content": str(exc)}
        return {"status": "ok", "content": content}

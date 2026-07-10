from __future__ import annotations

import threading
from typing import Any, Protocol

from .agent import PunGenAgent


class VoiceOutput(Protocol):
    def speak(self, text: str, *, voice_pack: str) -> dict[str, Any]: ...


class MotionOutput(Protocol):
    def perform(self, action: dict[str, Any]) -> dict[str, Any]: ...


class MusicOutput(Protocol):
    def play(self, track_id: str) -> dict[str, Any]: ...


class PunGenUnitreeRuntime:
    """One triggered ASR turn from cultural recognition to Unitree outputs.

    This runtime implements the demo's "understand meme" and "perform meme"
    stages. Proactive timing/insertion is intentionally outside this class.
    """

    def __init__(
        self,
        *,
        agent: PunGenAgent,
        voice: VoiceOutput,
        motion: MotionOutput,
        music: MusicOutput,
    ) -> None:
        self.agent = agent
        self.voice = voice
        self.motion = motion
        self.music = music
        self._turn_lock = threading.Lock()

    def handle_hearing_event(self, event: dict[str, Any]) -> dict[str, Any] | None:
        if event.get("type") != "transcription" or not event.get("final"):
            return None
        text = str(event.get("text") or "").strip()
        if not text:
            return None
        return self.handle_transcript(text)

    def handle_transcript(self, text: str, scene: str = "unitree_live_demo") -> dict[str, Any]:
        if not self._turn_lock.acquire(blocking=False):
            return {"status": "busy", "input": text}
        try:
            response = self.agent.respond(text, scene=scene)
            recognition = response["recognition"]
            action = response["action"]
            meme_id = recognition.get("meme_id")
            if not meme_id:
                return {
                    "status": "no_meme",
                    "input": text,
                    "meme_id": None,
                    "action_id": "idle_listen",
                    "agent_response": response,
                }

            line = action.get("line") or recognition.get("line") or ""
            voice_result = self.voice.speak(line, voice_pack=str(meme_id)) if line else None
            music_result = None
            if action.get("action_id") == "ymca_dance":
                music_result = self.music.play("ymca")
            motion_result = self.motion.perform(action)
            return {
                "status": "handled",
                "input": text,
                "meme_id": meme_id,
                "confidence": recognition.get("confidence"),
                "line": line,
                "action_id": action.get("action_id"),
                "voice": voice_result,
                "music": music_result,
                "motion": motion_result,
                "agent_response": response,
            }
        finally:
            self._turn_lock.release()

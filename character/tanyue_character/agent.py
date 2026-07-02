from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import request


@dataclass(frozen=True)
class CharacterAgentConfig:
    """HTTP endpoint for the local browser bridge."""

    base_url: str = "http://127.0.0.1:8893"
    timeout: float = 5.0


class CharacterAgent:
    """Small Python client for controlling the browser VRM character.

    The browser page subscribes to the bridge with EventSource. This client posts
    commands to the bridge, which then broadcasts them to the active page.
    """

    def __init__(self, config: CharacterAgentConfig | None = None) -> None:
        self.config = config or CharacterAgentConfig()

    def health(self) -> dict[str, Any]:
        return self._get_json("/health")

    def command(self, command_type: str, **payload: Any) -> dict[str, Any]:
        command = {"type": command_type, **payload}
        return self._post_json("/api/command", command)

    def batch(self, commands: list[dict[str, Any]]) -> dict[str, Any]:
        return self.command("batch", commands=commands)

    def set_state(self, **state: Any) -> dict[str, Any]:
        return self.command("setState", payload=state)

    def set_expression(self, expression: str) -> dict[str, Any]:
        return self.command("setExpression", expression=expression)

    def set_pose(self, pose: str) -> dict[str, Any]:
        return self.command("setPose", pose=pose)

    def play_motion(self, motion: str, *, loop: bool | None = None, speed: float | None = None) -> dict[str, Any]:
        commands: list[dict[str, Any]] = []
        state: dict[str, Any] = {}
        if loop is not None:
            state["motionLoop"] = loop
        if speed is not None:
            state["motionSpeed"] = speed
        if state:
            commands.append({"type": "setState", "payload": state})
        commands.append({"type": "playMotion", "motion": motion})
        if len(commands) == 1:
            return self.command("playMotion", motion=motion)
        return self.batch(commands)

    def stop_motion(self) -> dict[str, Any]:
        return self.command("stopMotion")

    def set_mouth(self, *, aa: float = 0.0, oh: float = 0.0) -> dict[str, Any]:
        return self.command("setMouth", aa=aa, oh=oh)

    def set_lip_sync_level(self, level: float) -> dict[str, Any]:
        return self.command("setLipSyncLevel", level=level)

    def play_audio_url(self, url: str) -> dict[str, Any]:
        return self.command("playAudioUrl", url=url)

    def start_microphone_lip_sync(self) -> dict[str, Any]:
        return self.command("startMicrophoneLipSync")

    def stop_lip_sync(self) -> dict[str, Any]:
        return self.command("stopLipSync")

    def listening(self) -> dict[str, Any]:
        return self.batch(
            [
                {"type": "setPose", "pose": "listening"},
                {"type": "setExpression", "expression": "relaxed"},
            ]
        )

    def speaking(self, *, expression: str = "happy", energy: float = 0.72) -> dict[str, Any]:
        return self.batch(
            [
                {"type": "setState", "payload": {"expression": expression, "energy": energy, "idle": True}},
                {"type": "setLipSyncLevel", "level": 0.45},
            ]
        )

    def _get_json(self, path: str) -> dict[str, Any]:
        with request.urlopen(self._url(path), timeout=self.config.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_request = request.Request(
            self._url(path),
            data=data,
            method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        with request.urlopen(http_request, timeout=self.config.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _url(self, path: str) -> str:
        return f"{self.config.base_url.rstrip('/')}/{path.lstrip('/')}"

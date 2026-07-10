from __future__ import annotations

import sys
import subprocess
import wave
from pathlib import Path
from typing import Any


TANYUE_ROOT = Path(__file__).resolve().parents[1]
UNITREE_SDK_PATH = TANYUE_ROOT / "robot_voice" / "references" / "unitree_sdk2_python"


class G1VoiceOutput:
    def __init__(
        self,
        robot_voice: Any,
        speaker_ids: dict[str, int] | None = None,
        voice_pack_tracks: dict[str, str | Path] | None = None,
    ) -> None:
        self.robot_voice = robot_voice
        self.speaker_ids = speaker_ids or {}
        self.voice_pack_tracks = {
            key: Path(value) for key, value in (voice_pack_tracks or {}).items()
        }

    def speak(self, text: str, *, voice_pack: str) -> dict[str, Any]:
        track = self.voice_pack_tracks.get(voice_pack)
        if track is not None and track.is_file():
            pcm = _read_unitree_wav(track)
            self.robot_voice.play_pcm16_16k_mono_stream(
                [pcm],
                app_name="pungen_voice_pack",
                stream_id=f"pungen-{voice_pack}",
            )
            return {
                "status": "spoken_voice_pack",
                "voice_pack": voice_pack,
                "path": str(track),
            }
        speaker_id = int(self.speaker_ids.get(voice_pack, 0))
        self.robot_voice.say_builtin(text, speaker_id=speaker_id)
        return {
            "status": "spoken_builtin",
            "voice_pack": voice_pack,
            "speaker_id": speaker_id,
        }


class G1MotionOutput:
    """Safe high-level G1 demo motions available in the checked-in SDK.

    The SDK exposes WaveHand and WaveHand-with-turn, but no accordion or YMCA
    primitive. Those mappings are intentionally reported as approximate.
    """

    def __init__(self, loco_client: Any, accordion_runner=None) -> None:
        self.loco_client = loco_client
        self.accordion_runner = accordion_runner

    def perform(self, action: dict[str, Any]) -> dict[str, Any]:
        action_id = str(action.get("action_id") or action.get("arm_action") or "")
        if action_id == "accordion_gesture":
            if self.accordion_runner is not None:
                result = dict(self.accordion_runner())
                return {
                    **result,
                    "action_id": action_id,
                    "sdk_motion": "g1_trump_accordion",
                    "fidelity": "exact",
                    "evidence_level": "real_external",
                    "physical_motion_confirmed": False,
                }
            self.loco_client.WaveHand(False)
            return self._result(action_id, "WaveHand", "approximate")
        if action_id == "ymca_dance":
            self.loco_client.WaveHand(True)
            return self._result(action_id, "WaveHand(turn)", "approximate")
        if action_id in {"imperial_small_wave", "shrug_then_wave", "ward_off_push"}:
            self.loco_client.WaveHand(False)
            return self._result(action_id, "WaveHand", "approximate")
        return {
            "status": "unsupported_safe_idle",
            "executed": False,
            "action_id": action_id,
            "fidelity": "unsupported",
        }

    @staticmethod
    def _result(action_id: str, sdk_motion: str, fidelity: str) -> dict[str, Any]:
        return {
            "status": "command_sent",
            "executed": False,
            "action_id": action_id,
            "sdk_motion": sdk_motion,
            "fidelity": fidelity,
            "evidence_level": "real_external",
            "physical_motion_confirmed": False,
        }


class LowLevelAccordionRunner:
    """Explicitly gated subprocess wrapper for the low-level arm controller."""

    def __init__(
        self,
        binary: str | Path,
        network_interface: str,
        *,
        enabled: bool = False,
        timeout: float = 30.0,
    ) -> None:
        self.binary = Path(binary)
        self.network_interface = network_interface
        self.enabled = enabled
        self.timeout = timeout

    def __call__(self) -> dict[str, Any]:
        if not self.enabled:
            return {"status": "low_level_disabled", "executed": False}
        if not self.binary.is_file():
            return {
                "status": "accordion_binary_missing",
                "executed": False,
                "binary": str(self.binary),
            }
        completed = subprocess.run(
            [
                str(self.binary),
                self.network_interface,
                "--auto",
                "--i-understand-low-level-arm-risk",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=self.timeout,
        )
        return {
            "status": "process_completed" if completed.returncode == 0 else "process_failed",
            "executed": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout_tail": completed.stdout[-1000:],
            "stderr_tail": completed.stderr[-1000:],
        }

class G1MusicOutput:
    def __init__(self, robot_voice: Any, tracks: dict[str, str | Path] | None = None) -> None:
        self.robot_voice = robot_voice
        self.tracks = {key: Path(value) for key, value in (tracks or {}).items()}

    def play(self, track_id: str) -> dict[str, Any]:
        path = self.tracks.get(track_id)
        if path is None or not path.is_file():
            return {
                "status": "track_not_configured",
                "executed": False,
                "track_id": track_id,
            }
        pcm = _read_unitree_wav(path)
        self.robot_voice.play_pcm16_16k_mono_stream(
            [pcm],
            app_name="pungen_music",
            stream_id=f"pungen-{track_id}",
        )
        return {
            "status": "played",
            "executed": True,
            "track_id": track_id,
            "path": str(path),
        }


def _read_unitree_wav(path: Path) -> bytes:
    with wave.open(str(path), "rb") as handle:
        if (
            handle.getnchannels() != 1
            or handle.getsampwidth() != 2
            or handle.getframerate() != 16000
        ):
            raise ValueError("Unitree audio WAV must be 16 kHz mono PCM16.")
        return handle.readframes(handle.getnframes())


def connect_g1(network_interface: str, timeout: float = 10.0) -> tuple[Any, Any]:
    """Initialize one Unitree DDS channel and return audio and locomotion clients."""

    sdk_path = str(UNITREE_SDK_PATH)
    tanyue_path = str(TANYUE_ROOT)
    if tanyue_path not in sys.path:
        sys.path.insert(0, tanyue_path)
    if sdk_path not in sys.path:
        sys.path.insert(0, sdk_path)
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize
    from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient
    from unitree_sdk2py.g1.loco.g1_loco_client import LocoClient

    ChannelFactoryInitialize(0, network_interface)
    audio = AudioClient()
    audio.SetTimeout(timeout)
    audio.Init()
    loco = LocoClient()
    loco.SetTimeout(timeout)
    loco.Init()
    return audio, loco


class G1BuiltinVoiceClient:
    """Compatibility wrapper for AudioClient's built-in TTS API."""

    def __init__(self, audio_client: Any) -> None:
        self.audio_client = audio_client
        self._tts_index = 0

    def say_builtin(self, text: str, speaker_id: int = 0) -> None:
        import json

        self._tts_index += 1
        payload = json.dumps(
            {"index": self._tts_index, "text": text, "speaker_id": speaker_id},
            ensure_ascii=False,
        )
        code, _ = self.audio_client._Call(1001, payload)
        if code != 0:
            raise RuntimeError(f"TtsMaker failed: {code}")

    def play_pcm16_16k_mono_stream(self, chunks, **kwargs: Any) -> None:
        from robot_voice.unitree_g1_voice import UnitreeG1Voice

        proxy = UnitreeG1Voice.__new__(UnitreeG1Voice)
        proxy._client = self.audio_client
        proxy.play_pcm16_16k_mono_stream(chunks, **kwargs)

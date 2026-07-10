from __future__ import annotations

import json
import platform
import sys
import time
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
LOCAL_SDK = ROOT / "robot_voice" / "references" / "unitree_sdk2_python"


class UnitreeG1Voice:
    """Small wrapper around Unitree G1 AudioClient."""

    def __init__(self, network_interface: str, timeout: float = 10.0, sdk_path: str | None = None) -> None:
        self.network_interface = network_interface
        self.timeout = timeout
        self.sdk_path = Path(sdk_path).expanduser().resolve() if sdk_path else LOCAL_SDK
        self._client = None
        self._tts_index = 0

    def connect(self) -> None:
        if self._client is not None:
            return
        if str(self.sdk_path) not in sys.path:
            sys.path.insert(0, str(self.sdk_path))
        try:
            from unitree_sdk2py.core.channel import ChannelFactoryInitialize
            from unitree_sdk2py.g1.audio.g1_audio_client import AudioClient
        except ModuleNotFoundError as exc:
            if exc.name == "cyclonedds":
                python_version = platform.python_version()
                raise RuntimeError(
                    "unitree_sdk2py requires cyclonedds. In this project it is installed in the "
                    f"`Tanyue` conda env. Current Python is {python_version}. Run:\n"
                    "  conda activate Tanyue\n"
                    "  python robot_voice/stream_tts_to_robot.py --list-interfaces\n"
                    "  python robot_voice/stream_tts_to_robot.py <interface> --volume 85"
                ) from exc
            raise

        ChannelFactoryInitialize(0, self.network_interface)
        client = AudioClient()
        client.SetTimeout(self.timeout)
        client.Init()
        self._client = client

    @property
    def client(self):
        self.connect()
        return self._client

    def get_volume(self) -> int:
        code, data = self.client.GetVolume()
        if code != 0:
            raise RuntimeError(f"GetVolume failed: {code}")
        if isinstance(data, dict):
            if "volume" in data:
                return int(data["volume"])
            if "value" in data:
                return int(data["value"])
        raise RuntimeError(f"Unexpected GetVolume response: {data!r}")

    def set_volume(self, volume: int) -> None:
        volume = max(0, min(100, int(volume)))
        code = self.client.SetVolume(volume)
        if code != 0:
            raise RuntimeError(f"SetVolume failed: {code}")

    def led(self, r: int, g: int, b: int) -> None:
        code = self.client.LedControl(clamp_u8(r), clamp_u8(g), clamp_u8(b))
        if code != 0:
            raise RuntimeError(f"LedControl failed: {code}")

    def say_builtin(self, text: str, speaker_id: int = 0) -> None:
        """Use robot built-in TTS, avoiding the current Python SDK tts_index bug."""

        self._tts_index += 1
        payload = json.dumps(
            {
                "index": self._tts_index,
                "text": text,
                "speaker_id": int(speaker_id),
            },
            ensure_ascii=False,
        )
        code, _data = self.client._Call(1001, payload)
        if code != 0:
            raise RuntimeError(f"TtsMaker failed: {code}")

    def play_pcm16_16k_mono_stream(
        self,
        chunks: Iterable[bytes],
        app_name: str = "tanyue",
        stream_id: str | None = None,
        send_interval_ms: float = 40.0,
        verbose: bool = False,
    ) -> None:
        stream_id = stream_id or str(int(time.time() * 1000))
        sent = 0
        try:
            for index, chunk in enumerate(chunks):
                if not chunk:
                    continue
                code, _ = self.client.PlayStream(app_name, stream_id, chunk)
                if code != 0:
                    raise RuntimeError(f"PlayStream failed at chunk {index}: {code}")
                sent += len(chunk)
                if verbose:
                    print(f"[robot] chunk={index} bytes={len(chunk)} total={sent}", flush=True)
                if send_interval_ms > 0:
                    time.sleep(send_interval_ms / 1000.0)
        finally:
            self.stop(app_name)

    def stop(self, app_name: str = "tanyue") -> None:
        self.client.PlayStop(app_name)


def clamp_u8(value: int) -> int:
    return max(0, min(255, int(value)))

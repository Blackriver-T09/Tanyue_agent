from __future__ import annotations

import importlib
import os
import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from robot_voice.remote_tts_client import TTSRequest, emotion_to_instruct


SAFE_MODEL = "cosyvoice-v3.5-plus"
SAFE_VOICE = "longxiaochun"


@dataclass(frozen=True)
class AliyunCosyVoiceConfig:
    api_key: str
    workspace_id: str | None = None
    api_host: str | None = None
    region: str = "beijing"
    model: str = SAFE_MODEL
    sample_rate: int = 24000
    volume: int = 50
    speech_rate: float = 1.0
    pitch_rate: float = 1.0
    style_params_enabled: bool = False

    @property
    def websocket_url(self) -> str | None:
        if self.api_host:
            return f"wss://{self.api_host}/api-ws/v1/inference"
        if not self.workspace_id:
            return None
        if self.region == "singapore":
            return f"wss://{self.workspace_id}.ap-southeast-1.maas.aliyuncs.com/api-ws/v1/inference"
        return f"wss://{self.workspace_id}.cn-beijing.maas.aliyuncs.com/api-ws/v1/inference"


class AliyunCosyVoiceClient:
    sample_rate = 24000

    def __init__(self, config: AliyunCosyVoiceConfig | None = None) -> None:
        self.config = config or config_from_project()
        self.sample_rate = self.config.sample_rate

    def stream_pcm(self, req: TTSRequest) -> Iterator[bytes]:
        audio_queue: queue.Queue[bytes | BaseException | None] = queue.Queue()

        def worker() -> None:
            try:
                import dashscope
                from dashscope.audio.tts_v2 import AudioFormat, ResultCallback, SpeechSynthesizer

                dashscope.api_key = self.config.api_key
                if self.config.websocket_url:
                    dashscope.base_websocket_api_url = self.config.websocket_url

                class Callback(ResultCallback):
                    def on_data(self, data: bytes) -> None:
                        audio_queue.put(data)

                    def on_error(self, message: str) -> None:
                        audio_queue.put(RuntimeError(f"Aliyun CosyVoice TTS error: {message}"))

                    def on_complete(self) -> None:
                        audio_queue.put(None)

                kwargs = {
                    "model": self.config.model,
                    "voice": req.voice_id or SAFE_VOICE,
                    "format": AudioFormat.PCM_24000HZ_MONO_16BIT,
                    "volume": self.config.volume,
                    "speech_rate": req.speed or self.config.speech_rate,
                    "pitch_rate": self.config.pitch_rate,
                    "workspace": self.config.workspace_id,
                    "url": self.config.websocket_url,
                    "callback": Callback(),
                }
                if self.config.style_params_enabled or req.mode == "instruct2":
                    kwargs["instruction"] = req.instruct_text or emotion_to_instruct(
                        req.emotion,
                        req.emotion_strength,
                    )
                    kwargs["language_hints"] = ["zh", "en"]

                synthesizer = SpeechSynthesizer(**kwargs)
                text = req.text.strip()
                if text:
                    synthesizer.streaming_call(text)
                    synthesizer.streaming_complete()
                else:
                    audio_queue.put(None)
            except BaseException as exc:  # noqa: BLE001
                audio_queue.put(exc)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        while True:
            item = audio_queue.get()
            if item is None:
                break
            if isinstance(item, BaseException):
                raise item
            yield item
        thread.join(timeout=3)


def config_from_project() -> AliyunCosyVoiceConfig:
    load_env_files()
    config = import_config()
    api_key = os.environ.get("DASHSCOPE_API_KEY") or getattr(config, "API_KEY", None)
    if not api_key:
        raise RuntimeError("Missing DashScope API key. Set DASHSCOPE_API_KEY or Config.py API_KEY.")
    workspace_id = (
        os.environ.get("DASHSCOPE_WORKSPACE_ID")
        or getattr(config, "DASHSCOPE_WORKSPACE_ID", None)
        or getattr(config, "WORKSPACE_ID", None)
        or getattr(config, "WORKSAPCE_ID", None)
    )
    api_host = os.environ.get("DASHSCOPE_API_HOST") or os.environ.get("API_HOST") or getattr(config, "API_HOST", None)
    region = os.environ.get("DASHSCOPE_REGION") or getattr(config, "DASHSCOPE_REGION", None) or "beijing"
    return AliyunCosyVoiceConfig(
        api_key=api_key,
        workspace_id=workspace_id,
        api_host=api_host,
        region=region,
        model=os.environ.get("TANYUE_COSYVOICE_MODEL", SAFE_MODEL),
        volume=int(os.environ.get("TANYUE_COSYVOICE_VOLUME", "50")),
        speech_rate=float(os.environ.get("TANYUE_COSYVOICE_SPEECH_RATE", "1.0")),
        pitch_rate=float(os.environ.get("TANYUE_COSYVOICE_PITCH_RATE", "1.0")),
        style_params_enabled=env_bool("TANYUE_COSYVOICE_ENABLE_STYLE_PARAMS", False),
    )


def load_env_files() -> None:
    try:
        from dotenv import load_dotenv
    except Exception:  # noqa: BLE001
        return
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    load_dotenv(root / "voice" / ".env")


def import_config():
    try:
        return importlib.import_module("Config")
    except Exception:  # noqa: BLE001
        return object()


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value in {"1", "true", "True", "yes", "YES", "on", "ON"}

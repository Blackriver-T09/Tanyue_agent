from __future__ import annotations

import asyncio
import logging
import os
import queue as sync_queue
import threading
from dataclasses import dataclass, field
from typing import AsyncIterable, AsyncIterator


LOGGER = logging.getLogger("tanyue.aliyun_tts")
SAFE_MODEL = "cosyvoice-v1"
SAFE_VOICE = "longxiaochun"
LEGACY_INVALID_MODEL = "cosyvoice-v3-flash"
LEGACY_INVALID_VOICE = "longanyang"


@dataclass(frozen=True)
class AliyunCosyVoiceConfig:
    api_key: str
    workspace_id: str | None = None
    api_host: str | None = None
    region: str = "beijing"
    model: str = "cosyvoice-v1"
    voice: str = "longxiaochun"
    sample_rate: int = 24000
    volume: int = 50
    speech_rate: float = 1.0
    pitch_rate: float = 1.0
    instruction: str | None = None
    language_hints: list[str] = field(default_factory=lambda: ["zh"])

    @property
    def websocket_url(self) -> str | None:
        if self.api_host:
            return f"wss://{self.api_host}/api-ws/v1/inference"
        if not self.workspace_id:
            return None
        if self.region == "singapore":
            return f"wss://{self.workspace_id}.ap-southeast-1.maas.aliyuncs.com/api-ws/v1/inference"
        return f"wss://{self.workspace_id}.cn-beijing.maas.aliyuncs.com/api-ws/v1/inference"


class AliyunCosyVoiceTTS:
    sample_rate = 24000
    num_channels = 1

    def __init__(self, config: AliyunCosyVoiceConfig) -> None:
        self.config = config
        self.sample_rate = config.sample_rate

    async def synthesize_frames(self, text: AsyncIterable[str]) -> AsyncIterator["rtc.AudioFrame"]:
        from livekit import rtc

        audio_queue: asyncio.Queue[bytes | BaseException | None] = asyncio.Queue()
        text_queue: sync_queue.Queue[str | None] = sync_queue.Queue()
        loop = asyncio.get_running_loop()

        def put_threadsafe(item: bytes | BaseException | None) -> None:
            loop.call_soon_threadsafe(audio_queue.put_nowait, item)

        def synthesize_worker() -> None:
            try:
                import dashscope
                from dashscope.audio.tts_v2 import AudioFormat, ResultCallback, SpeechSynthesizer

                dashscope.api_key = self.config.api_key
                if self.config.websocket_url:
                    dashscope.base_websocket_api_url = self.config.websocket_url

                class Callback(ResultCallback):
                    def on_data(self, data: bytes) -> None:
                        nonlocal first_audio
                        if first_audio:
                            LOGGER.info("Aliyun CosyVoice first audio chunk received")
                            first_audio = False
                        put_threadsafe(data)

                    def on_error(self, message: str) -> None:
                        put_threadsafe(RuntimeError(f"Aliyun CosyVoice TTS error: {message}"))

                    def on_complete(self) -> None:
                        put_threadsafe(None)

                kwargs = {
                    "model": self.config.model,
                    "voice": self.config.voice,
                    "format": AudioFormat.PCM_24000HZ_MONO_16BIT,
                    "volume": self.config.volume,
                    "speech_rate": self.config.speech_rate,
                    "pitch_rate": self.config.pitch_rate,
                    "workspace": self.config.workspace_id,
                    "url": self.config.websocket_url,
                    "callback": Callback(),
                }
                if os.environ.get("TANYUE_COSYVOICE_ENABLE_STYLE_PARAMS", "0") in {"1", "true", "True"}:
                    kwargs["instruction"] = self.config.instruction
                    kwargs["language_hints"] = self.config.language_hints

                LOGGER.info(
                    "Aliyun CosyVoice stream opening: model=%s voice=%s url=%s",
                    self.config.model,
                    self.config.voice,
                    self.config.websocket_url or "dashscope-default",
                )
                synthesizer = SpeechSynthesizer(**kwargs)
                LOGGER.info("Aliyun CosyVoice stream ready")

                sent_text = False
                while True:
                    chunk = text_queue.get()
                    if chunk is None:
                        break
                    chunk = chunk.strip()
                    if chunk:
                        if not sent_text:
                            LOGGER.info("Aliyun CosyVoice first text chunk sent")
                            sent_text = True
                        synthesizer.streaming_call(chunk)
                if sent_text:
                    synthesizer.streaming_complete()
                else:
                    put_threadsafe(None)
            except BaseException as exc:  # noqa: BLE001
                put_threadsafe(exc)

        async def feed_text() -> None:
            try:
                async for chunk in text:
                    if chunk and chunk.strip():
                        text_queue.put(chunk)
            except BaseException as exc:  # noqa: BLE001
                put_threadsafe(exc)
            finally:
                text_queue.put(None)

        first_audio = True
        worker = threading.Thread(target=synthesize_worker, daemon=True)
        worker.start()
        producer = asyncio.create_task(feed_text())

        try:
            while True:
                item = await audio_queue.get()
                if item is None:
                    break
                if isinstance(item, BaseException):
                    raise item
                yield self._pcm_to_frame(rtc, item)
        finally:
            if not producer.done():
                producer.cancel()
                text_queue.put(None)

    def _pcm_to_frame(self, rtc, data: bytes):
        samples_per_channel = len(data) // 2
        return rtc.AudioFrame(
            data=bytearray(data),
            sample_rate=self.sample_rate,
            num_channels=self.num_channels,
            samples_per_channel=samples_per_channel,
        )


def config_from_env(api_key: str | None = None) -> AliyunCosyVoiceConfig:
    model = os.environ.get("TANYUE_COSYVOICE_MODEL", SAFE_MODEL)
    voice = os.environ.get("TANYUE_COSYVOICE_VOICE", SAFE_VOICE)
    if (
        model == LEGACY_INVALID_MODEL
        or voice == LEGACY_INVALID_VOICE
    ) and os.environ.get("TANYUE_COSYVOICE_ALLOW_LEGACY", "0") not in {"1", "true", "True"}:
        LOGGER.warning(
            "Ignoring legacy CosyVoice config model=%s voice=%s; using model=%s voice=%s",
            model,
            voice,
            SAFE_MODEL,
            SAFE_VOICE,
        )
        model = SAFE_MODEL
        voice = SAFE_VOICE

    return AliyunCosyVoiceConfig(
        api_key=api_key or os.environ["DASHSCOPE_API_KEY"],
        workspace_id=os.environ.get("DASHSCOPE_WORKSPACE_ID"),
        api_host=os.environ.get("DASHSCOPE_API_HOST") or os.environ.get("API_HOST"),
        region=os.environ.get("DASHSCOPE_REGION", "beijing"),
        model=model,
        voice=voice,
        instruction=os.environ.get("TANYUE_COSYVOICE_INSTRUCTION") or "温柔、亲近、自然地说话",
    )

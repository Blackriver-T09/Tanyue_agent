from __future__ import annotations

import asyncio
import logging
import math
import os
import threading
import time
from dataclasses import dataclass
from typing import Any

from livekit.agents import stt
from livekit.agents.types import APIConnectOptions, DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN, NotGivenOr


BEIJING_WEBSOCKET_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
SINGAPORE_WEBSOCKET_URL = "wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference"
LOGGER = logging.getLogger("tanyue.aliyun_stt")


@dataclass(frozen=True)
class AliyunRealtimeSTTConfig:
    api_key: str
    model: str = "fun-asr-realtime"
    language: str = "zh"
    region: str = "beijing"
    url: str | None = None
    sample_rate: int = 16000
    semantic_punctuation: bool = False
    # Keep short pauses inside one utterance. The gate continues sending digital
    # silence until ASR emits the final transcript, so this is the actual
    # sentence-end debounce rather than a workaround for missing audio.
    max_sentence_silence_ms: int = 900
    skip_preflight: bool = True
    noise_gate_enabled: bool = True
    noise_gate_dbfs: float = -45.0
    noise_gate_open_ms: int = 80
    noise_gate_hangover_ms: int = 900
    noise_gate_send_silence_after_speech: bool = True
    noise_gate_log_interval_s: float = 5.0

    @property
    def websocket_url(self) -> str:
        if self.url:
            return self.url
        return SINGAPORE_WEBSOCKET_URL if self.region == "singapore" else BEIJING_WEBSOCKET_URL


class AliyunRealtimeSTT(stt.STT):
    def __init__(self, config: AliyunRealtimeSTTConfig) -> None:
        super().__init__(
            capabilities=stt.STTCapabilities(
                streaming=True,
                interim_results=True,
                diarization=False,
                aligned_transcript="word",
                offline_recognize=False,
            )
        )
        self.config = config

    @property
    def model(self) -> str:
        return self.config.model

    @property
    def provider(self) -> str:
        return "aliyun"

    async def _recognize_impl(
        self,
        buffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions,
    ) -> stt.SpeechEvent:
        raise NotImplementedError("AliyunRealtimeSTT only supports streaming recognition.")

    def stream(
        self,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.SpeechStream:
        return _AliyunSpeechStream(self, language=language, conn_options=conn_options)


class _AliyunSpeechStream(stt.SpeechStream):
    def __init__(
        self,
        stt_instance: AliyunRealtimeSTT,
        *,
        language: NotGivenOr[str],
        conn_options: APIConnectOptions,
    ) -> None:
        super().__init__(
            stt=stt_instance,
            conn_options=conn_options,
            sample_rate=stt_instance.config.sample_rate,
        )
        self._aliyun_stt = stt_instance
        self._language = language if language is not NOT_GIVEN else stt_instance.config.language
        self._loop: asyncio.AbstractEventLoop | None = None
        self._opened = threading.Event()
        self._closed = threading.Event()
        self._recognizer = None
        self._in_speech = False
        self._gate_open = False
        self._last_loud_audio_at = 0.0
        self._pending_loud_audio: list[bytes] = []
        self._pending_loud_ms = 0.0
        self._last_gate_log_at = 0.0
        self._suppressed_frames = 0

    async def _run(self) -> None:
        self._loop = asyncio.get_running_loop()
        LOGGER.info(
            "Aliyun STT stream starting: model=%s url=%s sample_rate=%s",
            self._aliyun_stt.config.model,
            self._aliyun_stt.config.websocket_url,
            self._aliyun_stt.config.sample_rate,
        )
        self._start_recognizer()
        opened = await asyncio.to_thread(self._opened.wait, 15)
        if not opened:
            raise RuntimeError("Timed out connecting to Aliyun realtime ASR.")
        LOGGER.info("Aliyun STT stream connected")

        try:
            async for item in self._input_ch:
                if isinstance(item, stt.SpeechStream._FlushSentinel):
                    continue
                data = bytes(item.data)
                if data:
                    data = self._gate_audio(data)
                    if not data:
                        continue
                    await asyncio.to_thread(self._recognizer.send_audio_frame, data)
        finally:
            await asyncio.to_thread(self._stop_recognizer)

    def _start_recognizer(self) -> None:
        import dashscope
        from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult

        config = self._aliyun_stt.config
        dashscope.api_key = config.api_key
        dashscope.base_websocket_api_url = config.websocket_url

        stream = self

        class Callback(RecognitionCallback):
            def on_open(self) -> None:
                stream._opened.set()

            def on_close(self) -> None:
                stream._closed.set()

            def on_complete(self) -> None:
                stream._closed.set()

            def on_error(self, message: Any) -> None:
                stream._closed.set()
                LOGGER.error("Aliyun STT stream error: %s", message)
                stream._emit_exception(RuntimeError(f"Aliyun realtime ASR error: {message}"))

            def on_event(self, result: RecognitionResult) -> None:
                stream._handle_result(result)

        self._recognizer = Recognition(
            model=config.model,
            format="pcm",
            sample_rate=config.sample_rate,
            semantic_punctuation_enabled=config.semantic_punctuation,
            max_sentence_silence=config.max_sentence_silence_ms,
            callback=Callback(),
        )
        self._recognizer.start()

    def _stop_recognizer(self) -> None:
        if not self._recognizer:
            return
        try:
            self._recognizer.stop()
        except Exception:
            pass
        self._closed.wait(timeout=5)

    def _gate_audio(self, data: bytes) -> bytes:
        config = self._aliyun_stt.config
        if not config.noise_gate_enabled:
            return data

        dbfs = pcm16_dbfs(data)
        now = time.monotonic()
        is_loud = dbfs >= config.noise_gate_dbfs
        if is_loud:
            self._last_loud_audio_at = now
            if self._gate_open:
                return data

            self._pending_loud_audio.append(data)
            self._pending_loud_ms += audio_duration_ms(data, config.sample_rate)
            if self._pending_loud_ms >= config.noise_gate_open_ms:
                self._gate_open = True
                joined = b"".join(self._pending_loud_audio)
                self._pending_loud_audio.clear()
                self._pending_loud_ms = 0.0
                LOGGER.info(
                    "Aliyun STT noise gate opened: dbfs=%.1f threshold=%.1f open_ms=%d",
                    dbfs,
                    config.noise_gate_dbfs,
                    config.noise_gate_open_ms,
                )
                return joined
            return b""

        self._suppressed_frames += 1
        self._pending_loud_audio.clear()
        self._pending_loud_ms = 0.0
        if now - self._last_gate_log_at >= config.noise_gate_log_interval_s:
            LOGGER.debug(
                "Aliyun STT noise gate suppressing low audio: dbfs=%.1f threshold=%.1f frames=%d",
                dbfs,
                config.noise_gate_dbfs,
                self._suppressed_frames,
            )
            self._last_gate_log_at = now
            self._suppressed_frames = 0

        if self._gate_open:
            hangover_s = max(0.0, config.noise_gate_hangover_ms / 1000.0)
            if now - self._last_loud_audio_at <= hangover_s:
                # Do not send the real below-threshold microphone frame. Digital silence
                # preserves ASR timing and lets the cloud recognizer finish the sentence.
                return b"\x00" * len(data) if config.noise_gate_send_silence_after_speech else b""
            if self._in_speech and config.noise_gate_send_silence_after_speech:
                # Do not close the transport-side gate before Aliyun has emitted
                # END_OF_SPEECH. Otherwise ASR may wait for the next real frame
                # and attach the previous sentence to the next utterance.
                return b"\x00" * len(data)
            LOGGER.info("Aliyun STT noise gate closed: dbfs=%.1f threshold=%.1f", dbfs, config.noise_gate_dbfs)
            self._gate_open = False

        return b""

    def _handle_result(self, result: Any) -> None:
        from dashscope.audio.asr import RecognitionResult

        sentence = result.get_sentence() or {}
        text = (sentence.get("text") or "").strip()
        if not text:
            return

        is_final = RecognitionResult.is_sentence_end(sentence)
        LOGGER.info("Aliyun STT %s transcript: %s", "final" if is_final else "interim", text)
        request_id = result.get_request_id() or ""
        begin_ms = sentence.get("begin_time")
        end_ms = sentence.get("end_time")
        start_time = (begin_ms or 0) / 1000.0
        end_time = (end_ms or begin_ms or 0) / 1000.0

        if not self._in_speech:
            self._in_speech = True
            self._emit_event(
                stt.SpeechEvent(
                    type=stt.SpeechEventType.START_OF_SPEECH,
                    request_id=request_id,
                    speech_start_time=time.time(),
                )
            )

        event_type = stt.SpeechEventType.FINAL_TRANSCRIPT if is_final else stt.SpeechEventType.INTERIM_TRANSCRIPT
        self._emit_event(
            stt.SpeechEvent(
                type=event_type,
                request_id=request_id,
                alternatives=[
                    stt.SpeechData(
                        language=self._language or "zh",
                        text=text,
                        start_time=start_time,
                        end_time=end_time,
                        confidence=0.0,
                        metadata={
                            "provider": "aliyun",
                            "backend": "funasr",
                            "sentence": sentence,
                        },
                    )
                ],
            )
        )

        if is_final:
            self._emit_event(
                stt.SpeechEvent(
                    type=stt.SpeechEventType.END_OF_SPEECH,
                    request_id=request_id,
                )
            )
            self._in_speech = False

    def _emit_event(self, event: stt.SpeechEvent) -> None:
        if self._loop:
            self._loop.call_soon_threadsafe(self._event_ch.send_nowait, event)

    def _emit_exception(self, exc: BaseException) -> None:
        if self._loop:
            self._loop.call_soon_threadsafe(self._event_ch.close, exc)


def config_from_env(api_key: str | None = None) -> AliyunRealtimeSTTConfig:
    return AliyunRealtimeSTTConfig(
        api_key=api_key or os.environ["DASHSCOPE_API_KEY"],
        model=os.environ.get("TANYUE_ALIYUN_STT_MODEL", "fun-asr-realtime"),
        language=os.environ.get("TANYUE_STT_LANGUAGE", "zh"),
        region=os.environ.get("DASHSCOPE_REGION", "beijing"),
        url=os.environ.get("TANYUE_ALIYUN_STT_URL") or os.environ.get("DASHSCOPE_FUNASR_WEBSOCKET_URL"),
        semantic_punctuation=os.environ.get("TANYUE_ALIYUN_STT_PUNCTUATION", "0") in {"1", "true", "True"},
        max_sentence_silence_ms=int(os.environ.get("TANYUE_ALIYUN_STT_SILENCE_MS", "900")),
        noise_gate_enabled=os.environ.get("TANYUE_ALIYUN_STT_NOISE_GATE_ENABLED", "1") in {"1", "true", "True"},
        noise_gate_dbfs=float(os.environ.get("TANYUE_ALIYUN_STT_NOISE_GATE_DBFS", "-45")),
        noise_gate_open_ms=int(os.environ.get("TANYUE_ALIYUN_STT_NOISE_GATE_OPEN_MS", "80")),
        noise_gate_hangover_ms=int(os.environ.get("TANYUE_ALIYUN_STT_NOISE_GATE_HANGOVER_MS", "900")),
        noise_gate_send_silence_after_speech=os.environ.get(
            "TANYUE_ALIYUN_STT_NOISE_GATE_SEND_SILENCE",
            "1",
        ) in {"1", "true", "True"},
        noise_gate_log_interval_s=float(os.environ.get("TANYUE_ALIYUN_STT_NOISE_GATE_LOG_INTERVAL_S", "5")),
    )


def pcm16_dbfs(data: bytes) -> float:
    if len(data) < 2:
        return -120.0
    if len(data) % 2:
        data = data[:-1]
    samples = memoryview(data).cast("h")
    if not samples:
        return -120.0
    square_sum = 0
    for sample in samples:
        square_sum += sample * sample
    rms = math.sqrt(square_sum / len(samples)) / 32768.0
    if rms <= 0.0:
        return -120.0
    return 20.0 * math.log10(rms)


def audio_duration_ms(data: bytes, sample_rate: int) -> float:
    if sample_rate <= 0:
        return 0.0
    return (len(data) / 2.0) / float(sample_rate) * 1000.0

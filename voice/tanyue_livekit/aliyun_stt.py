from __future__ import annotations

import asyncio
import logging
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
    max_sentence_silence_ms: int = 400
    skip_preflight: bool = True

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
        max_sentence_silence_ms=int(os.environ.get("TANYUE_ALIYUN_STT_SILENCE_MS", "400")),
    )

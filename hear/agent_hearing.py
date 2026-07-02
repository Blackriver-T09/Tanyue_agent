#!/usr/bin/env python3
"""Modular realtime hearing channel for agents."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import queue
import signal
import socket
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlparse

try:
    import dashscope
    import numpy as np
    import sounddevice as sd
    import websockets
    from dashscope.audio.asr import Recognition, RecognitionCallback, RecognitionResult
    from dashscope.audio.qwen_omni import (
        MultiModality,
        OmniRealtimeCallback,
        OmniRealtimeConversation,
    )
    from dashscope.audio.qwen_omni.omni_realtime import TranscriptionParams
    from dashscope.common.error import InvalidParameter
except ImportError as exc:
    missing = exc.name or "dependency"
    raise SystemExit(
        f"Missing dependency: {missing}\n"
        "Install with: conda activate Tanyue && pip install -r hear/requirements-aliyun.txt"
    ) from exc


SAMPLE_RATE = 16_000
CHANNELS = 1
AUDIO_FORMAT = "pcm"
BEIJING_WEBSOCKET_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
SINGAPORE_WEBSOCKET_URL = "wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference"
QWEN_BEIJING_URL_TEMPLATE = "wss://{workspace}.cn-beijing.maas.aliyuncs.com/api-ws/v1/realtime"

AgentEventHandler = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class HearingConfig:
    api_key: str
    backend: str = "funasr"
    model: str | None = None
    language: str | None = "zh"
    device: int | str | None = None
    chunk_ms: int = 100
    vad_silence_ms: int = 400
    vad_threshold: float = 0.2
    semantic_punctuation: bool = False
    workspace: str | None = None
    region: str = "beijing"
    funasr_url: str | None = None
    qwen_url: str | None = None
    skip_preflight: bool = False
    include_raw: bool = True
    emit_stdout: bool = False
    debug: bool = False
    agent_id: str = "tanyue"

    def resolved_model(self) -> str:
        if self.model:
            return self.model
        return "qwen3-asr-flash-realtime" if self.backend == "qwen" else "fun-asr-realtime"

    def resolved_funasr_url(self) -> str:
        if self.funasr_url:
            return self.funasr_url
        return SINGAPORE_WEBSOCKET_URL if self.region == "singapore" else BEIJING_WEBSOCKET_URL

    def resolved_qwen_url(self) -> str | None:
        if self.qwen_url:
            return self.qwen_url
        if self.workspace:
            return QWEN_BEIJING_URL_TEMPLATE.format(workspace=self.workspace)
        return None


class JsonWebSocketBroadcaster:
    """Small local JSON broadcaster for agent subscribers."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.clients: set[Any] = set()
        self.loop: asyncio.AbstractEventLoop | None = None
        self._stop_future: asyncio.Future[None] | None = None
        self._thread: threading.Thread | None = None
        self.started = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        if not self.started.wait(timeout=5):
            raise RuntimeError("Timed out starting hearing WebSocket broadcaster.")

    def stop(self) -> None:
        if self.loop and self._stop_future and not self._stop_future.done():
            self.loop.call_soon_threadsafe(self._stop_future.set_result, None)
        if self._thread:
            self._thread.join(timeout=3)

    def broadcast(self, event: dict[str, Any]) -> None:
        if not self.loop or not self.clients:
            return
        payload = json.dumps(event, ensure_ascii=False, default=str)
        asyncio.run_coroutine_threadsafe(self._broadcast(payload), self.loop)

    def _run(self) -> None:
        asyncio.run(self._serve())

    async def _serve(self) -> None:
        self.loop = asyncio.get_running_loop()
        self._stop_future = self.loop.create_future()
        async with websockets.serve(self._handler, self.host, self.port):
            self.started.set()
            await self._stop_future

    async def _handler(self, websocket: Any) -> None:
        self.clients.add(websocket)
        try:
            await websocket.send(
                json.dumps(
                    {
                        "type": "status",
                        "status": "connected",
                        "channel": "agent_hearing",
                        "message": "hearing event stream connected",
                        "received_at": time.time(),
                    },
                    ensure_ascii=False,
                )
            )
            async for _message in websocket:
                pass
        finally:
            self.clients.discard(websocket)

    async def _broadcast(self, payload: str) -> None:
        for websocket in list(self.clients):
            try:
                await websocket.send(payload)
            except Exception:
                self.clients.discard(websocket)


class AudioInput:
    def __init__(self, config: HearingConfig) -> None:
        self.config = config
        self.queue: queue.Queue[bytes] = queue.Queue(maxsize=200)
        self.stop_event = threading.Event()

    def __enter__(self) -> "AudioInput":
        blocksize = int(SAMPLE_RATE * self.config.chunk_ms / 1000)

        def callback(indata: np.ndarray, _frames: int, _time: Any, status: sd.CallbackFlags) -> None:
            if status and self.config.debug:
                print(f"[audio status] {status}", file=sys.stderr)
            try:
                self.queue.put_nowait(indata.copy().tobytes())
            except queue.Full:
                if self.config.debug:
                    print("[audio warning] dropping chunk; queue is full", file=sys.stderr)

        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=blocksize,
            device=self.config.device,
            callback=callback,
        )
        self.stream.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.stream.__exit__(exc_type, exc, tb)

    def chunks(self):
        while not self.stop_event.is_set():
            try:
                yield self.queue.get(timeout=0.2)
            except queue.Empty:
                continue

    def stop(self) -> None:
        self.stop_event.set()


class AgentFunAsrCallback(RecognitionCallback):
    def __init__(
        self,
        config: HearingConfig,
        publish: AgentEventHandler,
        opened: threading.Event,
        stopped: threading.Event,
    ) -> None:
        self.config = config
        self.publish = publish
        self.opened = opened
        self.stopped = stopped

    def on_open(self) -> None:
        self.opened.set()
        self.publish(status_event(self.config, "connected", "Fun-ASR connection opened"))

    def on_close(self) -> None:
        self.stopped.set()
        self.publish(status_event(self.config, "closed", "Fun-ASR connection closed"))

    def on_complete(self) -> None:
        self.stopped.set()
        self.publish(status_event(self.config, "completed", "Fun-ASR recognition completed"))

    def on_error(self, message: Any) -> None:
        self.stopped.set()
        self.publish(error_event(self.config, "funasr", format_sdk_error(message), message))

    def on_event(self, result: RecognitionResult) -> None:
        sentence = result.get_sentence() or {}
        text = sentence.get("text", "")
        if not text:
            return

        is_final = RecognitionResult.is_sentence_end(sentence)
        event: dict[str, Any] = {
            "type": "transcription",
            "source": "aliyun",
            "agent_id": self.config.agent_id,
            "backend": "funasr",
            "model": self.config.resolved_model(),
            "language": self.config.language,
            "final": bool(is_final),
            "text": text,
            "emotion": None,
            "tone": {
                "available": False,
                "source": None,
                "note": "Fun-ASR provides timestamps. Use backend=qwen for 7-class emotion.",
            },
            "timestamps": {
                "begin_time_ms": sentence.get("begin_time"),
                "end_time_ms": sentence.get("end_time"),
                "words": sentence.get("words"),
            },
            "request_id": result.get_request_id(),
            "usage": result.get_usage(sentence) if is_final else None,
            "received_at": time.time(),
        }
        if self.config.include_raw:
            event["raw"] = {"sentence": sentence}
        self.publish(event)


class AgentQwenCallback(OmniRealtimeCallback):
    def __init__(
        self,
        config: HearingConfig,
        publish: AgentEventHandler,
        opened: threading.Event,
        stopped: threading.Event,
    ) -> None:
        self.config = config
        self.publish = publish
        self.opened = opened
        self.stopped = stopped

    def on_open(self) -> None:
        self.opened.set()
        self.publish(status_event(self.config, "connected", "Qwen-ASR connection opened"))

    def on_close(self, code: int, msg: str) -> None:
        self.stopped.set()
        self.publish(status_event(self.config, "closed", f"Qwen-ASR connection closed: {code} {msg}"))

    def on_event(self, response: dict[str, Any]) -> None:
        event_type = response.get("type")
        if event_type == "session.created":
            self.publish(status_event(self.config, "session_created", "Qwen-ASR session created", response))
            return

        if event_type == "conversation.item.input_audio_transcription.text":
            text = f"{response.get('text', '')}{response.get('stash', '')}"
            if text:
                self.publish(self._transcription_event(text, False, response))
            return

        if event_type == "conversation.item.input_audio_transcription.completed":
            self.publish(self._transcription_event(response.get("transcript", ""), True, response))
            return

        if event_type in {"input_audio_buffer.speech_started", "input_audio_buffer.speech_stopped"}:
            self.publish(
                {
                    "type": "vad",
                    "source": "aliyun",
                    "agent_id": self.config.agent_id,
                    "backend": "qwen",
                    "event": event_type,
                    "received_at": time.time(),
                    "raw": response if self.config.include_raw else None,
                }
            )
            return

        if self.config.debug:
            self.publish(status_event(self.config, "debug", event_type or "qwen_event", response))

    def _transcription_event(self, text: str, final: bool, response: dict[str, Any]) -> dict[str, Any]:
        emotion = response.get("emotion")
        event: dict[str, Any] = {
            "type": "transcription",
            "source": "aliyun",
            "agent_id": self.config.agent_id,
            "backend": "qwen",
            "model": self.config.resolved_model(),
            "language": self.config.language,
            "final": final,
            "text": text,
            "emotion": emotion,
            "tone": {
                "available": emotion is not None,
                "source": "qwen3-asr-flash-realtime",
                "emotion": emotion,
                "labels": ["surprised", "neutral", "happy", "sad", "disgusted", "angry", "fearful"],
            },
            "timestamps": None,
            "received_at": time.time(),
        }
        if self.config.include_raw:
            event["raw"] = response
        return event


class AgentHearing:
    """Realtime hearing service that agents can call as a Python module."""

    def __init__(
        self,
        config: HearingConfig,
        on_event: AgentEventHandler | None = None,
        websocket_host: str | None = None,
        websocket_port: int = 8765,
    ) -> None:
        self.config = config
        self.on_event = on_event
        self.events: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=500)
        self.stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._broadcaster = (
            JsonWebSocketBroadcaster(websocket_host, websocket_port) if websocket_host else None
        )

    def start_background(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def get_event(self, timeout: float | None = None) -> dict[str, Any]:
        return self.events.get(timeout=timeout)

    def run(self) -> None:
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGINT, self._handle_signal)
            signal.signal(signal.SIGTERM, self._handle_signal)

        dashscope.api_key = self.config.api_key
        if self._broadcaster:
            self._broadcaster.start()
            self.publish(
                status_event(
                    self.config,
                    "websocket_ready",
                    f"agent hearing WebSocket ready on ws://{self._broadcaster.host}:{self._broadcaster.port}",
                )
            )

        try:
            if self.config.backend == "qwen":
                self._run_qwen()
            else:
                self._run_funasr()
        finally:
            if self._broadcaster:
                self._broadcaster.stop()

    def publish(self, event: dict[str, Any]) -> None:
        event = compact_event(event)
        try:
            self.events.put_nowait(event)
        except queue.Full:
            if self.config.debug:
                print("[agent hearing] event queue full; dropping event", file=sys.stderr)

        if self.config.emit_stdout:
            print(json.dumps(event, ensure_ascii=False, default=str), flush=True)

        if self._broadcaster:
            self._broadcaster.broadcast(event)

        if self.on_event:
            self.on_event(event)

    def _run_funasr(self) -> None:
        dashscope.base_websocket_api_url = self.config.resolved_funasr_url()
        if not self.config.skip_preflight:
            preflight_websocket_url(self.config.resolved_funasr_url())

        opened = threading.Event()
        stopped = threading.Event()
        callback = AgentFunAsrCallback(self.config, self.publish, opened, stopped)
        recognizer = Recognition(
            model=self.config.resolved_model(),
            format=AUDIO_FORMAT,
            sample_rate=SAMPLE_RATE,
            semantic_punctuation_enabled=self.config.semantic_punctuation,
            max_sentence_silence=self.config.vad_silence_ms,
            callback=callback,
        )

        recognizer.start()
        if not opened.wait(timeout=15):
            raise RuntimeError("Timed out connecting to Aliyun Fun-ASR realtime API.")

        self.publish(status_event(self.config, "listening", "microphone streaming started"))
        try:
            with AudioInput(self.config) as audio:
                self._stream_audio(audio, recognizer.send_audio_frame, stopped)
        finally:
            safe_stop_recognizer(recognizer)
            stopped.wait(timeout=5)
            self.publish(
                status_event(
                    self.config,
                    "metrics",
                    "Fun-ASR recognition metrics",
                    {
                        "request_id": recognizer.get_last_request_id(),
                        "first_package_delay_ms": recognizer.get_first_package_delay(),
                        "last_package_delay_ms": recognizer.get_last_package_delay(),
                    },
                )
            )

    def _run_qwen(self) -> None:
        opened = threading.Event()
        stopped = threading.Event()
        callback = AgentQwenCallback(self.config, self.publish, opened, stopped)
        conversation = OmniRealtimeConversation(
            model=self.config.resolved_model(),
            url=self.config.resolved_qwen_url(),
            workspace=self.config.workspace,
            api_key=self.config.api_key,
            callback=callback,
        )

        conversation.connect()
        if not opened.wait(timeout=15):
            raise RuntimeError("Timed out connecting to Aliyun Qwen-ASR realtime API.")

        params = TranscriptionParams(
            language=self.config.language,
            sample_rate=SAMPLE_RATE,
            input_audio_format=AUDIO_FORMAT,
        )
        conversation.update_session(
            output_modalities=[MultiModality.TEXT],
            enable_input_audio_transcription=True,
            enable_turn_detection=True,
            turn_detection_threshold=self.config.vad_threshold,
            turn_detection_silence_duration_ms=self.config.vad_silence_ms,
            transcription_params=params,
        )

        self.publish(status_event(self.config, "listening", "microphone streaming started"))
        try:
            with AudioInput(self.config) as audio:
                self._stream_audio(
                    audio,
                    lambda chunk: conversation.append_audio(base64.b64encode(chunk).decode("ascii")),
                )
            conversation.end_session()
        finally:
            conversation.close()
            stopped.wait(timeout=5)

    def _stream_audio(
        self,
        audio: AudioInput,
        send: Callable[[bytes], None],
        stopped: threading.Event | None = None,
    ) -> None:
        while not self.stop_event.is_set():
            for chunk in audio.chunks():
                if self.stop_event.is_set() or (stopped and stopped.is_set()):
                    break
                try:
                    send(chunk)
                except InvalidParameter as exc:
                    if "stopped" in str(exc).lower():
                        self.stop_event.set()
                        break
                    raise
            break
        audio.stop()

    def _handle_signal(self, _signum: int, _frame: Any) -> None:
        self.stop_event.set()


def status_event(
    config: HearingConfig,
    status: str,
    message: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = {
        "type": "status",
        "source": "local",
        "agent_id": config.agent_id,
        "backend": config.backend,
        "model": config.resolved_model(),
        "status": status,
        "message": message,
        "received_at": time.time(),
    }
    if extra is not None:
        event["details"] = extra
    return event


def error_event(
    config: HearingConfig,
    backend: str,
    message: str,
    raw: Any | None = None,
) -> dict[str, Any]:
    event = {
        "type": "error",
        "source": "aliyun",
        "agent_id": config.agent_id,
        "backend": backend,
        "model": config.resolved_model(),
        "message": message,
        "received_at": time.time(),
    }
    if config.include_raw and raw is not None:
        event["raw"] = raw_to_dict(raw)
    return event


def compact_event(event: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in event.items() if value is not None}


def raw_to_dict(value: Any) -> Any:
    if isinstance(value, dict):
        return value
    fields: dict[str, Any] = {}
    for name in ("status_code", "code", "message", "request_id", "output", "usage"):
        try:
            item = getattr(value, name)
        except Exception:
            item = None
        if item is not None:
            fields[name] = item
    return fields or repr(value)


def format_sdk_error(message: Any) -> str:
    fields = raw_to_dict(message)
    if isinstance(fields, dict) and fields:
        return json.dumps(fields, ensure_ascii=False, default=str)
    return str(fields)


def safe_stop_recognizer(recognizer: Recognition) -> None:
    try:
        recognizer.stop()
    except InvalidParameter as exc:
        if "stopped" not in str(exc).lower():
            raise


def preflight_websocket_url(url: str) -> None:
    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "wss" else 80)
    if not host:
        raise SystemExit(f"Invalid WebSocket URL: {url}")
    try:
        with socket.create_connection((host, port), timeout=5):
            return
    except OSError as exc:
        raise SystemExit(f"Cannot connect to Aliyun realtime endpoint: {url}\n{exc}") from exc


def config_from_args() -> HearingConfig:
    parser = argparse.ArgumentParser(description="Agent-facing realtime hearing service.")
    parser.add_argument("--backend", choices=("funasr", "qwen"), default="funasr")
    parser.add_argument("--model", default=None)
    parser.add_argument("--language", default="zh")
    parser.add_argument("--device", default=None)
    parser.add_argument("--chunk-ms", type=int, default=100)
    parser.add_argument("--vad-silence-ms", type=int, default=400)
    parser.add_argument("--vad-threshold", type=float, default=0.2)
    parser.add_argument("--semantic-punctuation", action="store_true")
    parser.add_argument("--workspace", default=os.environ.get("DASHSCOPE_WORKSPACE_ID"))
    parser.add_argument("--region", choices=("beijing", "singapore"), default=os.environ.get("DASHSCOPE_REGION", "beijing"))
    parser.add_argument("--funasr-url", default=os.environ.get("DASHSCOPE_FUNASR_WEBSOCKET_URL"))
    parser.add_argument("--qwen-url", default=os.environ.get("DASHSCOPE_QWEN_REALTIME_URL"))
    parser.add_argument("--skip-preflight", action="store_true")
    parser.add_argument("--no-raw", action="store_true")
    parser.add_argument("--stdout", action="store_true", help="Print JSONL events for standalone testing.")
    parser.add_argument("--agent-id", default="tanyue")
    parser.add_argument("--websocket", action="store_true", help="Start local WebSocket broadcaster.")
    parser.add_argument("--ws-host", default="127.0.0.1")
    parser.add_argument("--ws-port", type=int, default=8765)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise SystemExit("DASHSCOPE_API_KEY is not set.")

    if args.backend == "qwen" and not (args.workspace or args.qwen_url):
        raise SystemExit("Qwen-ASR realtime needs DASHSCOPE_WORKSPACE_ID or --qwen-url.")

    return HearingConfig(
        api_key=api_key,
        backend=args.backend,
        model=args.model,
        language=args.language or None,
        device=args.device,
        chunk_ms=args.chunk_ms,
        vad_silence_ms=args.vad_silence_ms,
        vad_threshold=args.vad_threshold,
        semantic_punctuation=args.semantic_punctuation,
        workspace=args.workspace,
        region=args.region,
        funasr_url=args.funasr_url,
        qwen_url=args.qwen_url,
        skip_preflight=args.skip_preflight,
        include_raw=not args.no_raw,
        emit_stdout=args.stdout or not args.websocket,
        debug=args.debug,
        agent_id=args.agent_id,
    ), args


def main() -> None:
    config, args = config_from_args()
    service = AgentHearing(
        config,
        websocket_host=args.ws_host if args.websocket else None,
        websocket_port=args.ws_port,
    )
    service.run()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Aliyun Model Studio realtime microphone transcription."""

from __future__ import annotations

import argparse
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
from typing import Any
from urllib.parse import urlparse

try:
    import dashscope
    import numpy as np
    import sounddevice as sd
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
FORMAT = "pcm"
BEIJING_WEBSOCKET_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
SINGAPORE_WEBSOCKET_URL = "wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference"
QWEN_BEIJING_URL_TEMPLATE = "wss://{workspace}.cn-beijing.maas.aliyuncs.com/api-ws/v1/realtime"


@dataclass(frozen=True)
class Config:
    api_key: str
    backend: str
    model: str
    language: str | None
    device: int | str | None
    chunk_ms: int
    vad_silence_ms: int
    vad_threshold: float
    semantic_punctuation: bool
    workspace: str | None
    funasr_url: str
    qwen_url: str | None
    skip_preflight: bool
    json_output: bool
    debug: bool


class AudioInput:
    def __init__(self, config: Config) -> None:
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


class FunAsrCallback(RecognitionCallback):
    def __init__(self, config: Config, opened: threading.Event, stopped: threading.Event) -> None:
        self.config = config
        self.opened = opened
        self.stopped = stopped

    def on_open(self) -> None:
        self.opened.set()
        if self.config.debug:
            print("[funasr] connection opened", file=sys.stderr)

    def on_close(self) -> None:
        self.stopped.set()
        if self.config.debug:
            print("[funasr] connection closed", file=sys.stderr)

    def on_complete(self) -> None:
        self.stopped.set()
        if self.config.debug:
            print("[funasr] recognition completed", file=sys.stderr)

    def on_error(self, message: Any) -> None:
        self.stopped.set()
        print(f"[funasr error] {format_sdk_error(message)}", file=sys.stderr)

    def on_event(self, result: RecognitionResult) -> None:
        sentence = result.get_sentence() or {}
        text = sentence.get("text", "")
        if not text:
            if self.config.debug:
                print(f"[funasr debug] {json.dumps(dict(result), ensure_ascii=False)}", file=sys.stderr)
            return

        is_final = RecognitionResult.is_sentence_end(sentence)
        event = {
            "backend": "funasr",
            "model": self.config.model,
            "final": bool(is_final),
            "text": text,
            "request_id": result.get_request_id(),
            "usage": result.get_usage(sentence) if is_final else None,
            "sentence": sentence,
            "received_at": time.time(),
        }
        emit_result(event, self.config.json_output)


class QwenCallback(OmniRealtimeCallback):
    def __init__(self, config: Config, opened: threading.Event, stopped: threading.Event) -> None:
        self.config = config
        self.opened = opened
        self.stopped = stopped

    def on_open(self) -> None:
        self.opened.set()
        if self.config.debug:
            print("[qwen] connection opened", file=sys.stderr)

    def on_close(self, code: int, msg: str) -> None:
        self.stopped.set()
        if self.config.debug:
            print(f"[qwen] connection closed code={code} msg={msg}", file=sys.stderr)

    def on_event(self, response: dict[str, Any]) -> None:
        event_type = response.get("type")
        if event_type == "session.created":
            if self.config.debug:
                print(f"[qwen] session={response.get('session', {}).get('id')}", file=sys.stderr)
            return

        if event_type == "conversation.item.input_audio_transcription.text":
            text = f"{response.get('text', '')}{response.get('stash', '')}"
            if text:
                emit_result(
                    {
                        "backend": "qwen",
                        "model": self.config.model,
                        "final": False,
                        "text": text,
                        "emotion": response.get("emotion"),
                        "event": response,
                        "received_at": time.time(),
                    },
                    self.config.json_output,
                )
            return

        if event_type == "conversation.item.input_audio_transcription.completed":
            emit_result(
                {
                    "backend": "qwen",
                    "model": self.config.model,
                    "final": True,
                    "text": response.get("transcript", ""),
                    "emotion": response.get("emotion"),
                    "event": response,
                    "received_at": time.time(),
                },
                self.config.json_output,
            )
            return

        if event_type in {"input_audio_buffer.speech_started", "input_audio_buffer.speech_stopped"}:
            if self.config.debug:
                print(f"[qwen] {event_type}", file=sys.stderr)
            return

        if self.config.debug:
            print(f"[qwen debug] {json.dumps(response, ensure_ascii=False)}", file=sys.stderr)


def emit_result(event: dict[str, Any], json_output: bool) -> None:
    if json_output:
        print(json.dumps(event, ensure_ascii=False, default=str), flush=True)
        return

    tag = "final" if event.get("final") else "partial"
    emotion = event.get("emotion")
    prefix = f"[{tag}]"
    if emotion:
        prefix += f"[emotion={emotion}]"
    print(f"{prefix} {event.get('text', '')}", flush=True)


def format_sdk_error(message: Any) -> str:
    fields: dict[str, Any] = {}
    for name in ("status_code", "code", "message", "request_id", "output"):
        try:
            value = getattr(message, name)
        except Exception:
            value = None
        if value is not None:
            fields[name] = value

    if isinstance(message, dict):
        fields.update(message)

    if fields:
        return json.dumps(fields, ensure_ascii=False, default=str)

    try:
        return repr(message)
    except Exception:
        return f"<unprintable {type(message).__name__}>"


class AliyunRealtimeTranscriber:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.stop_event = threading.Event()

    def run(self) -> None:
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
        dashscope.api_key = self.config.api_key

        if self.config.backend == "qwen":
            self._run_qwen()
        else:
            self._run_funasr()

    def _run_funasr(self) -> None:
        dashscope.base_websocket_api_url = self.config.funasr_url
        if not self.config.skip_preflight:
            self._preflight_websocket_url(self.config.funasr_url)

        opened = threading.Event()
        stopped = threading.Event()
        callback = FunAsrCallback(self.config, opened, stopped)
        recognizer = Recognition(
            model=self.config.model,
            format=FORMAT,
            sample_rate=SAMPLE_RATE,
            semantic_punctuation_enabled=self.config.semantic_punctuation,
            max_sentence_silence=self.config.vad_silence_ms,
            callback=callback,
        )

        recognizer.start()
        if not opened.wait(timeout=15):
            raise RuntimeError("Timed out connecting to Aliyun Fun-ASR realtime API.")

        print("Listening with Aliyun Fun-ASR. Press Ctrl+C to stop.", flush=True)
        try:
            with AudioInput(self.config) as audio:
                self._stream_audio(audio, recognizer.send_audio_frame, stopped)
        finally:
            self._safe_stop_recognizer(recognizer)
            stopped.wait(timeout=5)
            print(
                "[metric] requestId={}, first_package_delay_ms={}, last_package_delay_ms={}".format(
                    recognizer.get_last_request_id(),
                    recognizer.get_first_package_delay(),
                    recognizer.get_last_package_delay(),
                ),
                flush=True,
            )

    def _run_qwen(self) -> None:
        opened = threading.Event()
        stopped = threading.Event()
        callback = QwenCallback(self.config, opened, stopped)
        conversation = OmniRealtimeConversation(
            model=self.config.model,
            url=self._qwen_url(),
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
            input_audio_format=FORMAT,
        )
        conversation.update_session(
            output_modalities=[MultiModality.TEXT],
            enable_input_audio_transcription=True,
            enable_turn_detection=True,
            turn_detection_threshold=self.config.vad_threshold,
            turn_detection_silence_duration_ms=self.config.vad_silence_ms,
            transcription_params=params,
        )

        print("Listening with Aliyun Qwen-ASR. Press Ctrl+C to stop.", flush=True)
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
        send: Any,
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

    def _safe_stop_recognizer(self, recognizer: Recognition) -> None:
        try:
            recognizer.stop()
        except InvalidParameter as exc:
            if "stopped" not in str(exc).lower():
                raise

    def _qwen_url(self) -> str | None:
        if self.config.qwen_url:
            return self.config.qwen_url
        if self.config.workspace:
            return QWEN_BEIJING_URL_TEMPLATE.format(workspace=self.config.workspace)
        return None

    def _preflight_websocket_url(self, url: str) -> None:
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        if not host:
            raise SystemExit(f"Invalid WebSocket URL: {url}")

        try:
            with socket.create_connection((host, port), timeout=5):
                return
        except OSError as exc:
            proxy_keys = ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy")
            proxy_hint = ", ".join(k for k in proxy_keys if os.environ.get(k)) or "none"
            raise SystemExit(
                "Cannot connect to Aliyun realtime endpoint before opening microphone.\n"
                f"endpoint: {url}\n"
                f"error: {exc}\n"
                f"proxy env detected: {proxy_hint}\n"
                "Try: check DNS/network, switch --region singapore if your API key is from Singapore, "
                "or pass --funasr-url with the endpoint shown in your Model Studio console."
            ) from exc

    def _handle_signal(self, _signum: int, _frame: Any) -> None:
        self.stop_event.set()


def parse_args() -> Config:
    parser = argparse.ArgumentParser(description="Aliyun realtime microphone transcription.")
    parser.add_argument(
        "--backend",
        choices=("funasr", "qwen"),
        default="funasr",
        help="funasr gives low-latency text and timestamps; qwen gives 7-class emotion.",
    )
    parser.add_argument("--model", default=None, help="Override model name.")
    parser.add_argument("--language", default="zh", help="Language hint, e.g. zh or en. Use '' to disable.")
    parser.add_argument("--device", default=None, help="sounddevice input device id or name.")
    parser.add_argument("--chunk-ms", type=int, default=100)
    parser.add_argument("--vad-silence-ms", type=int, default=400)
    parser.add_argument("--vad-threshold", type=float, default=0.2)
    parser.add_argument(
        "--semantic-punctuation",
        action="store_true",
        help="Enable semantic punctuation for Fun-ASR. Leave off for lowest latency and full timestamp fields.",
    )
    parser.add_argument("--workspace", default=os.environ.get("DASHSCOPE_WORKSPACE_ID"))
    parser.add_argument(
        "--region",
        choices=("beijing", "singapore"),
        default=os.environ.get("DASHSCOPE_REGION", "beijing"),
        help="Endpoint preset for Fun-ASR. Beijing and Singapore API keys are different.",
    )
    parser.add_argument(
        "--funasr-url",
        default=os.environ.get("DASHSCOPE_FUNASR_WEBSOCKET_URL"),
        help="Override Fun-ASR WebSocket URL.",
    )
    parser.add_argument("--qwen-url", default=os.environ.get("DASHSCOPE_QWEN_REALTIME_URL"))
    parser.add_argument("--skip-preflight", action="store_true")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON lines.")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise SystemExit("DASHSCOPE_API_KEY is not set.")

    if args.backend == "qwen" and not (args.workspace or args.qwen_url):
        raise SystemExit(
            "Qwen-ASR realtime needs a Model Studio workspace endpoint. "
            "Set DASHSCOPE_WORKSPACE_ID or pass --qwen-url."
        )

    model = args.model
    if not model:
        model = "qwen3-asr-flash-realtime" if args.backend == "qwen" else "fun-asr-realtime"

    funasr_url = args.funasr_url
    if not funasr_url:
        funasr_url = SINGAPORE_WEBSOCKET_URL if args.region == "singapore" else BEIJING_WEBSOCKET_URL

    return Config(
        api_key=api_key,
        backend=args.backend,
        model=model,
        language=args.language or None,
        device=args.device,
        chunk_ms=args.chunk_ms,
        vad_silence_ms=args.vad_silence_ms,
        vad_threshold=args.vad_threshold,
        semantic_punctuation=args.semantic_punctuation,
        workspace=args.workspace,
        funasr_url=funasr_url,
        qwen_url=args.qwen_url,
        skip_preflight=args.skip_preflight,
        json_output=args.json,
        debug=args.debug,
    )


def main() -> None:
    config = parse_args()
    AliyunRealtimeTranscriber(config).run()


if __name__ == "__main__":
    main()

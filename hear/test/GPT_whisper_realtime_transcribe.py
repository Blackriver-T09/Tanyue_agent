#!/usr/bin/env python3
"""Realtime microphone transcription for the Tanyue love agent."""

from __future__ import annotations

import argparse
import base64
import json
import os
import queue
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

try:
    import numpy as np
    import sounddevice as sd
    import websocket
except ImportError as exc:
    missing = exc.name or "dependency"
    raise SystemExit(
        f"Missing dependency: {missing}\n"
        "Install with: conda activate Tanyue && pip install -r hear/requirements.txt"
    ) from exc


OPENAI_REALTIME_URL = "wss://api.openai.com/v1/realtime"
OPENAI_REALTIME_CLIENT_SECRETS_URL = "https://api.openai.com/v1/realtime/client_secrets"
SAMPLE_RATE = 24_000
CHANNELS = 1


@dataclass(frozen=True)
class TranscriptionConfig:
    api_key: str
    transcription_model: str
    language: str | None
    delay: str
    device: int | str | None
    chunk_ms: int
    silence_ms: int
    max_segment_ms: int
    rms_threshold: float
    use_client_secret: bool
    debug: bool


class RealtimeTranscriber:
    def __init__(self, config: TranscriptionConfig) -> None:
        self.config = config
        self.audio_queue: queue.Queue[bytes | None] = queue.Queue(maxsize=200)
        self.stop_event = threading.Event()
        self.connected_event = threading.Event()
        self.failed_event = threading.Event()
        self.ws: websocket.WebSocketApp | None = None
        self.current_delta: dict[str, str] = {}
        self.last_error: str | None = None
        self.last_audio_at = 0.0
        self.segment_started_at = 0.0
        self.has_speech = False
        self.commit_lock = threading.Lock()

    def run(self) -> None:
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

        ws_thread = threading.Thread(target=self._run_websocket, daemon=True)
        ws_thread.start()
        if not self._wait_for_connection(timeout=15):
            detail = f": {self.last_error}" if self.last_error else ""
            self.stop_event.set()
            if self.ws:
                self.ws.close()
            ws_thread.join(timeout=3)
            raise RuntimeError(f"Could not connect to OpenAI Realtime API{detail}")

        print("Listening. Speak into the microphone. Press Ctrl+C to stop.", flush=True)
        self._capture_and_send_audio()
        self.stop_event.set()
        self._commit_if_needed(force=True)
        if self.ws:
            self.ws.close()
        ws_thread.join(timeout=3)

    def _run_websocket(self) -> None:
        try:
            token = self._create_client_secret() if self.config.use_client_secret else self.config.api_key
        except Exception:
            return
        headers = [f"Authorization: Bearer {token}"]
        self.ws = websocket.WebSocketApp(
            OPENAI_REALTIME_URL,
            header=headers,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self.ws.run_forever(ping_interval=20, ping_timeout=10)

    def _wait_for_connection(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.connected_event.is_set():
                return True
            if self.failed_event.is_set():
                return False
            time.sleep(0.05)
        return False

    def _create_client_secret(self) -> str:
        session = self._session_config()
        body = json.dumps({"session": session}).encode("utf-8")
        request = urllib.request.Request(
            OPENAI_REALTIME_CLIENT_SECRETS_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            self.last_error = f"client secret request failed: HTTP {exc.code} {error_body}"
            self.failed_event.set()
            raise
        except Exception as exc:
            self.last_error = f"client secret request failed: {exc}"
            self.failed_event.set()
            raise

        value = payload.get("value")
        if not value:
            self.last_error = f"client secret response missing value: {payload}"
            self.failed_event.set()
            raise RuntimeError(self.last_error)
        return value

    def _on_open(self, ws: websocket.WebSocketApp) -> None:
        ws.send(json.dumps({"type": "session.update", "session": self._session_config()}))
        self.connected_event.set()

    def _session_config(self) -> dict[str, Any]:
        session: dict[str, Any] = {
            "type": "transcription",
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": SAMPLE_RATE},
                    "transcription": {
                        "model": self.config.transcription_model,
                        "delay": self.config.delay,
                    },
                    "turn_detection": None,
                }
            },
        }
        if self.config.language:
            session["audio"]["input"]["transcription"]["language"] = self.config.language
        return session

    def _on_message(self, _ws: websocket.WebSocketApp, message: str) -> None:
        event = json.loads(message)
        event_type = event.get("type")

        if event_type == "conversation.item.input_audio_transcription.delta":
            item_id = event.get("item_id", "unknown")
            delta = event.get("delta", "")
            self.current_delta[item_id] = self.current_delta.get(item_id, "") + delta
            print(delta, end="", flush=True)
            return

        if event_type == "conversation.item.input_audio_transcription.completed":
            item_id = event.get("item_id", "unknown")
            transcript = event.get("transcript") or self.current_delta.pop(item_id, "")
            print(f"\n[final] {transcript}", flush=True)
            return

        if event_type == "error":
            print(f"\n[openai error] {json.dumps(event, ensure_ascii=False)}", file=sys.stderr)
            return

        if self.config.debug:
            print(f"\n[debug] {json.dumps(event, ensure_ascii=False)}", file=sys.stderr)

    def _on_error(self, _ws: websocket.WebSocketApp, error: Any) -> None:
        self.last_error = f"websocket error: {error}"
        print(f"\n[websocket error] {error}", file=sys.stderr)
        self.failed_event.set()
        self.stop_event.set()

    def _on_close(
        self,
        _ws: websocket.WebSocketApp,
        status_code: int | None,
        message: str | None,
    ) -> None:
        if not self.stop_event.is_set():
            self.last_error = f"websocket closed: {status_code or ''} {message or ''}".strip()
            print(f"\n[websocket closed] {status_code or ''} {message or ''}", file=sys.stderr)
            self.failed_event.set()
            self.stop_event.set()

    def _capture_and_send_audio(self) -> None:
        blocksize = int(SAMPLE_RATE * self.config.chunk_ms / 1000)

        def callback(indata: np.ndarray, _frames: int, _time: Any, status: sd.CallbackFlags) -> None:
            if status and self.config.debug:
                print(f"\n[audio status] {status}", file=sys.stderr)
            try:
                self.audio_queue.put_nowait(indata.copy().tobytes())
            except queue.Full:
                if self.config.debug:
                    print("\n[audio warning] dropping audio chunk; queue is full", file=sys.stderr)

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=blocksize,
            device=self.config.device,
            callback=callback,
        ):
            while not self.stop_event.is_set():
                try:
                    chunk = self.audio_queue.get(timeout=0.2)
                except queue.Empty:
                    self._commit_if_needed()
                    continue
                if chunk is None:
                    break
                self._send_audio_chunk(chunk)
                self._update_segment_state(chunk)
                self._commit_if_needed()

    def _send_audio_chunk(self, chunk: bytes) -> None:
        if not self.ws:
            return
        encoded = base64.b64encode(chunk).decode("ascii")
        self.ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": encoded}))

    def _update_segment_state(self, chunk: bytes) -> None:
        samples = np.frombuffer(chunk, dtype=np.int16)
        if samples.size == 0:
            return
        rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
        now = time.monotonic()
        if rms >= self.config.rms_threshold:
            if not self.has_speech:
                self.segment_started_at = now
            self.has_speech = True
            self.last_audio_at = now

    def _commit_if_needed(self, force: bool = False) -> None:
        if not self.has_speech or not self.ws:
            return
        now = time.monotonic()
        silence_elapsed_ms = (now - self.last_audio_at) * 1000
        segment_elapsed_ms = (now - self.segment_started_at) * 1000
        should_commit = (
            force
            or silence_elapsed_ms >= self.config.silence_ms
            or segment_elapsed_ms >= self.config.max_segment_ms
        )
        if not should_commit:
            return
        with self.commit_lock:
            self.ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
            self.has_speech = False
            self.last_audio_at = 0.0
            self.segment_started_at = 0.0

    def _handle_signal(self, _signum: int, _frame: Any) -> None:
        self.stop_event.set()


def parse_args() -> TranscriptionConfig:
    parser = argparse.ArgumentParser(description="Realtime OpenAI microphone transcription.")
    parser.add_argument("--transcription-model", default="gpt-realtime-whisper")
    parser.add_argument("--language", default="zh", help="Optional BCP-47 language hint. Use '' to disable.")
    parser.add_argument(
        "--delay",
        default="high",
        choices=("minimal", "low", "medium", "high", "xhigh"),
        help="Accuracy/latency tradeoff for gpt-realtime-whisper.",
    )
    parser.add_argument("--device", default=None, help="sounddevice input device id or name.")
    parser.add_argument("--chunk-ms", type=int, default=100)
    parser.add_argument("--silence-ms", type=int, default=800)
    parser.add_argument("--max-segment-ms", type=int, default=10_000)
    parser.add_argument("--rms-threshold", type=float, default=300.0)
    parser.add_argument(
        "--no-client-secret",
        action="store_true",
        help="Connect with OPENAI_API_KEY directly instead of creating a transcription client secret.",
    )
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set.")

    return TranscriptionConfig(
        api_key=api_key,
        transcription_model=args.transcription_model,
        language=args.language or None,
        delay=args.delay,
        device=args.device,
        chunk_ms=args.chunk_ms,
        silence_ms=args.silence_ms,
        max_segment_ms=args.max_segment_ms,
        rms_threshold=args.rms_threshold,
        use_client_secret=not args.no_client_secret,
        debug=args.debug,
    )


def main() -> None:
    config = parse_args()
    RealtimeTranscriber(config).run()


if __name__ == "__main__":
    main()

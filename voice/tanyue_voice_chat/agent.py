from __future__ import annotations

import queue
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

try:
    from hear.agent_hearing import AgentHearing, HearingConfig
except ImportError as exc:
    raise SystemExit(
        "Missing hearing dependencies. Activate the Tanyue environment and install hear requirements first."
    ) from exc

from ..tanyue_voice_remote import RemoteTTSClient, RemoteTTSConfig, TTSRequest
from .qwen_flash import QwenFlashClient, QwenFlashConfig


_TURN_END = object()


@dataclass(frozen=True)
class VoiceConversationConfig:
    api_key: str
    hearing_backend: str = "funasr"
    hearing_language: str | None = "zh"
    hearing_device: int | str | None = None
    hearing_chunk_ms: int = 60
    hearing_vad_silence_ms: int = 320
    hearing_vad_threshold: float = 0.2
    hearing_workspace: str | None = None
    hearing_region: str = "beijing"
    hearing_funasr_url: str | None = None
    hearing_qwen_url: str | None = None
    hearing_skip_preflight: bool = False
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen3.6-flash"
    qwen_temperature: float = 0.7
    qwen_top_p: float = 0.8
    qwen_max_tokens: int | None = None
    tts_api_base: str = "https://frp-run.com:56330"
    tts_emotion: str = "温柔、亲近"
    tts_emotion_strength: str = "strong"
    tts_mode: str = "auto"
    tts_speed: float = 1.0
    tts_use_env_proxy: bool = False
    tts_resolve_ip: str | None = "183.131.59.150"
    tts_segment_min_chars: int = 12
    tts_segment_max_chars: int = 28
    tts_segment_flush_seconds: float = 0.9
    post_tts_cooldown_seconds: float = 1.5
    history_turns: int = 8
    system_prompt: str = (
        "你是Tanyue的语音对话助手。请只用一句简短、自然、口语化的中文回答，"
        "尽量不超过30个汉字，不要追问，不要展开成多句。"
    )


class VoiceConversationAgent:
    def __init__(self, config: VoiceConversationConfig) -> None:
        self.config = config
        hearing_config = HearingConfig(
            api_key=config.api_key,
            backend=config.hearing_backend,
            language=config.hearing_language,
            device=config.hearing_device,
            chunk_ms=config.hearing_chunk_ms,
            vad_silence_ms=config.hearing_vad_silence_ms,
            vad_threshold=config.hearing_vad_threshold,
            workspace=config.hearing_workspace,
            region=config.hearing_region,
            funasr_url=config.hearing_funasr_url,
            qwen_url=config.hearing_qwen_url,
            skip_preflight=config.hearing_skip_preflight,
            include_raw=False,
            emit_stdout=False,
        )
        self._turns: queue.Queue[str] = queue.Queue()
        self._stop = threading.Event()
        self._assistant_busy = threading.Event()
        self._console_lock = threading.Lock()
        self._partial_line = ""
        self._history: list[dict[str, Any]] = [{"role": "system", "content": config.system_prompt}]
        self._worker: threading.Thread | None = None
        self._tts_worker: threading.Thread | None = None
        self._tts_queue: queue.Queue[object] = queue.Queue(maxsize=50)
        self._tts_turn_done = threading.Event()
        self._tts_buffer = ""
        self._tts_buffer_started_at: float | None = None
        self._ignore_hearing_until = 0.0
        self._hearing = AgentHearing(hearing_config, on_event=self._on_hearing_event)
        self._qwen = QwenFlashClient(
            QwenFlashConfig(
                api_key=config.api_key,
                base_url=config.qwen_base_url,
                model=config.qwen_model,
                temperature=config.qwen_temperature,
                top_p=config.qwen_top_p,
                max_tokens=config.qwen_max_tokens,
            )
        )
        self._tts = RemoteTTSClient(
            RemoteTTSConfig(
                api_base=config.tts_api_base,
                use_env_proxy=config.tts_use_env_proxy,
                resolve_ip=config.tts_resolve_ip,
            )
        )

    def run(self) -> None:
        self._print_line("Listening. Speak into the microphone. Ctrl+C to stop.")
        self._hearing.start_background()
        self._worker = threading.Thread(target=self._assistant_loop, daemon=True)
        self._worker.start()
        self._tts_worker = threading.Thread(target=self._tts_loop, daemon=True)
        self._tts_worker.start()
        try:
            while not self._stop.is_set():
                time.sleep(0.2)
        except KeyboardInterrupt:
            self.stop()
        finally:
            self.stop()

    def stop(self) -> None:
        if self._stop.is_set():
            return
        self._stop.set()
        self._hearing.stop()
        try:
            self._tts_queue.put_nowait(_TURN_END)
        except queue.Full:
            pass
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=5)
        if self._tts_worker and self._tts_worker.is_alive():
            self._tts_worker.join(timeout=5)

    def _on_hearing_event(self, event: dict[str, Any]) -> None:
        if event.get("type") != "transcription":
            return

        if self._assistant_busy.is_set():
            return

        text = (event.get("text") or "").strip()
        if not text:
            return

        if time.monotonic() < self._ignore_hearing_until:
            return

        if event.get("final"):
            self._print_line("")
            self._print_line(f"[user] {text}")
            self._turns.put(text)
            self._partial_line = ""
            return

        self._render_partial(text)

    def _assistant_loop(self) -> None:
        while not self._stop.is_set():
            try:
                user_text = self._turns.get(timeout=0.2)
            except queue.Empty:
                continue

            user_text = user_text.strip()
            if not user_text:
                continue

            self._assistant_busy.set()
            try:
                reply = self._generate_reply(user_text)
                if reply:
                    self._flush_tts_buffer(final=True)
                    self._finalize_tts_turn()
            except Exception as exc:
                self._print_line(f"[error] {exc}")
            finally:
                self._clear_tts_buffer()
                self._assistant_busy.clear()

    def _generate_reply(self, user_text: str) -> str:
        self._history.append({"role": "user", "content": user_text})
        self._trim_history()

        reply_chunks: list[str] = []
        self._print("[assistant] ")
        for delta, _event in self._qwen.stream_chat(self._history):
            if self._stop.is_set():
                break
            reply_chunks.append(delta)
            self._print(delta)
            self._append_tts_text(delta)
        self._print_line("")

        reply = "".join(reply_chunks).strip()
        if not reply:
            reply = "我在。"
        self._history.append({"role": "assistant", "content": reply})
        self._trim_history()
        self._print_line(f"[reply] {reply}")
        return reply

    def _tts_loop(self) -> None:
        while not self._stop.is_set():
            try:
                segment = self._tts_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if segment is _TURN_END:
                self._tts_turn_done.set()
                continue
            if not isinstance(segment, str):
                continue
            segment = segment.strip()
            if not segment:
                continue

            try:
                self._speak(segment)
            except Exception as exc:
                self._print_line(f"[tts error] {exc}")

    def _append_tts_text(self, delta: str) -> None:
        if not delta:
            return
        if not self._tts_buffer:
            self._tts_buffer_started_at = time.monotonic()
        self._tts_buffer += delta
        for segment in self._drain_ready_tts_segments(final=False):
            self._enqueue_tts_segment(segment)

    def _flush_tts_buffer(self, final: bool = False) -> None:
        for segment in self._drain_ready_tts_segments(final=final):
            self._enqueue_tts_segment(segment)

    def _enqueue_tts_segment(self, segment: str) -> None:
        segment = segment.strip()
        if not segment:
            return
        try:
            self._tts_queue.put_nowait(segment)
        except queue.Full:
            self._print_line("[tts] queue full; dropping segment")

    def _finalize_tts_turn(self) -> None:
        self._tts_turn_done.clear()
        try:
            self._tts_queue.put_nowait(_TURN_END)
        except queue.Full:
            self._tts_turn_done.set()
            return
        self._tts_turn_done.wait(timeout=120)
        self._ignore_hearing_until = time.monotonic() + self.config.post_tts_cooldown_seconds

    def _clear_tts_buffer(self) -> None:
        self._tts_buffer = ""
        self._tts_buffer_started_at = None

    def _drain_ready_tts_segments(self, final: bool) -> list[str]:
        ready: list[str] = []
        while True:
            segment, remainder, should_emit = self._split_tts_buffer(final=final)
            if not should_emit:
                break
            if segment:
                ready.append(segment)
            self._tts_buffer = remainder
            self._tts_buffer_started_at = time.monotonic() if remainder else None
        return ready

    def _split_tts_buffer(self, final: bool) -> tuple[str, str, bool]:
        buf = self._tts_buffer.strip()
        if not buf:
            return "", "", False

        strong_punct = "。！？!?；;\n"
        weak_punct = "，,、"

        for idx, ch in enumerate(buf):
            if ch in strong_punct:
                return buf[: idx + 1], buf[idx + 1 :].lstrip(), True

        if len(buf) >= self.config.tts_segment_min_chars:
            for idx, ch in enumerate(buf):
                if ch in weak_punct and idx + 1 >= self.config.tts_segment_min_chars:
                    return buf[: idx + 1], buf[idx + 1 :].lstrip(), True

        age = None
        if self._tts_buffer_started_at is not None:
            age = time.monotonic() - self._tts_buffer_started_at
        if final or len(buf) >= self.config.tts_segment_max_chars:
            return buf[: self.config.tts_segment_max_chars], buf[self.config.tts_segment_max_chars :].lstrip(), True
        if age is not None and age >= self.config.tts_segment_flush_seconds and len(buf) >= max(6, self.config.tts_segment_min_chars // 2):
            return buf, "", True
        return "", buf, False

    def _speak(self, text: str) -> None:
        ffplay = shutil.which("ffplay")
        if not ffplay:
            raise RuntimeError("ffplay not found. Install ffmpeg first.")

        request = TTSRequest(
            text=text,
            emotion=self.config.tts_emotion,
            emotion_strength=self.config.tts_emotion_strength,
            mode=self.config.tts_mode,
            speed=self.config.tts_speed,
        )

        player = subprocess.Popen(
            [
                ffplay,
                "-autoexit",
                "-nodisp",
                "-f",
                "s16le",
                "-ar",
                "24000",
                "-ch_layout",
                "mono",
                "-",
            ],
            stdin=subprocess.PIPE,
        )
        self._print_line("[tts] playing")
        try:
            for chunk in self._tts.stream_pcm(request):
                if self._stop.is_set():
                    break
                if player.stdin is None:
                    break
                try:
                    player.stdin.write(chunk)
                    player.stdin.flush()
                except BrokenPipeError:
                    break
        finally:
            if player.stdin:
                try:
                    player.stdin.close()
                except BrokenPipeError:
                    pass
            player.wait()

    def _trim_history(self) -> None:
        system = self._history[:1]
        tail = self._history[1:]
        limit = max(self.config.history_turns * 2, 2)
        if len(tail) > limit:
            tail = tail[-limit:]
        self._history = system + tail

    def _render_partial(self, text: str) -> None:
        self._partial_line = text
        with self._console_lock:
            sys.stdout.write("\r")
            sys.stdout.write(f"[user] {text}   ")
            sys.stdout.flush()

    def _print(self, text: str) -> None:
        with self._console_lock:
            sys.stdout.write(text)
            sys.stdout.flush()

    def _print_line(self, text: str) -> None:
        with self._console_lock:
            sys.stdout.write("\r")
            sys.stdout.write("\033[K")
            sys.stdout.write(text)
            sys.stdout.write("\n")
            sys.stdout.flush()

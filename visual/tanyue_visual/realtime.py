from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import numpy as np

from .emotion import EmotionResult, OpenFaceEmotionRecognizer


@dataclass
class RealtimeEmotionState:
    results: list[EmotionResult]
    infer_fps: float
    last_infer_at: float


class RealtimeEmotionWorker:
    """Run OpenFace inference in the background over the latest video frame."""

    def __init__(
        self,
        recognizer: OpenFaceEmotionRecognizer,
        infer_interval: float = 0.5,
    ):
        self.recognizer = recognizer
        self.infer_interval = infer_interval
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._latest_frame: np.ndarray | None = None
        self._state = RealtimeEmotionState(results=[], infer_fps=0.0, last_infer_at=0.0)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="openface-inference", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def update_frame(self, frame: np.ndarray) -> None:
        with self._lock:
            self._latest_frame = frame.copy()

    def get_state(self) -> RealtimeEmotionState:
        with self._lock:
            return RealtimeEmotionState(
                results=list(self._state.results),
                infer_fps=self._state.infer_fps,
                last_infer_at=self._state.last_infer_at,
            )

    def _run(self) -> None:
        last_run = 0.0
        while not self._stop_event.is_set():
            now = time.perf_counter()
            wait_time = self.infer_interval - (now - last_run)
            if wait_time > 0:
                self._stop_event.wait(min(wait_time, 0.05))
                continue

            with self._lock:
                frame = None if self._latest_frame is None else self._latest_frame.copy()

            if frame is None:
                self._stop_event.wait(0.01)
                continue

            started = time.perf_counter()
            results = self.recognizer.predict(frame)
            elapsed = max(time.perf_counter() - started, 1e-6)
            with self._lock:
                self._state = RealtimeEmotionState(
                    results=results,
                    infer_fps=1.0 / elapsed,
                    last_infer_at=time.perf_counter(),
                )
            last_run = time.perf_counter()

    def __enter__(self) -> "RealtimeEmotionWorker":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

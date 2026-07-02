from __future__ import annotations

import platform
import time
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True)
class CameraConfig:
    index: int = 0
    backend: str = "auto"
    frame_width: int = 1280
    frame_height: int = 720
    warmup_frames: int = 30
    allow_black: bool = False


def camera_backend(choice: str) -> int:
    if choice == "avfoundation":
        return cv2.CAP_AVFOUNDATION
    if choice == "any":
        return cv2.CAP_ANY
    if platform.system() == "Darwin":
        return cv2.CAP_AVFOUNDATION
    return cv2.CAP_ANY


def frame_stats(frame: np.ndarray | None) -> tuple[float, float]:
    if frame is None:
        return 0.0, 0.0
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(gray.mean()), float(gray.std())


def is_black_frame(frame: np.ndarray | None) -> bool:
    mean, std = frame_stats(frame)
    return mean < 3.0 and std < 3.0


def list_cameras(backend: str = "auto", max_index: int = 6) -> list[dict[str, object]]:
    results = []
    for index in range(max_index + 1):
        cap = cv2.VideoCapture(index, camera_backend(backend))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        opened = cap.isOpened()
        read_ok, frame = (False, None)
        if opened:
            for _ in range(20):
                read_ok, frame = cap.read()
                if read_ok and frame is not None and not is_black_frame(frame):
                    break
                time.sleep(0.03)
        mean, std = frame_stats(frame)
        results.append(
            {
                "index": index,
                "opened": opened,
                "read": read_ok,
                "shape": None if frame is None else frame.shape,
                "mean": mean,
                "std": std,
                "black": is_black_frame(frame),
            }
        )
        cap.release()
    return results


class CameraSource:
    def __init__(self, config: CameraConfig):
        self.config = config
        self.cap: cv2.VideoCapture | None = None
        self.pending_frame: np.ndarray | None = None

    def open(self) -> None:
        self.cap = cv2.VideoCapture(self.config.index, camera_backend(self.config.backend))
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.frame_width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.frame_height)
        if not self.cap.isOpened():
            raise RuntimeError(f"Could not open camera index {self.config.index}.")

        frame, mean, std = self._read_warmup_frame()
        if frame is None:
            self.release()
            raise RuntimeError(
                f"Opened camera index {self.config.index}, but could not read frames."
            )
        if is_black_frame(frame) and not self.config.allow_black:
            self.release()
            raise RuntimeError(
                f"Camera index {self.config.index} is returning black frames "
                f"(mean={mean:.1f}, std={std:.1f}). Run --list-cameras or use another index."
            )
        self.pending_frame = frame

    def read(self) -> tuple[bool, np.ndarray | None]:
        if self.pending_frame is not None:
            frame = self.pending_frame
            self.pending_frame = None
            return True, frame
        if self.cap is None:
            raise RuntimeError("CameraSource.open() must be called before read().")
        return self.cap.read()

    def release(self) -> None:
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def _read_warmup_frame(self) -> tuple[np.ndarray | None, float, float]:
        if self.cap is None:
            return None, 0.0, 0.0
        frame = None
        last_mean = 0.0
        last_std = 0.0
        for _ in range(max(1, self.config.warmup_frames)):
            ok, candidate = self.cap.read()
            if ok and candidate is not None:
                frame = candidate
                last_mean, last_std = frame_stats(frame)
                if self.config.allow_black or not is_black_frame(frame):
                    break
            time.sleep(0.05)
        return frame, last_mean, last_std

    def __enter__(self) -> "CameraSource":
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()

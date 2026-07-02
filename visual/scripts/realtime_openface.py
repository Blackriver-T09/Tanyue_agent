#!/usr/bin/env python
"""Realtime webcam emotion recognition demo for Tanyue."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from tanyue_visual import CameraConfig, CameraSource, OpenFaceEmotionRecognizer, RealtimeEmotionWorker, list_cameras
from tanyue_visual.emotion import draw_emotion_results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run realtime facial emotion recognition using OpenFace 3.0."
    )
    parser.add_argument("--camera", type=int, default=0, help="Camera index.")
    parser.add_argument(
        "--list-cameras",
        action="store_true",
        help="Scan camera indexes and exit.",
    )
    parser.add_argument(
        "--backend",
        choices=["auto", "avfoundation", "any"],
        default="auto",
        help="OpenCV camera backend.",
    )
    parser.add_argument(
        "--device",
        choices=["auto", "cpu", "mps", "cuda"],
        default="auto",
        help="Inference device. Use cpu on macOS if mps gives unsupported-op errors.",
    )
    parser.add_argument(
        "--weights-dir",
        type=Path,
        default=PROJECT_DIR / "weights",
        help="Directory containing OpenFace 3.0 weights.",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.65,
        help="Minimum face detection score to display.",
    )
    parser.add_argument(
        "--frame-width",
        type=int,
        default=1280,
        help="Requested camera frame width.",
    )
    parser.add_argument(
        "--frame-height",
        type=int,
        default=720,
        help="Requested camera frame height.",
    )
    parser.add_argument(
        "--warmup-frames",
        type=int,
        default=30,
        help="Frames to wait for camera startup before failing.",
    )
    parser.add_argument(
        "--allow-black",
        action="store_true",
        help="Allow all-black frames instead of failing during camera warm-up.",
    )
    parser.add_argument(
        "--infer-interval",
        type=float,
        default=0.5,
        help="Seconds between OpenFace inference runs. Display remains realtime.",
    )
    parser.add_argument(
        "--prediction-ttl",
        type=float,
        default=2.0,
        help="Seconds to keep drawing the latest prediction.",
    )
    parser.add_argument(
        "--no-landmarks",
        action="store_true",
        help="Disable STAR landmarks for faster inference.",
    )
    parser.add_argument(
        "--no-head-pose",
        action="store_true",
        help="Disable head pose estimation.",
    )
    return parser.parse_args()


def print_camera_scan(backend: str) -> None:
    for info in list_cameras(backend=backend):
        print(
            f"camera {info['index']}: opened={info['opened']} read={info['read']} "
            f"shape={info['shape']} mean={info['mean']:.1f} "
            f"std={info['std']:.1f} black={info['black']}"
        )


def main() -> int:
    args = parse_args()
    if args.list_cameras:
        print_camera_scan(args.backend)
        return 0

    camera_config = CameraConfig(
        index=args.camera,
        backend=args.backend,
        frame_width=args.frame_width,
        frame_height=args.frame_height,
        warmup_frames=args.warmup_frames,
        allow_black=args.allow_black,
    )

    recognizer = OpenFaceEmotionRecognizer(
        weights_dir=args.weights_dir,
        device=args.device,
        min_score=args.min_score,
        include_landmarks=not args.no_landmarks,
        include_head_pose=not args.no_head_pose,
    )

    print("Press q or Esc in the camera window to quit.")
    display_fps = 0.0
    last_time = time.perf_counter()

    with CameraSource(camera_config) as camera, RealtimeEmotionWorker(
        recognizer=recognizer,
        infer_interval=args.infer_interval,
    ) as worker:
        while True:
            ok, frame = camera.read()
            if not ok or frame is None:
                print("Could not read frame from camera.")
                break

            worker.update_frame(frame)
            state = worker.get_state()

            now = time.perf_counter()
            draw_emotion_results(frame, state.results, ttl=args.prediction_ttl, now=now)

            display_fps = 0.9 * display_fps + 0.1 * (1.0 / max(now - last_time, 1e-6))
            last_time = now
            cv2.putText(
                frame,
                f"Display {display_fps:.1f} FPS | OpenFace {state.infer_fps:.1f} FPS | {recognizer.device}",
                (12, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.75,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )
            cv2.imshow("Tanyue realtime emotion recognition", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                break

    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

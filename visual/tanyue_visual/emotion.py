from __future__ import annotations

import os
import sys
import time
from contextlib import redirect_stdout
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import torch


PROJECT_DIR = Path(__file__).resolve().parents[1]

EMOTIONS = [
    "neutral",
    "happy",
    "sad",
    "surprise",
    "fear",
    "disgust",
    "anger",
    "contempt",
]

AU_LABELS = ["AU1", "AU2", "AU4", "AU6", "AU9", "AU12", "AU25", "AU26"]


@dataclass
class FaceAnalysisResult:
    face_id: int
    bbox: tuple[int, int, int, int]
    face_score: float
    emotion: str
    emotion_confidence: float
    emotion_scores: dict[str, float]
    gaze: dict[str, float | bool]
    action_units: dict[str, float]
    landmarks: list[tuple[float, float]] | None
    head_pose: dict[str, float] | None
    signals: dict[str, bool | float]
    timestamp: float

    def as_dict(self) -> dict[str, object]:
        return {
            "face_id": self.face_id,
            "bbox": self.bbox,
            "face_score": self.face_score,
            "emotion": {
                "label": self.emotion,
                "confidence": self.emotion_confidence,
                "scores": self.emotion_scores,
            },
            "gaze": self.gaze,
            "action_units": self.action_units,
            "landmarks": self.landmarks,
            "head_pose": self.head_pose,
            "signals": self.signals,
            "timestamp": self.timestamp,
        }


# Backward-compatible alias for earlier agent code.
EmotionResult = FaceAnalysisResult


def resolve_device(choice: str) -> str:
    if choice != "auto":
        return choice
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_openface_modules(include_landmarks: bool = False) -> dict[str, Any]:
    original_argv = sys.argv[:]
    sys.argv = [sys.argv[0]]
    try:
        from openface.Pytorch_Retinaface.layers.functions.prior_box import PriorBox
        from openface.Pytorch_Retinaface.utils.box_utils import decode, decode_landm
        from openface.Pytorch_Retinaface.utils.nms.py_cpu_nms import py_cpu_nms
        from openface.face_detection import FaceDetector
        import openface.multitask_model as multitask_module
        from openface.multitask_model import MultitaskPredictor

        LandmarkDetector = None
        if include_landmarks:
            os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-tanyue")
            import scipy.integrate as scipy_integrate

            if not hasattr(scipy_integrate, "simps") and hasattr(scipy_integrate, "simpson"):
                scipy_integrate.simps = scipy_integrate.simpson

            from openface.landmark_detection import LandmarkDetector
            from openface.STAR.conf import base as star_base

            def init_instance_noop(self):
                self.writer = None
                self.logger = None

            star_base.Base.init_instance = init_instance_noop
    finally:
        sys.argv = original_argv

    # openface.multitask_model 0.1.14 misses this import.
    multitask_module.cv2 = cv2
    return {
        "PriorBox": PriorBox,
        "decode": decode,
        "decode_landm": decode_landm,
        "py_cpu_nms": py_cpu_nms,
        "FaceDetector": FaceDetector,
        "MultitaskPredictor": MultitaskPredictor,
        "LandmarkDetector": LandmarkDetector,
    }


def require_weights(weights_dir: Path, include_landmarks: bool = False) -> tuple[Path, Path, Path | None]:
    face_model = weights_dir / "Alignment_RetinaFace.pth"
    multitask_model = weights_dir / "MTL_backbone.pth"
    landmark_model = weights_dir / "Landmark_98.pkl"
    required = [face_model, multitask_model]
    if include_landmarks:
        required.append(landmark_model)
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing OpenFace 3.0 weights: "
            + ", ".join(missing)
            + ". Run: conda run -n Tanyue openface download"
        )
    return face_model, multitask_model, landmark_model if include_landmarks else None


class OpenFaceEmotionRecognizer:
    def __init__(
        self,
        weights_dir: Path | str = PROJECT_DIR / "weights",
        device: str = "auto",
        min_score: float = 0.65,
        include_landmarks: bool = True,
        include_head_pose: bool = True,
    ):
        self.weights_dir = Path(weights_dir)
        self.device = resolve_device(device)
        self.min_score = min_score
        self.include_landmarks = include_landmarks
        self.include_head_pose = include_head_pose
        self.openface_modules = load_openface_modules(include_landmarks=include_landmarks)
        face_model_path, multitask_model_path, landmark_model_path = require_weights(
            self.weights_dir,
            include_landmarks=include_landmarks,
        )

        face_detector_cls = self.openface_modules["FaceDetector"]
        multitask_predictor_cls = self.openface_modules["MultitaskPredictor"]
        self.detector = face_detector_cls(
            model_path=str(face_model_path),
            device=self.device,
            confidence_threshold=0.02,
            nms_threshold=0.4,
            vis_threshold=min_score,
        )
        self.emotion_model = multitask_predictor_cls(
            model_path=str(multitask_model_path),
            device=self.device,
        )

        self.landmark_detector = None
        if include_landmarks and landmark_model_path is not None:
            landmark_cls = self.openface_modules["LandmarkDetector"]
            landmark_device = "cuda" if self.device == "cuda" else "cpu"
            with redirect_stdout(StringIO()):
                self.landmark_detector = landmark_cls(
                    model_path=str(landmark_model_path),
                    device=landmark_device,
                    device_ids=[0] if landmark_device == "cuda" else [-1],
                )

    def predict(self, frame: np.ndarray) -> list[FaceAnalysisResult]:
        results = []
        dets = self._detect_faces(frame)
        timestamp = time.perf_counter()
        landmarks_by_face = self._detect_landmarks(frame, dets) if self.landmark_detector else []

        for face_id, det in enumerate(dets):
            face_score = float(det[4])
            if face_score < self.min_score:
                continue
            face = self._crop_face(frame, det)
            if face is None:
                continue

            emotion_scores, gaze, action_units = self._predict_multitask(face)
            emotion = max(emotion_scores, key=emotion_scores.get)
            emotion_confidence = emotion_scores[emotion]
            x1, y1, x2, y2 = [int(value) for value in det[:4]]

            landmarks = None
            if face_id < len(landmarks_by_face):
                landmarks = self._serialize_landmarks(landmarks_by_face[face_id])
            head_pose = estimate_head_pose(frame.shape, landmarks) if self.include_head_pose else None
            signals = infer_behavior_signals(
                bbox=(x1, y1, x2, y2),
                frame_shape=frame.shape,
                emotion=emotion,
                emotion_confidence=emotion_confidence,
                gaze=gaze,
                action_units=action_units,
                head_pose=head_pose,
            )

            results.append(
                FaceAnalysisResult(
                    face_id=len(results),
                    bbox=(x1, y1, x2, y2),
                    face_score=face_score,
                    emotion=emotion,
                    emotion_confidence=emotion_confidence,
                    emotion_scores=emotion_scores,
                    gaze=gaze,
                    action_units=action_units,
                    landmarks=landmarks,
                    head_pose=head_pose,
                    signals=signals,
                    timestamp=timestamp,
                )
            )
        return results

    def _detect_faces(self, frame: np.ndarray, resize: float = 1.0) -> np.ndarray:
        prior_box = self.openface_modules["PriorBox"]
        decode = self.openface_modules["decode"]
        decode_landm = self.openface_modules["decode_landm"]
        py_cpu_nms = self.openface_modules["py_cpu_nms"]

        image = np.float32(frame)
        if resize != 1.0:
            image = cv2.resize(image, None, fx=resize, fy=resize, interpolation=cv2.INTER_LINEAR)

        network_input = image.copy()
        network_input -= (104, 117, 123)
        network_input = network_input.transpose(2, 0, 1)
        network_input = torch.from_numpy(network_input).unsqueeze(0).to(self.detector.device)

        with torch.no_grad():
            loc, conf, landms = self.detector.model(network_input)

        height, width, _ = frame.shape
        scale = torch.tensor(
            [
                network_input.shape[3],
                network_input.shape[2],
                network_input.shape[3],
                network_input.shape[2],
            ],
            device=self.detector.device,
        )
        priorbox = prior_box(self.detector.cfg, image_size=(height, width))
        priors = priorbox.forward().to(self.detector.device)

        boxes = decode(loc.data.squeeze(0), priors.data, self.detector.cfg["variance"])
        boxes = (boxes * scale / resize).cpu().numpy()
        scores = conf.squeeze(0).data.cpu().numpy()[:, 1]

        landms = decode_landm(landms.data.squeeze(0), priors.data, self.detector.cfg["variance"])
        scale_landmarks = torch.tensor(
            [network_input.shape[3], network_input.shape[2]] * 5,
            device=self.detector.device,
        )
        landms = (landms * scale_landmarks / resize).cpu().numpy()

        indexes = np.where(scores > self.detector.confidence_threshold)[0]
        boxes, landms, scores = boxes[indexes], landms[indexes], scores[indexes]

        dets = np.hstack((boxes, scores[:, np.newaxis])).astype(np.float32, copy=False)
        keep = py_cpu_nms(dets, self.detector.nms_threshold)
        dets = dets[keep]
        landms = landms[keep]
        if len(dets) == 0:
            return dets
        return np.concatenate((dets, landms), axis=1)

    def _detect_landmarks(self, frame: np.ndarray, dets: np.ndarray) -> list[np.ndarray]:
        if self.landmark_detector is None or len(dets) == 0:
            return []
        try:
            with redirect_stdout(StringIO()):
                return self.landmark_detector.detect_landmarks(
                    frame,
                    dets,
                    confidence_threshold=self.min_score,
                )
        except Exception as exc:
            print(f"Landmark detection failed: {exc}")
            return []

    def _crop_face(self, frame: np.ndarray, det: np.ndarray) -> np.ndarray | None:
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = det[:4].astype(int)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(width - 1, x2), min(height - 1, y2)
        if x2 <= x1 or y2 <= y1:
            return None
        return frame[y1:y2, x1:x2]

    def _predict_multitask(
        self,
        face: np.ndarray,
    ) -> tuple[dict[str, float], dict[str, float | bool], dict[str, float]]:
        try:
            emotion_logits, gaze_output, au_output = self.emotion_model.predict(face)
        except RuntimeError as exc:
            if self.device == "mps":
                raise RuntimeError("MPS inference failed. Retry with device='cpu'.") from exc
            raise

        emotion_probs = torch.softmax(emotion_logits, dim=1).detach().cpu().numpy()[0]
        emotion_scores = {
            label: float(emotion_probs[index])
            for index, label in enumerate(EMOTIONS)
        }

        gaze_values = gaze_output.detach().cpu().numpy()[0].astype(float)
        gaze = {
            "yaw": float(gaze_values[0]),
            "pitch": float(gaze_values[1]),
            "looking_at_camera": abs(float(gaze_values[0])) < 0.15 and abs(float(gaze_values[1])) < 0.15,
            "looking_down": float(gaze_values[1]) > 0.18,
            "looking_away": abs(float(gaze_values[0])) > 0.25,
        }

        au_values = au_output.detach().cpu().numpy()[0].astype(float)
        action_units = {
            label: float(max(0.0, au_values[index]))
            for index, label in enumerate(AU_LABELS)
        }
        return emotion_scores, gaze, action_units

    def _serialize_landmarks(self, landmarks: np.ndarray) -> list[tuple[float, float]]:
        points = np.asarray(landmarks, dtype=float)
        return [(float(x), float(y)) for x, y in points[:, :2]]


def estimate_head_pose(
    frame_shape: tuple[int, int, int],
    landmarks: list[tuple[float, float]] | None,
) -> dict[str, float] | None:
    if landmarks is None or len(landmarks) < 68:
        return None

    points = np.asarray(landmarks, dtype=np.float64)
    if len(points) >= 98:
        image_points = np.array(
            [points[54], points[16], points[60], points[72], points[76], points[82]],
            dtype=np.float64,
        )
    else:
        image_points = np.array(
            [points[30], points[8], points[36], points[45], points[48], points[54]],
            dtype=np.float64,
        )

    model_points = np.array(
        [
            (0.0, 0.0, 0.0),
            (0.0, -330.0, -65.0),
            (-225.0, 170.0, -135.0),
            (225.0, 170.0, -135.0),
            (-150.0, -150.0, -125.0),
            (150.0, -150.0, -125.0),
        ],
        dtype=np.float64,
    )

    height, width = frame_shape[:2]
    focal_length = float(width)
    camera_matrix = np.array(
        [
            [focal_length, 0, width / 2],
            [0, focal_length, height / 2],
            [0, 0, 1],
        ],
        dtype=np.float64,
    )
    dist_coeffs = np.zeros((4, 1))
    ok, rotation_vector, translation_vector = cv2.solvePnP(
        model_points,
        image_points,
        camera_matrix,
        dist_coeffs,
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not ok:
        return None

    rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
    sy = np.sqrt(rotation_matrix[0, 0] * rotation_matrix[0, 0] + rotation_matrix[1, 0] * rotation_matrix[1, 0])
    singular = sy < 1e-6
    if not singular:
        pitch = np.degrees(np.arctan2(rotation_matrix[2, 1], rotation_matrix[2, 2]))
        yaw = np.degrees(np.arctan2(-rotation_matrix[2, 0], sy))
        roll = np.degrees(np.arctan2(rotation_matrix[1, 0], rotation_matrix[0, 0]))
    else:
        pitch = np.degrees(np.arctan2(-rotation_matrix[1, 2], rotation_matrix[1, 1]))
        yaw = np.degrees(np.arctan2(-rotation_matrix[2, 0], sy))
        roll = 0.0
    if pitch < -90.0:
        pitch += 180.0
    elif pitch > 90.0:
        pitch -= 180.0
    return {"yaw": float(yaw), "pitch": float(pitch), "roll": float(roll)}


def infer_behavior_signals(
    bbox: tuple[int, int, int, int],
    frame_shape: tuple[int, int, int],
    emotion: str,
    emotion_confidence: float,
    gaze: dict[str, float | bool],
    action_units: dict[str, float],
    head_pose: dict[str, float] | None,
) -> dict[str, bool | float]:
    x1, y1, x2, y2 = bbox
    frame_h, frame_w = frame_shape[:2]
    face_area_ratio = ((x2 - x1) * (y2 - y1)) / max(frame_w * frame_h, 1)

    yaw = float(gaze["yaw"])
    pitch = float(gaze["pitch"])
    head_yaw = abs(float(head_pose["yaw"])) if head_pose else 0.0
    head_pitch = float(head_pose["pitch"]) if head_pose else 0.0
    au4 = action_units.get("AU4", 0.0)
    au6 = action_units.get("AU6", 0.0)
    au12 = action_units.get("AU12", 0.0)
    au25 = action_units.get("AU25", 0.0)
    au26 = action_units.get("AU26", 0.0)

    smiling = emotion == "happy" and emotion_confidence > 0.35 or au12 > 0.35
    frowning = au4 > 0.35
    looking_down = bool(gaze["looking_down"]) or head_pitch > 18.0
    looking_at_camera = bool(gaze["looking_at_camera"]) and head_yaw < 18.0
    avoiding = bool(gaze["looking_away"]) or head_yaw > 25.0
    approaching = face_area_ratio > 0.16
    emotionally_aroused = (
        emotion in {"anger", "fear", "surprise", "disgust"}
        and emotion_confidence > 0.30
    ) or (au25 + au26 + au4 > 1.0)
    engagement_dropping = avoiding or looking_down or emotion in {"sad", "neutral"} and emotion_confidence > 0.55

    return {
        "looking_at_camera": looking_at_camera,
        "avoiding": avoiding,
        "looking_down": looking_down,
        "approaching": approaching,
        "frowning": frowning,
        "smiling": smiling,
        "emotionally_aroused": emotionally_aroused,
        "engagement_dropping": engagement_dropping,
        "face_area_ratio": float(face_area_ratio),
        "engagement_score": float(
            max(
                0.0,
                min(
                    1.0,
                    0.55
                    + (0.2 if looking_at_camera else -0.2)
                    + (0.15 if smiling else 0.0)
                    - (0.2 if avoiding else 0.0)
                    - (0.15 if looking_down else 0.0),
                ),
            )
        ),
    }


def draw_emotion_results(
    frame: np.ndarray,
    results: list[FaceAnalysisResult],
    ttl: float = 2.0,
    now: float | None = None,
) -> None:
    current_time = time.perf_counter() if now is None else now
    for result in results:
        if current_time - result.timestamp > ttl:
            continue
        x1, y1, x2, y2 = result.bbox
        signals = [name for name, active in result.signals.items() if isinstance(active, bool) and active]
        label = f"#{result.face_id} {result.emotion} {result.emotion_confidence:.2f}"
        detail = (
            f"gaze({float(result.gaze['yaw']):+.2f},{float(result.gaze['pitch']):+.2f}) "
            + " ".join(signals[:3])
        )
        cv2.rectangle(frame, (x1, y1), (x2, y2), (26, 188, 156), 2)
        cv2.putText(
            frame,
            label,
            (x1, max(22, y1 - 30)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (26, 188, 156),
            2,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            detail,
            (x1, max(44, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

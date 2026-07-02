# Face Emotion Agent Usage / 面部情绪与互动状态模块使用说明

## Purpose / 目标

This module provides realtime multi-face visual perception for the Tanyue love agent. It wraps OpenFace 3.0 and exposes structured results for agent decision making.

本模块为 Tanyue 恋爱 Agent 提供实时多人脸视觉感知能力。它封装 OpenFace 3.0，并以结构化数据形式暴露给 Agent 决策逻辑。

The module supports:

模块支持：

- Multi-face detection / 多人脸检测
- Emotion recognition / 情绪识别
- Gaze estimation / 眼动与视线估计
- Action Unit output / AU 面部动作单元输出
- Facial landmarks / 人脸关键点
- Head pose estimation / 头部姿态估计
- Interaction signals / 高级互动信号

## Files / 文件结构

- `tanyue_visual/camera.py`
  - Camera discovery, open/read, warm-up, black-frame checks.
  - 摄像头扫描、打开、读取、预热、黑帧检测。
- `tanyue_visual/emotion.py`
  - OpenFace 3.0 loading, single-frame face analysis, gaze/AU/signals.
  - OpenFace 3.0 加载、单帧人脸分析、gaze/AU/高级信号。
- `tanyue_visual/realtime.py`
  - Background inference worker for realtime agents.
  - 面向实时 Agent 的后台推理线程。
- `scripts/realtime_openface.py`
  - Demo CLI with smooth camera rendering.
  - 实时摄像头 Demo，显示画面与推理解耦。

## Quick Demo / 快速运行

From `visual/`:

在 `visual/` 目录下：

```sh
conda activate Tanyue
python scripts/realtime_openface.py --camera 1 --device cpu
```

Scan cameras:

扫描摄像头：

```sh
python scripts/realtime_openface.py --list-cameras
```

Use the camera where `opened=True`, `read=True`, and `black=False`.

选择 `opened=True`、`read=True`、`black=False` 的摄像头。

## Direct Agent API / 直接 Agent API

Use `OpenFaceEmotionRecognizer` for frame-level calls. It returns one `FaceAnalysisResult` per detected face.

使用 `OpenFaceEmotionRecognizer` 进行单帧调用。每张检测到的人脸会返回一个 `FaceAnalysisResult`。

```python
import cv2
from tanyue_visual import OpenFaceEmotionRecognizer

recognizer = OpenFaceEmotionRecognizer(device="cpu", min_score=0.65)

frame = cv2.imread("some_frame.jpg")
results = recognizer.predict(frame)

payload = [result.as_dict() for result in results]
```

Disable landmarks and head pose for lower latency:

如需更低延迟，可关闭关键点和头姿：

```python
recognizer = OpenFaceEmotionRecognizer(
    device="cpu",
    min_score=0.65,
    include_landmarks=False,
    include_head_pose=False,
)
```

## Result Schema / 返回结构

Each `result.as_dict()` returns:

每个 `result.as_dict()` 返回：

```python
{
    "face_id": 0,
    "bbox": [x1, y1, x2, y2],
    "face_score": 0.99,
    "emotion": {
        "label": "happy",
        "confidence": 0.82,
        "scores": {
            "neutral": 0.01,
            "happy": 0.82,
            "sad": 0.01,
            "surprise": 0.02,
            "fear": 0.01,
            "disgust": 0.01,
            "anger": 0.01,
            "contempt": 0.11,
        },
    },
    "gaze": {
        "yaw": -0.03,
        "pitch": 0.04,
        "looking_at_camera": True,
        "looking_down": False,
        "looking_away": False,
    },
    "action_units": {
        "AU1": 0.0,
        "AU2": 0.0,
        "AU4": 0.0,
        "AU6": 0.2,
        "AU9": 0.0,
        "AU12": 0.7,
        "AU25": 0.1,
        "AU26": 0.0,
    },
    "landmarks": [[x, y], ...],
    "head_pose": {
        "yaw": 0.0,
        "pitch": 5.0,
        "roll": -1.0,
    },
    "signals": {
        "looking_at_camera": True,
        "avoiding": False,
        "looking_down": False,
        "approaching": False,
        "frowning": False,
        "smiling": True,
        "emotionally_aroused": False,
        "engagement_dropping": False,
        "face_area_ratio": 0.08,
        "engagement_score": 0.9,
    },
    "timestamp": 123456.78,
}
```

Field meanings:

字段含义：

- `face_id`: face index in current frame / 当前帧中的人脸编号。
- `bbox`: face bounding box / 人脸框坐标。
- `face_score`: face detector confidence / 人脸检测置信度。
- `emotion`: emotion label, confidence, and all class scores / 情绪标签、置信度和各类别分数。
- `gaze`: eye gaze yaw/pitch and derived gaze flags / 眼动 yaw/pitch 与视线判断。
- `action_units`: AU intensity values / 面部动作单元强度。
- `landmarks`: 98 facial landmarks, or `None` if disabled / 98 点人脸关键点，关闭时为 `None`。
- `head_pose`: estimated yaw/pitch/roll, or `None` if disabled / 估计头部姿态，关闭时为 `None`。
- `signals`: behavior flags for agent logic / 面向 Agent 的高级行为信号。
- `timestamp`: monotonic timestamp from `time.perf_counter()` / 单调时钟时间戳。

## Behavior Signals / 高级行为信号

The following signals are derived from emotion, gaze, AU, face size, and head pose. They are heuristic but stable enough for agent state logic.

以下信号由情绪、gaze、AU、人脸大小和头姿推导而来。它们是工程启发式规则，适合 Agent 状态判断。

- `looking_at_camera`
  - User appears to look toward the camera.
  - 用户看向镜头。
- `avoiding`
  - Gaze or head pose suggests looking away.
  - gaze 或头姿显示用户在回避视线。
- `looking_down`
  - Gaze or head pose suggests looking downward.
  - gaze 或头姿显示用户低头。
- `approaching`
  - Face area is large in the frame.
  - 人脸面积占比较大，可能靠近摄像头。
- `frowning`
  - AU4 is active.
  - AU4 较强，可能皱眉。
- `smiling`
  - Happy emotion or AU12 is active.
  - happy 情绪或 AU12 较强，可能微笑。
- `emotionally_aroused`
  - Strong anger/fear/surprise/disgust or high AU activation.
  - 愤怒、恐惧、惊讶、厌恶等情绪或 AU 激活较强。
- `engagement_dropping`
  - Looking away, looking down, or sustained neutral/sad state.
  - 回避、低头，或持续中性/悲伤状态，可能参与度下降。
- `engagement_score`
  - A normalized interaction score from `0.0` to `1.0`.
  - 0 到 1 的参与度估计分数。

## Realtime Agent Pattern / 实时 Agent 调用模式

For live use, keep camera capture and model inference decoupled. Feed the latest frame into `RealtimeEmotionWorker`; the worker stores the latest analysis state.

实时场景中，建议让摄像头采集和模型推理解耦。将最新帧传给 `RealtimeEmotionWorker`，后台线程会保存最新分析状态。

```python
from tanyue_visual import (
    CameraConfig,
    CameraSource,
    OpenFaceEmotionRecognizer,
    RealtimeEmotionWorker,
)

camera_config = CameraConfig(index=1, frame_width=640, frame_height=480)
recognizer = OpenFaceEmotionRecognizer(device="cpu", min_score=0.65)

with CameraSource(camera_config) as camera, RealtimeEmotionWorker(
    recognizer,
    infer_interval=0.5,
) as worker:
    while True:
        ok, frame = camera.read()
        if not ok or frame is None:
            break

        worker.update_frame(frame)
        state = worker.get_state()

        agent_payload = [result.as_dict() for result in state.results]
        # Pass agent_payload to the love-agent state machine.
        # 将 agent_payload 传给恋爱 Agent 状态机。
```

Recommended defaults:

推荐默认值：

- `infer_interval=0.5`: about two analysis updates per second / 每秒约两次分析。
- `frame_width=640`, `frame_height=480`: lower CPU cost / 降低 CPU 开销。
- `device="cpu"` on macOS unless MPS is verified / macOS 上建议默认 CPU，确认 MPS 可用后再开启。
- `include_landmarks=False`, `include_head_pose=False` for lower latency / 低延迟时关闭关键点和头姿。

## CLI Options / 命令行选项

Smooth live display:

流畅显示：

```sh
python scripts/realtime_openface.py --camera 1 --device cpu --infer-interval 0.5
```

Lower CPU usage:

降低 CPU 占用：

```sh
python scripts/realtime_openface.py --camera 1 --device cpu --infer-interval 1.0
```

Keep labels visible longer:

让标签保留更久：

```sh
python scripts/realtime_openface.py --camera 1 --device cpu --prediction-ttl 3.0
```

Disable landmarks/head pose:

关闭关键点和头姿：

```sh
python scripts/realtime_openface.py --camera 1 --device cpu --no-landmarks --no-head-pose
```

## Notes / 注意事项

- OpenFace 3.0 weights are expected in `visual/weights/`.
  - OpenFace 3.0 权重默认位于 `visual/weights/`。
- Camera index `0` may be a black Continuity Camera stream on macOS.
  - macOS 上 camera 0 可能是黑屏的 Continuity Camera 流。
- Use `--list-cameras` and pick a non-black camera.
  - 使用 `--list-cameras`，选择非黑屏摄像头。
- Head pose is estimated from landmarks and should be treated as an interaction signal, not calibrated biometric measurement.
  - 头姿由关键点估算，适合作为互动状态信号，不应视为精密生物测量。

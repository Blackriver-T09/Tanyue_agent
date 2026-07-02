# Tanyue Love Agent Visual Module / Tanyue 恋爱 Agent 视觉模块

## Overview / 概览

This folder contains the realtime visual perception module for the Tanyue love agent. It uses OpenFace 3.0 to analyze one or more faces from a camera stream and exposes both low-level model outputs and higher-level interaction signals for agent logic.

本文件夹包含 Tanyue 恋爱 Agent 的实时视觉感知模块。模块基于 OpenFace 3.0，从摄像头画面中分析单人或多人脸，并向 Agent 暴露底层模型结果和高级互动状态。

Current outputs:

当前输出包括：

- Face boxes / 人脸框
- Multi-face results / 多人脸结果
- Emotion scores / 情绪分类与置信度
- Gaze yaw and pitch / 眼动 gaze 的 yaw、pitch
- Action Units / 面部动作单元 AU
- 98 facial landmarks / 98 点人脸关键点
- Head pose yaw, pitch, roll / 头部姿态 yaw、pitch、roll
- Agent signals / Agent 可直接使用的高级信号：
  - looking at camera / 是否看向镜头
  - avoiding / 是否回避
  - looking down / 是否低头
  - approaching / 是否靠近
  - frowning / 是否皱眉
  - smiling / 是否微笑
  - emotionally aroused / 是否情绪激动
  - engagement dropping / 是否参与度下降

## Environment / 环境

The Conda environment is named `Tanyue`.

Conda 环境名为 `Tanyue`。

```sh
conda activate Tanyue
```

Installed components:

已部署组件：

- Official OpenFace 3.0 source / 官方 OpenFace 3.0 源码：`vendor/OpenFace-3.0`
- Python package / Python 包：`openface-test==0.1.14`
- Model weights / 模型权重：`weights/`
- Importable package / 可导入模块：`tanyue_visual/`

`vendor/OpenFace-3.0` and `weights/` are local external dependencies and are ignored by this repository to avoid committing nested Git metadata and large model files. Re-clone OpenFace 3.0 and run `openface download` if rebuilding the environment on a new machine.

`vendor/OpenFace-3.0` 和 `weights/` 是本地外部依赖，已被本仓库忽略，以避免提交嵌套 Git 元数据和大型模型文件。在新机器重建环境时，请重新 clone OpenFace 3.0，并运行 `openface download`。

## Run Demo / 运行实时 Demo

From `visual/`:

在 `visual/` 目录下运行：

```sh
conda activate Tanyue
python scripts/realtime_openface.py --camera 1 --device cpu
```

Scan cameras first if needed:

如果不确定摄像头编号，先扫描：

```sh
python scripts/realtime_openface.py --list-cameras
```

Use the camera where `opened=True`, `read=True`, and `black=False`.

选择输出中 `opened=True`、`read=True`、`black=False` 的摄像头编号。

Press `q` or `Esc` in the camera window to quit.

在窗口中按 `q` 或 `Esc` 退出。

## Smooth Display / 流畅显示策略

The display loop is decoupled from OpenFace inference. The camera feed is rendered every frame, while OpenFace runs in a background worker at a lower frequency. The latest analysis result is overlaid onto the live image.

显示循环和 OpenFace 推理已经解耦。摄像头画面会按原始帧率显示，OpenFace 在后台低频运行，并把最近一次识别结果叠加到实时画面上。

Lower latency mode:

低延迟模式：

```sh
python scripts/realtime_openface.py --camera 1 --device cpu --no-landmarks --no-head-pose
```

Slower recognition interval:

降低识别频率：

```sh
python scripts/realtime_openface.py --camera 1 --device cpu --infer-interval 1.0
```

## Agent API / Agent 调用方式

See `docs/face_emotion_agent_usage.md` for full API details.

完整 API 说明见 `docs/face_emotion_agent_usage.md`。

Basic frame-level call:

单帧调用：

```python
from tanyue_visual import OpenFaceEmotionRecognizer

recognizer = OpenFaceEmotionRecognizer(device="cpu")
results = recognizer.predict(frame)
payload = [item.as_dict() for item in results]
```

Realtime background worker:

实时后台识别：

```python
from tanyue_visual import CameraConfig, CameraSource, OpenFaceEmotionRecognizer, RealtimeEmotionWorker

camera_config = CameraConfig(index=1, frame_width=640, frame_height=480)
recognizer = OpenFaceEmotionRecognizer(device="cpu")

with CameraSource(camera_config) as camera, RealtimeEmotionWorker(recognizer, infer_interval=0.5) as worker:
    ok, frame = camera.read()
    worker.update_frame(frame)
    state = worker.get_state()
```

## Model Files / 模型文件

Required files:

必需文件：

- `weights/Alignment_RetinaFace.pth`
- `weights/MTL_backbone.pth`
- `weights/Landmark_68.pkl`
- `weights/Landmark_98.pkl`
- `weights/mobilenetV1X0.25_pretrain.tar`

Download again if needed:

如需重新下载：

```sh
conda activate Tanyue
openface download
```

If `openface download` skips because `weights/` already exists, remove or rename the incomplete `weights/` directory and run it again.

如果 `openface download` 因 `weights/` 已存在而跳过，请删除或重命名不完整的 `weights/` 目录后重新运行。

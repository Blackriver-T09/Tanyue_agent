# Tanyue Motion Generator

## 中文

`character/motion_generator` 是一个独立的离线动作捕捉实验页。它不连接 LiveKit，也不连接 Agent。页面直接使用浏览器摄像头和 MediaPipe Holistic 捕捉人体姿态与双手关键点，并实时驱动当前 VRM 数字人。

当前目标是先跑通：

```text
Camera
  -> MediaPipe pose + hand landmarks
  -> Kalidokit realtime retarget
  -> VRM upper body / arms / wrists / approximate fingers
```

本工具已参考并本地克隆了 SysMocap：

```text
character/motion_generator/vendor/SysMocap
```

该目录只作为学习参考，不建议提交进主仓库。SysMocap 的关键思路是：不要直接把 landmark 向量硬套到 VRM 骨骼，而是先用 Kalidokit 把 MediaPipe Holistic 输出解算成 `riggedPose`、`riggedLeftHand`、`riggedRightHand`，再映射到 VRM Humanoid bones。

## 启动

从项目根目录启动静态服务器：

```bash
cd /Users/heihe/Desktop/Project/Tanyue
python3 -m http.server 8892 -d character
```

打开：

```text
http://127.0.0.1:8892/motion_generator/
```

如果要指定模型：

```text
http://127.0.0.1:8892/motion_generator/?model=LiuRuYan.vrm
```

点击 `Start Camera`，浏览器会请求摄像头权限。建议先确保整个人上半身在画面内，双手不要离身体太远。

## 当前能力

- 左侧显示 VRM 模型的实时骨骼投影。
- 右侧显示摄像头识别到的 MediaPipe 实时骨骼。
- `Show VRM skeleton` 可以显示或隐藏左侧 VRM 骨骼 overlay。
- 默认使用 `Kalidokit` 求解动作，比原来的手写向量 retarget 更稳定。
- `Solver` 可切换到 `Vector fallback`，用于对比旧算法或在 Kalidokit CDN 加载失败时继续测试。
- 实时捕捉上半身姿态。
- 驱动头部、胸部、上臂、前臂、手腕。
- 通过 Kalidokit 手部解算驱动手腕和手指骨骼。
- `Drive face` 可驱动眨眼、基础口型和视线方向。
- 可选 `Drive legs`，尝试驱动腿部骨骼。
- 可调 `Smoothing`、`Arm gain`、`Torso gain`。
- 可录制 landmarks 序列并下载 JSON。

## 录制格式

设置 `Seconds` 后点击 `Record`，页面会先显示 `3 / 2 / 1 / GO` 倒计时，然后按指定秒数自动录制。录制结束后会自动下载一个 `.fbx` 文件。

当前 FBX 是一个简化 Humanoid 骨架动画文件：

- 使用当前 VRM 标准骨骼名作为 FBX 节点名。
- 每帧保存本地 `position` 和 `quaternion`，导出时转换为 FBX translation / rotation 曲线。
- 用于后续在 Blender / Unity 中检查、清洗和 retarget。
- 它不是原始 VRM 模型本体，也不会包含衣服、材质或表情 blendshape。

`Download Capture JSON` 仍保留为调试输出，会把每帧保存为：

```json
{
  "t": 0.1333,
  "pose": [],
  "leftHand": [],
  "rightHand": [],
  "bones": {}
}
```

下载文件名类似：

```text
tanyue-motion-capture-178....json
```

这个 JSON 是后续调试、重烘焙到 VRMA 或自定义动作格式的输入数据，不是可直接放进 `character/motions/manifest.json` 的动作文件。
文件元数据会包含当前 `solver`，例如 `kalidokit` 或 `vector`，方便后续判断动作来自哪条 retarget 路径。

## 注意事项

- VRM 标准支持精确到手指的 Humanoid bones。当前 `LiuRuYan.vrm` 已绑定 30 根手指骨，包括左右手五指的近端、中间、远端骨骼。
- 识别准确不代表可以直接完美驱动 VRM。MediaPipe landmarks 是摄像头坐标系，VRM 是模型骨骼坐标系，中间需要 retarget、人体比例校准、左右镜像处理、骨骼 rest pose 校准和限制角度。
- 当前默认使用 Kalidokit 做实时求解，但还不是专业 Mocap。复杂转身、遮挡、手指互相遮住时仍会不稳定。
- MediaPipe 与 Kalidokit 在浏览器中运行，首次加载需要联网下载模型文件。
- 如果手臂方向反了，先尝试关闭或打开 `Mirror camera`。
- 如果动作抖动，调高 `Smoothing`。
- 如果手臂幅度太小或太夸张，调整 `Arm gain`。
- 全身动作对摄像头视角要求更高。只做上半身动作时建议关闭 `Drive legs`。

## 从 SysMocap 学到的实现要点

- 捕捉层：MediaPipe Holistic 输出 `poseLandmarks`、`poseWorldLandmarks`、`leftHandLandmarks`、`rightHandLandmarks`。
- 求解层：Kalidokit 将 landmarks 转成 VRM 更容易消费的欧拉角结构。
- 镜像层：参考 SysMocap，镜像只作用于显示层，不改传入 Kalidokit 的 landmark 数据。这样可以避免坐标被二次翻转，降低前后位移被误映射成左右位移的概率。
- 手部左右：参考 SysMocap，MediaPipe 双手 landmarks 在 Kalidokit 手部求解路径中固定互换后再求解。
- 渲染层：按 VRM Humanoid bone 名称应用旋转，例如 `Chest`、`Spine`、`LeftUpperArm`、`LeftLowerArm`、`LeftIndexProximal`。
- 手指控制：VRM 支持左右手五指的 proximal/intermediate/distal 骨骼，前提是模型本身确实绑定了这些骨骼。
- 面部控制：参考 SysMocap 的 `rigFace`，将 Kalidokit 的 `eye`、`mouth.shape` 和 `pupil` 写入 VRM expressions / lookAt。实际效果取决于 VRM 模型是否绑定了 `blinkLeft`、`blinkRight`、`aa`、`ee`、`ih`、`oh`、`ou` 等预设 expression。
- 我们现在保留左右两侧骨架可视化，用来检查“识别是准的，还是 retarget 映射错了”。

## 下一步

后续可以继续扩展：

- 将 capture JSON 烘焙成可复用的关键帧动作。
- 导出为 VRMA 或 FBX。
- 加入动作裁剪、平滑、循环段标记。
- 加入手势命名与动作描述生成，自动写入 `character/motions/manifest.json`。

## English

`character/motion_generator` is a standalone offline motion capture experiment page. It does not connect to LiveKit or the Agent. It uses the browser camera and MediaPipe Holistic to capture body and hand landmarks, then retargets them to the VRM avatar in realtime.

Run from the project root:

```bash
cd /Users/heihe/Desktop/Project/Tanyue
python3 -m http.server 8892 -d character
```

Open:

```text
http://127.0.0.1:8892/motion_generator/
```

Current support:

- Left pane: projected realtime VRM skeleton.
- Right pane: detected MediaPipe camera skeleton.
- Optional VRM skeleton overlay.
- Default Kalidokit retargeting, with a vector fallback mode.
- Upper-body pose tracking.
- Head, chest, arms, wrists, and VRM finger bones.
- Optional face tracking for blink, mouth shapes, and gaze.
- Optional leg driving.
- Timed recording with a 3/2/1 countdown.
- Automatic simplified animated Humanoid FBX export.
- JSON recording of pose, hand landmarks, and driven VRM bone transforms for debugging.

The exported FBX contains a simplified animated skeleton for inspection and retargeting. The downloaded JSON is a raw debug capture source for later baking.

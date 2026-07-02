# Tanyue Character / VRM Agent Interface

## 中文说明

`character` 是 Tanyue 数字人展示层。它用浏览器加载 VRM 模型，播放 FBX 动作，并把表情、姿态、动作、口型同步暴露给上层 Agent。

当前模型：

```text
character/models/test_01.vrm
```

## 架构

推荐使用 Web bridge 架构：

```text
Agent / Python
  -> POST http://127.0.0.1:8893/api/command
  -> character_bridge.py
  -> Server-Sent Events /events
  -> Browser page
  -> window.tanyueCharacter.applyCommand()
  -> VRM bones / expressions / motions / lip sync
```

这样做的好处是：

- Agent 可以用普通 HTTP 调用控制数字人。
- 浏览器仍负责 WebGL、VRM、音频分析和渲染。
- 不需要额外 WebSocket 依赖，Python 标准库即可运行。
- 后续可以把 bridge 换成远程服务，浏览器只需要改 `?bridge=` 地址。

## 启动

主项目页面已经内嵌角色窗口。常规使用时启动：

```bash
python tanyue_agent.py web
```

然后打开：

```text
http://127.0.0.1:8894
```

如果只想单独调试角色页面，可以在项目根目录启动独立静态页面：

```bash
python3 -m http.server 8892 -d character
```

另开一个终端启动 Agent bridge：

```bash
python3 character/scripts/character_bridge.py --host 127.0.0.1 --port 8893
```

浏览器打开：

```text
http://127.0.0.1:8892/
```

页面默认连接：

```text
http://127.0.0.1:8893/events
```

如果 bridge 不在默认地址，可以这样打开：

```text
http://127.0.0.1:8892/?bridge=http://127.0.0.1:8893
```

如果只想手动调试页面、不连接 Agent：

```text
http://127.0.0.1:8892/?bridge=off
```

## 快速测试 Agent 调用

确保角色页面和 bridge 都已经启动，然后运行：

```bash
python3 character/scripts/agent_character_demo.py
```

它会让角色进入开心状态、播放挥手动作、模拟一次口型电平，然后回到 listening 状态。

也可以直接用 curl：

```bash
curl -X POST http://127.0.0.1:8893/api/command \
  -H "Content-Type: application/json" \
  -d '{"type":"playMotion","motion":"waving"}'
```

## Python Agent 模块

上层 Agent 可以直接 import：

```python
from character.tanyue_character import CharacterAgent

avatar = CharacterAgent()
avatar.set_pose("listening")
avatar.set_expression("happy")
avatar.play_motion("waving", loop=False, speed=1.0)
avatar.set_lip_sync_level(0.65)
avatar.stop_motion()
```

如果当前工作目录不是项目根目录，可以把 `character` 加到 `PYTHONPATH`，或者参考 `character/scripts/agent_character_demo.py` 的写法把 `character` 路径加入 `sys.path`。

自定义 bridge 地址：

```python
from character.tanyue_character import CharacterAgent, CharacterAgentConfig

avatar = CharacterAgent(CharacterAgentConfig(base_url="http://127.0.0.1:8893"))
avatar.set_state(expression="relaxed", headYaw=8, energy=0.5)
```

## 命令格式

Bridge 接收 JSON：

```http
POST /api/command
Content-Type: application/json
```

常用命令：

```json
{"type":"setState","payload":{"expression":"happy","headYaw":10,"energy":0.8}}
```

```json
{"type":"setPose","pose":"listening"}
```

```json
{"type":"playMotion","motion":"waving"}
```

```json
{"type":"stopMotion"}
```

```json
{"type":"setMouth","aa":0.8,"oh":0.2}
```

```json
{"type":"setLipSyncLevel","level":0.62}
```

```json
{"type":"playAudioUrl","url":"/voice/output/tender.wav"}
```

批量命令：

```json
{
  "type": "batch",
  "commands": [
    {"type": "setState", "payload": {"expression": "happy", "motionLoop": false}},
    {"type": "playMotion", "motion": "waving"}
  ]
}
```

## 浏览器内 API

页面本身也暴露：

```js
window.tanyueCharacter.setState({
  expression: 'happy',
  headYaw: 12,
  headPitch: -6,
  mouthAa: 0.7,
  energy: 0.8,
});
```

统一命令入口：

```js
await window.tanyueCharacter.applyCommand({
  type: 'playMotion',
  motion: 'waving',
});
```

读取能力：

```js
window.tanyueCharacter.getCapabilities();
window.tanyueCharacter.getState();
```

## 当前可用动作

FBX 动作由 `character/motions/manifest.json` 注册。manifest 现在是版本化对象：

```json
{
  "version": 1,
  "defaultIdleMotion": "angry",
  "motions": [
    {
      "id": "waving",
      "label": "Waving",
      "file": "X Bot@Waving.fbx",
      "description": "挥手打招呼。适合问候、告别、欢迎用户、轻松回应。",
      "posture": "抬手挥动，表情可配合开心。",
      "situations": ["greeting", "farewell", "welcome"],
      "mood": ["friendly", "happy", "warm"],
      "tags": ["greeting", "wave"]
    }
  ]
}
```

`description`、`situations`、`mood`、`tags` 会被语音 Agent 放进 Qwen 提示词，用来让 AI 选择动作。以后新增动作时只要继续往 `motions` 数组追加对象即可。

当前可用 id：

```text
angry
catwalk_idle_to_twist_r
catwalk_walk_forward_highknees
dancing
excited
standing
golf_bad_shot
jog_in_circle
jogging
pointing_forward
pointing
rumba
salute
sitting
strut_walking
talking_on_phone
walking
waving
```

新增动作：

1. 把 Mixamo 风格 `.fbx` 放入 `character/motions/`。
2. 在 `character/motions/manifest.json` 的 `motions` 数组添加：

```json
{
  "id": "new_motion",
  "label": "New Motion",
  "file": "X Bot@New Motion.fbx",
  "description": "一句简短说明动作姿态、适用场景和人物心情。",
  "posture": "大致动作姿态。",
  "situations": ["example_scene"],
  "mood": ["example_mood"],
  "tags": ["custom"]
}
```

3. 刷新页面。
4. Agent 调用：

```python
avatar.play_motion("new_motion")
```

当前实现会在浏览器运行时把 Mixamo FBX retarget 到 VRM，不再使用之前转换出的 VRMA 文件。

## 口型同步

页面支持三种口型方式：

1. 浏览器麦克风测试：

```python
avatar.start_microphone_lip_sync()
```

2. 浏览器播放音频 URL，并自动分析音量：

```python
avatar.play_audio_url("/voice/output/tender.wav")
```

3. Agent 播放 TTS 流时同步发送音量电平：

```python
avatar.set_lip_sync_level(0.62)
```

如果音频是在 Python 或系统播放器里播放，浏览器无法直接分析那段声音。此时推荐在 TTS chunk 播放时计算 RMS 音量，然后持续调用 `set_lip_sync_level()`。

当前口型是音量级张合，主要驱动 VRM 的 `aa` 和 `oh`。如果需要更精确的音素级口型，后续应接入 TTS 的 phoneme / viseme 时间戳，映射到 VRM 的 `aa / ih / ou / ee / oh`。

## Agent 状态映射建议

可以把上层 Agent 状态映射为：

- `listening`：`setPose("listening")`，`setExpression("relaxed")`
- `thinking`：`setPose("thinking")`，降低 `energy`
- `speaking`：`setExpression("happy")` 或 `relaxed`，TTS chunk 持续调用 `set_lip_sync_level`
- `greeting`：`play_motion("waving")`
- `excited`：`play_motion("excited")` 或提高 `energy`
- `shy`：`setPose("shy")`，`setExpression("happy")`

## English

`character` is the browser-based VRM presentation layer for Tanyue. It loads the VRM model, retargets FBX motions at runtime, and exposes pose, expression, motion, and lip-sync controls to the upper Agent.

Current model:

```text
character/models/test_01.vrm
```

## Architecture

Recommended Web bridge architecture:

```text
Agent / Python
  -> POST http://127.0.0.1:8893/api/command
  -> character_bridge.py
  -> Server-Sent Events /events
  -> Browser page
  -> window.tanyueCharacter.applyCommand()
  -> VRM bones / expressions / motions / lip sync
```

The Agent uses plain HTTP, while the browser remains responsible for WebGL rendering, VRM animation, audio analysis, and lip sync. The bridge uses only the Python standard library.

## Run

Start the static character page from the project root:

```bash
python3 -m http.server 8892 -d character
```

Start the Agent bridge in another terminal:

```bash
python3 character/scripts/character_bridge.py --host 127.0.0.1 --port 8893
```

Open:

```text
http://127.0.0.1:8892/
```

The page connects to this bridge by default:

```text
http://127.0.0.1:8893/events
```

Use a custom bridge:

```text
http://127.0.0.1:8892/?bridge=http://127.0.0.1:8893
```

Disable bridge auto-connect:

```text
http://127.0.0.1:8892/?bridge=off
```

## Quick Agent Test

With the page and bridge running:

```bash
python3 character/scripts/agent_character_demo.py
```

Or send a command manually:

```bash
curl -X POST http://127.0.0.1:8893/api/command \
  -H "Content-Type: application/json" \
  -d '{"type":"playMotion","motion":"waving"}'
```

## Python Agent Module

```python
from character.tanyue_character import CharacterAgent

avatar = CharacterAgent()
avatar.set_pose("listening")
avatar.set_expression("happy")
avatar.play_motion("waving", loop=False, speed=1.0)
avatar.set_lip_sync_level(0.65)
avatar.stop_motion()
```

Custom bridge:

```python
from character.tanyue_character import CharacterAgent, CharacterAgentConfig

avatar = CharacterAgent(CharacterAgentConfig(base_url="http://127.0.0.1:8893"))
avatar.set_state(expression="relaxed", headYaw=8, energy=0.5)
```

## Command API

The bridge accepts:

```http
POST /api/command
Content-Type: application/json
```

Examples:

```json
{"type":"setState","payload":{"expression":"happy","headYaw":10,"energy":0.8}}
```

```json
{"type":"setPose","pose":"listening"}
```

```json
{"type":"playMotion","motion":"waving"}
```

```json
{"type":"setLipSyncLevel","level":0.62}
```

Batch:

```json
{
  "type": "batch",
  "commands": [
    {"type": "setState", "payload": {"expression": "happy", "motionLoop": false}},
    {"type": "playMotion", "motion": "waving"}
  ]
}
```

## Browser API

```js
window.tanyueCharacter.setState({
  expression: 'happy',
  headYaw: 12,
  headPitch: -6,
  mouthAa: 0.7,
  energy: 0.8,
});

await window.tanyueCharacter.applyCommand({
  type: 'playMotion',
  motion: 'waving',
});

window.tanyueCharacter.getCapabilities();
window.tanyueCharacter.getState();
```

## Motions

FBX motions are registered in `character/motions/manifest.json`. Add a Mixamo-style `.fbx` file to `character/motions/`, add a manifest entry, refresh the page, then call:

```python
avatar.play_motion("new_motion")
```

Registered Mixamo motions are retargeted to the current VRM in the browser at runtime.

## Lip Sync

Supported modes:

- Microphone test: `avatar.start_microphone_lip_sync()`
- Browser audio URL playback: `avatar.play_audio_url("/voice/output/tender.wav")`
- External TTS stream level: `avatar.set_lip_sync_level(0.62)`

If Python or a system player plays the TTS audio, the browser cannot analyze that audio directly. In that case, compute RMS per audio chunk in the Agent/TTS layer and send it to `set_lip_sync_level()`.

The current implementation is amplitude-based and drives `aa` and `oh`. For phoneme-level lip sync, connect TTS phoneme/viseme timings later and map them to VRM `aa / ih / ou / ee / oh`.

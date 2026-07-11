# Tanyue Digital Human Agent

## PunGen + Unitree Demo (Primary Competition Path)

The competition-critical path is now the physical Unitree voice runtime. The
web avatar is optional and is not required for the demo:

```text
Microphone -> Aliyun Fun-ASR -> PunGen fuzzy meme recognition
           -> G1 voice pack / AudioClient -> G1 action
```

Canonical PunGen source: `pungen_agent/`. Physical robot programs: `robot/`.
The outer Researchpipe `pungen_agent/__init__.py` is only a compatibility
forwarder; there is no second implementation.

Validated triggers:

- `你懂不懂机器人` -> Trump voice line + `accordion_gesture`.
- `播放 YMCA` -> configured YMCA WAV + `ymca_dance`.

Start from this directory:

```bash
export DASHSCOPE_API_KEY="..."
python3 -m pungen_agent.unitree_live <robot-interface> \
  --backend funasr \
  --trump-wav /path/to/trump-16k-mono.wav \
  --ymca-wav /path/to/ymca-16k-mono.wav
```

The safe default maps the two show actions to G1 high-level wave actions. To
use the real low-level accordion routine, first build and manually validate
`robot/g1_trump_accordion_example.cpp`; then add:

```bash
--accordion-bin robot/build/g1_trump_accordion \
--enable-low-level-accordion
```

See `robot/README.md` for the explicit safety gate. The C++ Unitree SDK2 is not
currently present in this checkout, so the low-level binary is not built yet.
Voice-pack and YMCA audio files are also user-supplied licensed assets.

## 中文

Tanyue 是一个面向实时陪伴交互的数字人 Agent 项目。当前代码已经完成四个基础模块，并优先跑通了“语音输入 -> 大模型回复 -> 语音输出”的实时闭环。

当前主链路：

```text
Browser microphone
  -> local LiveKit RTC
  -> local LiveKit Agents worker
  -> Aliyun realtime STT / Fun-ASR
  -> Aliyun Bailian Qwen 3.6 Flash
  -> Aliyun CosyVoice streaming TTS
  -> local LiveKit RTC
  -> Browser audio playback
```

LiveKit 只负责本地 RTC、房间、麦克风音频传输和 Agent 音频回传。STT、LLM、TTS 都走阿里云线上 API，以降低本地机器负担并减少模型部署复杂度。

## 当前模块

- `visual/`：OpenFace 3.0 面部情感识别、表情/头部姿态/视线/参与度等高级视觉特征。
- `hear/`：早期听觉输入实验和阿里云实时转录脚本。
- `voice/`：当前主用的实时语音 Agent，基于 LiveKit Agents + 阿里云 STT/Qwen/CosyVoice。
- `character/`：Web VRM 数字人展示、动作、口型和 Agent 控制接口。
- `LiveKit/`：本地自托管 LiveKit Server 配置。
- `web/`：浏览器语音测试页。
- `tanyue_agent.py`：项目根目录统一入口。

## 环境

推荐使用已有 conda 环境：

```bash
conda activate Tanyue
```

LiveKit 语音链路依赖：

```bash
conda run -n Tanyue python -m pip install -r voice/requirements-livekit.txt
```

本地 LiveKit Server 需要 Docker。macOS 如果没有 `docker` 命令，需要先安装并启动 Docker Desktop。

## 配置

真实密钥不要提交到 Git。当前 `.gitignore` 已忽略：

- `Config.py`
- `.env`
- `.env.*`
- `voice/reference_voice.*` / `voice/reference.wav`
- `voice/.cosyvoice_voice_id`
- Python 缓存
- 模型权重和输出文件

阿里云配置可以放在项目根目录 `Config.py`：

```python
API_KEY = "..."
DASHSCOPE_WORKSPACE_ID = "..."
API_HOST = "..."
DASHSCOPE_REGION = "beijing"
```

也可以复制环境变量模板：

```bash
cp voice/.env.livekit.example voice/.env
```

关键实时语音配置：

```bash
LIVEKIT_URL=ws://127.0.0.1:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=devsecret

TANYUE_STT_PROVIDER=aliyun
TANYUE_ALIYUN_STT_MODEL=fun-asr-realtime
TANYUE_ALIYUN_STT_NOISE_GATE_ENABLED=1
TANYUE_ALIYUN_STT_NOISE_GATE_DBFS=-45
TANYUE_ALIYUN_STT_NOISE_GATE_OPEN_MS=80
TANYUE_ALIYUN_STT_NOISE_GATE_HANGOVER_MS=900
TANYUE_ALIYUN_STT_NOISE_GATE_SEND_SILENCE=1

TANYUE_QWEN_MODEL=qwen3.6-flash
TANYUE_QWEN_ENABLE_THINKING=0
TANYUE_QWEN_MAX_COMPLETION_TOKENS=48
TANYUE_QWEN_TEMPERATURE=0.6

TANYUE_COSYVOICE_MODEL=cosyvoice-v3.5-plus
TANYUE_COSYVOICE_VOICE=longxiaochun
TANYUE_COSYVOICE_INSTRUCTION=
TANYUE_COSYVOICE_ENABLE_STYLE_PARAMS=0
TANYUE_COSYVOICE_CLONE_ENABLED=1
TANYUE_COSYVOICE_REFERENCE_AUDIO=voice/reference.wav
TANYUE_COSYVOICE_CLONE_CACHE=voice/.cosyvoice_voice_id
TANYUE_COSYVOICE_VOICE_REGISTRY=voice/cosyvoice_voices.json
TANYUE_COSYVOICE_RANDOM_VOICE_ENABLED=1
```

实时语音默认关闭 Qwen thinking。这个设置对延迟非常关键：实测默认 thinking 的首 token 可能接近 10 秒，关闭后通常进入亚秒级。

ASR 前默认开启本地音量门限。未打开门限时，低于 `TANYUE_ALIYUN_STT_NOISE_GATE_DBFS` 的麦克风音频会直接丢弃，不送到阿里云 STT；必须连续超过阈值 `TANYUE_ALIYUN_STT_NOISE_GATE_OPEN_MS` 毫秒才会打开 ASR。门限打开后，低于阈值的原始麦克风声仍不会被送出，但会发送短暂的纯数字静音来保持 ASR 时间连续并触发句末 final。环境噪声大时可以把阈值调高，例如 `-40`；误吞正常说话时调低，例如 `-50`。

CosyVoice 现在默认使用阿里云声音复刻。实时 Agent 会优先读取 `voice/cosyvoice_voices.json` 中所有已注册的 `voice_id`，每次 TTS 合成随机选择一个音色；如果注册表不存在或没有可用 `voice_id`，才退回单个 `voice/.cosyvoice_voice_id` 缓存。

注册表对应的本地参考音频放在：

```text
voice/reference_voice/
```

注意：阿里云 `voice-enrollment` 创建音色时需要阿里云服务端可访问的公网音频 URL，本地文件路径不能直接传给云端。拿到公网 URL 后注册：

```bash
python tanyue_agent.py clone-voice \
  --url doubao=https://your-public-host/doubao.wav
```

如果已经在阿里云控制台或其他脚本中注册好了 voice_id，可以直接写回注册表：

```bash
python tanyue_agent.py clone-voice \
  --set-voice-id doubao=cosyvoice-v3.5-plus-doubao-xxxxxxxx
```

查看当前注册表：

```bash
python tanyue_agent.py clone-voice --list-voices
```

如果参考音频是 44.1kHz stereo，建议先转成 24kHz mono 再注册，减少音高异常、低沉或抖动。

## 启动实时语音 Agent

### 1. 启动本地 LiveKit Server

```bash
cd /Users/heihe/Desktop/Project/Tanyue/LiveKit
docker compose up
```

看到类似日志表示 LiveKit 已启动：

```text
starting LiveKit server {"portHttp": 7880, ...}
```

### 2. 启动 Character Bridge

如果要让 AI 同时控制数字人动作，启动角色控制 bridge：

```bash
cd /Users/heihe/Desktop/Project/Tanyue
python3 character/scripts/character_bridge.py --host 127.0.0.1 --port 8893
```

角色页面现在由 `python tanyue_agent.py web` 统一托管，不需要再单独打开 `8892`。统一页面里的角色 iframe 会连接 `http://127.0.0.1:8893/events`，加载完成后自动循环播放 `angry` 作为待机动作。

### 3. 启动 Agent worker

新开终端：

```bash
cd /Users/heihe/Desktop/Project/Tanyue
conda activate Tanyue
python tanyue_agent.py start
```

正常日志会包含：

```text
registered worker
Tanyue job accepted ... qwen_thinking=False ... cosyvoice_model=cosyvoice-v3.5-plus voice=longxiaochun
Aliyun STT stream connected
```

Agent 会把 `character/motions/manifest.json` 中的动作说明加入提示词，并读取当前 VRM 模型中的预设表情。Qwen 每次回复会生成 `reply`、`motion` 和 `expression`，Agent 会在朗读 `reply` 的同时通过 `TANYUE_CHARACTER_BRIDGE_URL` 发送动作和表情给角色页面。表情强度默认使用 `1.0`，并保持到本轮语音播放结束；结束后回到 `relaxed`。随音量开合嘴巴现在默认关闭，后续需要时可以重新打开。

表情和口型相关参数：

```bash
TANYUE_CHARACTER_EXPRESSIONS=
TANYUE_CHARACTER_EXPRESSION_TAIL_SECONDS=0.9
TANYUE_CHARACTER_EXPRESSION_MAX_HOLD_SECONDS=12.0
TANYUE_CHARACTER_LIP_SYNC_ENABLED=0
TANYUE_CHARACTER_LIP_SYNC_INTERVAL=0.08
TANYUE_CHARACTER_LIP_SYNC_GAIN=7.0
TANYUE_CHARACTER_LIP_SYNC_NOISE_FLOOR=0.01
```

`TANYUE_CHARACTER_EXPRESSIONS` 留空时会优先从 `character/models/LiuRuYan.vrm` 读取 VRM preset expression；如果换模型后想手动限制表情列表，可以设置成逗号分隔值，例如 `happy,angry,sad,relaxed,surprised,neutral`。`TANYUE_CHARACTER_EXPRESSION_TAIL_SECONDS` 会在估算出的音频播放结束后额外保留表情，避免 TTS 生成流先结束导致表情提前恢复。

### 4. 启动语音 Web 页面

再开一个终端：

```bash
cd /Users/heihe/Desktop/Project/Tanyue
conda activate Tanyue
python tanyue_agent.py web
```

浏览器打开：

```text
http://127.0.0.1:8894
```

点击 `Connect`，允许麦克风权限，然后直接说话。页面会显示用户转录和 Agent 回复，浏览器会播放 Agent 语音。

统一页面左侧/中间是数字人舞台，右侧是可折叠 Debug 面板。点击面板顶部的 `›` 可以收起对话日志和连接控制，减少空间占用；需要看转录、dispatch、房间状态时再展开。

同一个房间断开后再次 Connect 时，Web 服务会替换旧 dispatch 并创建新的 Agent job，避免复用已经关闭的旧工作流。

### 玩梗模式

当前 Web 面板不再提供三幕剧情选择。实时链路固定为玩梗模式：

```text
用户语音 -> 阿里云 STT -> pungen_agent 本地梗识别
         -> 用户原文 + 梗识别结果 -> Qwen 在线 LLM
         -> 阿里云 CosyVoice -> LiveKit 播放
         -> 数字人动作 / 表情
```

`pungen_agent` 当前默认使用本地梗库匹配，不额外调用在线 API。Qwen 会收到压缩后的梗识别 JSON，但不会把 `meme_id`、`confidence` 等内部字段念出来。dispatch metadata 会包含：

```json
{"mode":"meme_play"}
```

命令行排查时可以运行：

```bash
python tanyue_agent.py status --room <当前页面里的Room>
```

## 常用命令

查看入口帮助：

```bash
python tanyue_agent.py --help
```

查看房间状态：

```bash
python tanyue_agent.py status --room tanyue-room
```

换一个干净房间测试：

```text
tanyue-test-1
```

如果房间里残留旧 dispatch 或旧 Agent，直接换新房间名最快；也可以重启 LiveKit Server。

## 延迟优化状态

当前实时链路已经做了这些优化：

- STT 使用阿里云实时 Fun-ASR，句末结果几乎立即返回。
- Qwen 使用 OpenAI-compatible streaming。
- 默认关闭 Qwen thinking，降低首 token 延迟。
- 限制 Qwen 回复长度，避免语音回复过长。
- CosyVoice 使用复刻 voice_id 和流式 `streaming_call()`，Qwen 产出的文本片段会立即送入 TTS。
- CosyVoice PCM 回调直接转 LiveKit `AudioFrame`，不落盘。
- 当前默认不向 TTS 传情感提示词；如果复刻音色稳定后再需要风格控制，可重新设置 `TANYUE_COSYVOICE_INSTRUCTION` 并打开 `TANYUE_COSYVOICE_ENABLE_STYLE_PARAMS=1`。
- 浏览器麦克风轨道启用回声消除、降噪和自动增益。Agent 仍允许用户打断，但默认要求至少 `0.65s` 且至少 `2` 个词才认为是真打断，避免把 Agent 自己的语音回声误识别成“嗯”等新输入。
- Agent 播放语音时会通过 LiveKit data channel 通知前端临时 mute 本地麦克风；前端也保留远端音频电平检测作为兜底，连续静音后再恢复输入，进一步避免扬声器回灌造成自我对话。

当前观察到的体感延迟：用户说完后约 1 秒左右开始播放 Agent 语音。剩余延迟主要来自云端首 token、TTS 首包和网络往返。

## 排障

- 页面连接失败：确认 `LiveKit/docker-compose.yml` 正在运行，`LIVEKIT_URL=ws://127.0.0.1:7880`。
- 页面能连接但没有 Agent：确认 `python tanyue_agent.py start` 仍在运行，并查看 `python tanyue_agent.py status --room <room>`。
- 能显示用户转录但没有回复：看 worker 日志中是否出现 `Aliyun CosyVoice TTS error` 或 Qwen API 错误。
- 从说完话到开始说话超过数秒：确认日志里 `qwen_thinking=False`。
- Agent 说话时被自己的声音打断：优先使用耳机或降低扬声器音量，并确认浏览器麦克风权限对应的是正确输入设备。可调高 `TANYUE_MIN_INTERRUPTION_WORDS` 或 `TANYUE_MIN_INTERRUPTION_DURATION`，也可临时设置 `TANYUE_ALLOW_INTERRUPTION=0` 完全关闭打断。
- 如果你看到页面提示 `Assistant speaking`，这是前端正在保护麦克风输入；等待 Agent 说完后会自动恢复为 `Listening`。
- `InsecureKeyLengthWarning`：本地 `devsecret` 太短，仅开发环境可接受；正式部署需要替换强密钥。
- `/.well-known/appspecific/com.chrome.devtools.json 404`：Chrome/Edge DevTools 探测请求，可忽略。

## Git 保存策略

当前仓库忽略密钥、缓存、模型权重和生成输出。提交代码前可以检查：

```bash
git status --short
git status --ignored --short
```

不要提交 `Config.py`、`.env`、模型权重、音频输出或缓存目录。

## English

Tanyue is a realtime digital-human agent project. The current working path is the voice loop: browser microphone, local LiveKit RTC, LiveKit Agents worker, Aliyun realtime STT, Qwen 3.6 Flash, Aliyun CosyVoice streaming TTS, and browser audio playback.

LiveKit is used only for RTC transport and rooms. STT, LLM, and TTS are cloud APIs to keep local runtime light.

Quick start:

```bash
cd /Users/heihe/Desktop/Project/Tanyue/LiveKit
docker compose up
```

```bash
cd /Users/heihe/Desktop/Project/Tanyue
conda activate Tanyue
python tanyue_agent.py start
```

```bash
cd /Users/heihe/Desktop/Project/Tanyue
conda activate Tanyue
python tanyue_agent.py web --port 8894
```

Open `http://127.0.0.1:8894`, click `Connect`, allow microphone access, and speak.

Important latency setting:

```bash
TANYUE_QWEN_ENABLE_THINKING=0
```

Realtime voice should keep Qwen thinking disabled. Otherwise first-token latency can jump from sub-second to several seconds.

CosyVoice uses a cloned voice by default. Create or refresh the cloned voice with a public reference-audio URL:

```bash
TANYUE_COSYVOICE_CLONE_AUDIO_URL=https://your-valid-public-url/reference.wav \
python tanyue_agent.py clone-voice --force
```

The generated voice_id is cached in `voice/.cosyvoice_voice_id`. TTS style instructions are disabled by default while validating cloned-voice quality.

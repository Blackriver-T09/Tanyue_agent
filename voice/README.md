# Tanyue Voice

## 中文

`voice` 目录现在默认采用 LiveKit Agents 作为实时语音 Agent 框架。架构分两层：

- RTC / 房间 / 实时音频传输：本地自托管 LiveKit Server
- STT：阿里云实时语音识别 Fun-ASR
- LLM：阿里云百炼 / DashScope OpenAI-compatible Qwen
- TTS：阿里云 CosyVoice WebSocket / Python SDK
- Realtime Agent 编排：本地 LiveKit Agents worker

旧的手搓链路仍保留在 `realtime_voice_chat.py`、`tanyue_voice_chat/`、`tanyue_voice_remote/` 中，但后续建议只把它们当作 legacy 调试工具。

RTC 是 Real-Time Communication，指实时音视频通信层。它只解决“浏览器麦克风音频如何实时送到 Agent、Agent 的声音如何实时送回浏览器”的问题，不负责 STT/LLM/TTS 模型本身。

## 1. 环境

依赖已写入：

```bash
voice/requirements-livekit.txt
```

如需重装：

```bash
conda run -n Tanyue python -m pip install -r voice/requirements-livekit.txt
```

注意：这次安装会使用较新的 `protobuf`，如果你之后还要运行旧的本地 TensorFlow / IndexTTS / CosyVoice2 工作流，建议给 LiveKit 单独建一个环境，避免依赖冲突。

## 2. 配置

先启动本地 LiveKit Server：

```bash
cd LiveKit
docker compose up
```

复制模板并填写：

```bash
cp voice/.env.livekit.example voice/.env
```

关键配置：

- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `DASHSCOPE_API_KEY`，也可以继续放在项目根目录 `Config.py` 的 `API_KEY`
- `DASHSCOPE_WORKSPACE_ID`，也可以继续放在 `Config.py`，当前代码兼容 `DASHSCOPE_WORKSPACE_ID`、`WORKSPACE_ID` 和已有拼写 `WORKSAPCE_ID`
- `API_HOST`，可选；如果提供，会优先使用 `wss://{API_HOST}/api-ws/v1/inference`
- `TANYUE_QWEN_MODEL=qwen3.6-flash`
- `TANYUE_QWEN_ENABLE_THINKING=0`，实时语音默认关闭 Qwen thinking，以降低首 token 延迟
- `TANYUE_QWEN_MAX_COMPLETION_TOKENS=48`，限制回复长度，避免语音回复拖太长
- `TANYUE_STT_PROVIDER=aliyun`
- `TANYUE_ALIYUN_STT_MODEL=fun-asr-realtime`
- `TANYUE_COSYVOICE_MODEL=cosyvoice-v3.5-plus`
- `TANYUE_COSYVOICE_VOICE=longxiaochun`
- `TANYUE_COSYVOICE_INSTRUCTION=`，默认不传情感提示词
- `TANYUE_COSYVOICE_ENABLE_STYLE_PARAMS=0`
- `TANYUE_COSYVOICE_CLONE_ENABLED=1`
- `TANYUE_COSYVOICE_REFERENCE_AUDIO=voice/reference.wav`
- `TANYUE_COSYVOICE_CLONE_CACHE=voice/.cosyvoice_voice_id`
- `TANYUE_COSYVOICE_VOICE_REGISTRY=voice/cosyvoice_voices.json`
- `TANYUE_COSYVOICE_RANDOM_VOICE_ENABLED=1`
- `TANYUE_ALIYUN_STT_NOISE_GATE_ENABLED=1`
- `TANYUE_ALIYUN_STT_NOISE_GATE_DBFS=-45`
- `TANYUE_ALIYUN_STT_NOISE_GATE_OPEN_MS=80`
- `TANYUE_CHARACTER_ENABLED=1`
- `TANYUE_CHARACTER_BRIDGE_URL=http://127.0.0.1:8893`
- `TANYUE_CHARACTER_EXPRESSIONS=`，留空时从当前 VRM 模型读取 preset expression
- `TANYUE_CHARACTER_EXPRESSION_TAIL_SECONDS=0.9`，估算音频播放结束后额外保留表情
- `TANYUE_CHARACTER_EXPRESSION_MAX_HOLD_SECONDS=12.0`
- `TANYUE_CHARACTER_LIP_SYNC_ENABLED=0`，当前默认不使用音量口型
- `TANYUE_CHARACTER_LIP_SYNC_INTERVAL=0.08`
- `TANYUE_CHARACTER_LIP_SYNC_GAIN=7.0`
- `TANYUE_CHARACTER_LIP_SYNC_NOISE_FLOOR=0.01`

`voice/.env` 和项目根目录 `.env` 都会被自动读取；真实密钥已被 `.gitignore` 忽略。

本地 LiveKit 默认开发配置是：

```bash
LIVEKIT_URL=ws://127.0.0.1:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=devsecretdevsecretdevsecretdevsecret
```

这些来自 [LiveKit/livekit.local.yaml](/Users/heihe/Desktop/Project/Tanyue/LiveKit/livekit.local.yaml)。正式部署时必须替换成强密钥。

## 3. 启动

根目录现在提供统一入口：

```bash
python tanyue_agent.py --help
```

查看 LiveKit Agents 命令：

```bash
python tanyue_agent.py console --help
```

本地控制台测试：

```bash
python tanyue_agent.py console
```

连接到 LiveKit 房间：

```bash
python tanyue_agent.py start
```

开发模式：

```bash
python tanyue_agent.py dev
```

Web 展示页：

```bash
python tanyue_agent.py web
```

然后打开：

```text
http://127.0.0.1:8894
```

推荐完整运行方式：

```bash
# Terminal 1: Agent worker
python tanyue_agent.py start

# Terminal 2: Character bridge
python3 character/scripts/character_bridge.py --host 127.0.0.1 --port 8893

# Terminal 3: Unified Web UI, character iframe, and token service
python tanyue_agent.py web
```

Agent 名称默认是 `tanyue`，可通过 `TANYUE_LIVEKIT_AGENT_NAME` 修改。

统一 Web 页面内嵌数字人角色，右侧 Debug 面板可以折叠，展开后可以看到房间、转录、dispatch 和日志。侧边栏新增 `本机播放音频` 和 `机器人播放音频` 两个复选框：前者直接控制浏览器里的助理语音是否发声，后者当前只是机器人通道的占位开关，尚未真正接入机器人。如果 `character_bridge.py` 已启动，语音 Agent 会读取 `character/motions/manifest.json` 和当前 VRM 模型的 preset expression，要求 Qwen 在每次回复中选择 `motion` 和 `expression`。Agent 会解析动作和表情指令，朗读 `reply` 的同时把动作、表情发给角色 bridge；如果本轮 TTS 选中的 voice key 对应一个同名 VRM 文件，角色会在语音播放期间临时切换到该模型，例如 `dingzhen.wav` -> `dingzhen.vrm`，播放结束后恢复默认模型。表情强度默认使用 `1.0`，并根据已输出音频帧时长估算播放结束时间，额外保留 `TANYUE_CHARACTER_EXPRESSION_TAIL_SECONDS` 后回到 `relaxed`。当前默认不发送音量口型；如果以后重新启用 `TANYUE_CHARACTER_LIP_SYNC_ENABLED=1`，TTS 流式音频会被计算 RMS 音量包络并发送 `setLipSyncLevel`。

### 三幕剧情 Scene

Web 面板的 `Scene` 选择会写入 Agent dispatch metadata：

```json
{"scene":"humiliation"}
```

可选值：

- `humiliation`：第一幕羞辱期，固定开场白和轻蔑身份贬低。
- `reversal`：第二幕反转期，固定第一反应和破碎惊恐。
- `pleading`：第三幕求饶期，固定第一句、夸张求饶和第一幕台词回收。

切换 `Scene` 时，前端会断开当前房间、清空日志、生成新的 room 名称并重新 dispatch Agent，从而重置 LiveKit Agent 的对话上下文。

## 4. 声音复刻

当前 TTS 默认使用阿里云 CosyVoice 声音复刻。流程是：

1. 使用参考音频创建阿里云 voice_id。
2. 将多个 voice_id 写入 `voice/cosyvoice_voices.json`。
3. 实时对话时每次 TTS 调用从已注册 voice_id 中随机选择一个。

参考音频：

```text
voice/reference_voice/
```

注意：阿里云 `voice-enrollment` 创建音色时需要公网可访问的音频 URL，本地文件路径不能直接传给云端。首次创建或强制刷新时使用：

```bash
python tanyue_agent.py clone-voice \
  --url dingzhen=https://your-public-host/dingzhen.wav \
  --url kobe=https://your-public-host/kobe.wav \
  --url doubao=https://your-public-host/doubao.wav \
  --url trump=https://your-public-host/trump.wav
```

如果已经在阿里云控制台或其他脚本中注册好了 voice_id，可以只写回本地注册表：

```bash
python tanyue_agent.py clone-voice \
  --set-voice-id doubao=cosyvoice-v3.5-plus-doubao-xxxxxxxx
```

如果参考音频是 44.1kHz stereo，建议先转成 24kHz mono 再注册，减少音高异常、低沉或抖动：

```bash
ffmpeg -y -i voice/reference.wav -ac 1 -ar 24000 -sample_fmt s16 \
  -af "highpass=f=70,lowpass=f=11000,loudnorm=I=-18:TP=-2:LRA=11" \
  voice/tmp/reference_24k_mono.wav
```

查看当前音色注册表：

```bash
python tanyue_agent.py clone-voice --list-voices
```

注册完成后可以直接运行：

```bash
python tanyue_agent.py start
```

如果 `voice/cosyvoice_voices.json` 里有可用 voice_id，worker 启动时会直接复用注册表，不会重新上传或重新复刻；只有注册表不可用时才退回 `voice/.cosyvoice_voice_id` 单音色缓存。

当前默认不向 TTS 传情感提示词。声音复刻质量稳定后，如需重新启用风格控制，可设置：

```bash
TANYUE_COSYVOICE_INSTRUCTION=成熟，鄙夷，魅惑
TANYUE_COSYVOICE_ENABLE_STYLE_PARAMS=1
```

## 5. 排障

如果页面能显示用户转录，但没有 Agent 文本或语音回复，优先看 `python tanyue_agent.py start` 的后台日志：

- 看到 `Aliyun STT final transcript`：说明麦克风、LiveKit、阿里云 STT 都已经正常。
- 环境人声或底噪误触发 ASR：调高 `TANYUE_ALIYUN_STT_NOISE_GATE_DBFS`，例如从 `-45` 改成 `-40`；也可以提高 `TANYUE_ALIYUN_STT_NOISE_GATE_OPEN_MS`，让短促波动更难打开 ASR。如果正常说话被吞掉，调低到 `-50`。门限只影响送往阿里云的 ASR 音频，不影响浏览器麦克风电平显示。门限打开后的句末会发送纯数字静音给 ASR，不会录入低音量环境声。
- 看到 `Tanyue job accepted`：确认当前实际使用的 `qwen_model`、`qwen_thinking`、`qwen_max_tokens`、`cosyvoice_model` 和 `voice`。
- 看到 `Using cached Aliyun cloned voice_id`：说明声音复刻缓存已生效。
- 创建复刻音色时报 `url error`：说明 `TANYUE_COSYVOICE_CLONE_AUDIO_URL` 不是阿里云服务端可访问的有效公网 URL，建议使用 OSS 或有效证书的 HTTPS 静态文件地址。
- 如果 `Aliyun STT final transcript` 到 `Aliyun CosyVoice first text chunk sent` 间隔很长，通常是 LLM 首 token 慢。实时语音默认设置 `TANYUE_QWEN_ENABLE_THINKING=0`；如果打开 thinking，首 token 可能从亚秒级变成数秒级。
- 如果 Agent 说话时被自己的声音打断，通常是扬声器回灌到麦克风。浏览器端已经启用回声消除、降噪和自动增益；Agent 开始/结束 TTS 时还会通过 LiveKit data channel 通知前端临时 mute/恢复本地麦克风，远端音频电平检测作为兜底。Agent 端默认要求至少 `TANYUE_MIN_INTERRUPTION_DURATION=0.65` 秒且至少 `TANYUE_MIN_INTERRUPTION_WORDS=2` 个词才触发打断。仍然误触发时，优先使用耳机或降低扬声器音量，也可以调高这两个阈值，或设置 `TANYUE_ALLOW_INTERRUPTION=0` 完全关闭打断。
- 看到 `Aliyun CosyVoice TTS error ... 428`：通常是 CosyVoice 模型或音色参数不匹配。默认已改为 `cosyvoice-v3.5-plus / longxiaochun`，并会自动忽略旧的 `cosyvoice-v3-flash / longanyang` 组合，除非显式设置 `TANYUE_COSYVOICE_ALLOW_LEGACY=1`。

修改配置或代码后，需要重启 Agent worker：

```bash
python tanyue_agent.py start
```

如果房间里残留了旧 dispatch，可在 Web 页面换一个新的 Room 名称，或重启本地 LiveKit Server。

## 6. 实现结构

- `LiveKit/docker-compose.yml`：本地 LiveKit Server。
- `LiveKit/livekit.local.yaml`：本地 RTC 服务配置。
- `voice/scripts/livekit_voice_agent.py`：LiveKit Agent 启动入口。
- `voice/tanyue_livekit/aliyun_stt.py`：把 LiveKit `AudioFrame` 转成阿里云 Fun-ASR 实时识别输入，并把识别回调转换成 LiveKit `SpeechEvent`。
- `voice/tanyue_livekit/aliyun_cosyvoice.py`：创建/缓存 CosyVoice 复刻 voice_id，并把阿里云 CosyVoice 的 PCM 流转换成 LiveKit `AudioFrame`。
- `tanyue_agent.py`：项目根目录统一入口，负责 LiveKit Agent CLI 转发和 Web UI。
- `web/tanyue_livekit.html`：浏览器语音入口，负责加入 LiveKit 房间、发布麦克风音频、播放 Agent 音频。
- `voice/.env.livekit.example`：环境变量模板。
- `voice/requirements-livekit.txt`：LiveKit 线上模型链路依赖。

阿里云 CosyVoice 使用官方 Python SDK 的流式调用：Qwen 生成的文本片段会立即通过 `streaming_call()` 推给 CosyVoice，不再等待完整回复生成结束；CosyVoice 返回的 PCM 音频回调会直接转换为 LiveKit 音频帧。实际首包延迟仍取决于 Qwen 首 token、CosyVoice websocket 建连和 CosyVoice 自身需要的最小文本/声学上下文。

阿里云 STT 使用 DashScope `dashscope.audio.asr.Recognition` 流式接口。LiveKit 推来的音频帧会重采样到 16kHz mono PCM，再送入 Fun-ASR；中间识别结果映射为 `INTERIM_TRANSCRIPT`，句末结果映射为 `FINAL_TRANSCRIPT`。

## English

`voice` now uses LiveKit Agents as the default realtime voice-agent framework. The architecture is split into two layers:

- RTC / rooms / realtime audio transport: self-hosted local LiveKit Server
- STT: Aliyun realtime Fun-ASR
- LLM: Aliyun Bailian / DashScope OpenAI-compatible Qwen
- TTS: Aliyun CosyVoice WebSocket / Python SDK
- Realtime orchestration: local LiveKit Agents worker

RTC means Real-Time Communication. In this project it only transports realtime audio between the browser and the agent; it is not the STT/LLM/TTS model layer.

The older handcrafted pipeline is still kept as legacy debugging code, but new integration should use the root entrypoint:

```bash
python tanyue_agent.py console
python tanyue_agent.py start
python tanyue_agent.py dev
python tanyue_agent.py web
```

Configuration lives in `voice/.env`; use `voice/.env.livekit.example` as the template. Real `.env` files and `Config.py` are ignored by git.

Main files:

- `LiveKit/docker-compose.yml`: local LiveKit Server.
- `LiveKit/livekit.local.yaml`: local RTC config.
- `voice/scripts/livekit_voice_agent.py`: LiveKit entrypoint.
- `voice/tanyue_livekit/aliyun_stt.py`: Aliyun realtime ASR adapter from LiveKit `AudioFrame` to LiveKit `SpeechEvent`.
- `voice/tanyue_livekit/aliyun_cosyvoice.py`: Aliyun CosyVoice streaming TTS adapter for LiveKit `AudioFrame`.
- `tanyue_agent.py`: root entrypoint for LiveKit Agent CLI forwarding and the local Web UI.
- `web/tanyue_livekit.html`: browser client for room join, microphone publishing, and assistant audio playback.
- `voice/requirements-livekit.txt`: dependencies.
- `voice/.env.livekit.example`: configuration template.

CosyVoice now uses Aliyun voice cloning by default. The reference audio is `voice/reference.wav`, but creating a cloned voice requires a public audio URL that Aliyun can fetch. Create or refresh the cloned voice with:

```bash
TANYUE_COSYVOICE_CLONE_AUDIO_URL=https://your-valid-public-url/reference.wav \
python tanyue_agent.py clone-voice --force
```

The returned voice_id is cached in `voice/.cosyvoice_voice_id`; realtime sessions reuse the cached voice_id and do not upload the reference audio again. TTS style instructions are disabled by default while validating cloned-voice quality.

Aliyun CosyVoice is used through the official Python SDK streaming API. Qwen text chunks are forwarded to CosyVoice immediately with `streaming_call()` instead of waiting for the full reply. Returned PCM bytes are converted directly into LiveKit audio frames. The remaining first-audio latency depends on Qwen first-token time, CosyVoice websocket setup, and CosyVoice's own minimum text/acoustic context.

Aliyun STT uses DashScope `dashscope.audio.asr.Recognition`. LiveKit audio frames are resampled to 16kHz mono PCM, streamed to Fun-ASR, and returned as LiveKit interim/final transcript events.

Reference docs:

- https://help.aliyun.com/zh/model-studio/cosyvoice-websocket-api
- https://help.aliyun.com/zh/model-studio/cosyvoice-python-sdk
- https://help.aliyun.com/zh/model-studio/cosyvoice-client-events

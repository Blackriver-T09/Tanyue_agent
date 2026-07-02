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
- `TANYUE_COSYVOICE_MODEL=cosyvoice-v1`
- `TANYUE_COSYVOICE_VOICE=longxiaochun`

`voice/.env` 和项目根目录 `.env` 都会被自动读取；真实密钥已被 `.gitignore` 忽略。

本地 LiveKit 默认开发配置是：

```bash
LIVEKIT_URL=ws://127.0.0.1:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=devsecret
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
http://127.0.0.1:8893
```

推荐完整运行方式：

```bash
# Terminal 1: Agent worker
python tanyue_agent.py start

# Terminal 2: Web UI and token service
python tanyue_agent.py web
```

Agent 名称默认是 `tanyue`，可通过 `TANYUE_LIVEKIT_AGENT_NAME` 修改。

## 4. 排障

如果页面能显示用户转录，但没有 Agent 文本或语音回复，优先看 `python tanyue_agent.py start` 的后台日志：

- 看到 `Aliyun STT final transcript`：说明麦克风、LiveKit、阿里云 STT 都已经正常。
- 看到 `Tanyue job accepted`：确认当前实际使用的 `qwen_model`、`qwen_thinking`、`qwen_max_tokens`、`cosyvoice_model` 和 `voice`。
- 如果 `Aliyun STT final transcript` 到 `Aliyun CosyVoice first text chunk sent` 间隔很长，通常是 LLM 首 token 慢。实时语音默认设置 `TANYUE_QWEN_ENABLE_THINKING=0`；如果打开 thinking，首 token 可能从亚秒级变成数秒级。
- 看到 `Aliyun CosyVoice TTS error ... 428`：通常是 CosyVoice 模型或音色参数不匹配。默认已改为 `cosyvoice-v1 / longxiaochun`，并会自动忽略旧的 `cosyvoice-v3-flash / longanyang` 组合，除非显式设置 `TANYUE_COSYVOICE_ALLOW_LEGACY=1`。

修改配置或代码后，需要重启 Agent worker：

```bash
python tanyue_agent.py start
```

如果房间里残留了旧 dispatch，可在 Web 页面换一个新的 Room 名称，或重启本地 LiveKit Server。

## 5. 实现结构

- `LiveKit/docker-compose.yml`：本地 LiveKit Server。
- `LiveKit/livekit.local.yaml`：本地 RTC 服务配置。
- `voice/scripts/livekit_voice_agent.py`：LiveKit Agent 启动入口。
- `voice/tanyue_livekit/aliyun_stt.py`：把 LiveKit `AudioFrame` 转成阿里云 Fun-ASR 实时识别输入，并把识别回调转换成 LiveKit `SpeechEvent`。
- `voice/tanyue_livekit/aliyun_cosyvoice.py`：把阿里云 CosyVoice 的 PCM 流转换成 LiveKit `AudioFrame`。
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

Aliyun CosyVoice is used through the official Python SDK streaming API. Qwen text chunks are forwarded to CosyVoice immediately with `streaming_call()` instead of waiting for the full reply. Returned PCM bytes are converted directly into LiveKit audio frames. The remaining first-audio latency depends on Qwen first-token time, CosyVoice websocket setup, and CosyVoice's own minimum text/acoustic context.

Aliyun STT uses DashScope `dashscope.audio.asr.Recognition`. LiveKit audio frames are resampled to 16kHz mono PCM, streamed to Fun-ASR, and returned as LiveKit interim/final transcript events.

Reference docs:

- https://help.aliyun.com/zh/model-studio/cosyvoice-websocket-api
- https://help.aliyun.com/zh/model-studio/cosyvoice-python-sdk
- https://help.aliyun.com/zh/model-studio/cosyvoice-client-events

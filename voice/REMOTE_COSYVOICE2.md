# Tanyue Remote CosyVoice2 Voice Service

如果你只需要“文本转语音”，看这里。
如果你要完整的“麦克风 -> 转写 -> Qwen Flash -> TTS”语音回合，优先看 [README.md](./README.md) 和 `voice/scripts/realtime_voice_chat.py`。

## 中文

### 当前部署

- 远端主机：`WSL-Sakura`
- 服务目录：`/home/heihe/Competitions/tanyue_robot/voice_server`
- Conda 环境：`Tanyue`
- 模型：`iic/CosyVoice2-0.5B`
- 参考音频：`reference_voice.mp3`
- 内网服务：`http://127.0.0.1:8891`
- 公网入口：`https://frp-run.com:56330`

服务启动后会预加载 CosyVoice2 模型，并用 `reference_voice.mp3` 做一次 warmup。服务现在运行在 `screen` 会话 `tanyue_voice` 中，便于监控和手动控制。当前 `/health` 已返回：

- `ready: true`
- `sample_rate: 24000`
- `cuda: true`
- `stream_format: s16le mono PCM`

### Screen 管理

查看会话：

```bash
ssh WSL-Sakura 'screen -ls'
```

进入服务控制台：

```bash
ssh WSL-Sakura
screen -r tanyue_voice
```

在 screen 内退出但不停止服务：按 `Ctrl-a`，再按 `d`。

停止服务：进入 screen 后按 `Ctrl-c`，或执行：

```bash
ssh WSL-Sakura 'screen -S tanyue_voice -X quit'
```

重新后台启动：

```bash
ssh WSL-Sakura 'cd /home/heihe/Competitions/tanyue_robot/voice_server && screen -dmS tanyue_voice bash -lc "source /home/heihe/.pyenv/versions/anaconda3-2024.10-1/etc/profile.d/conda.sh; conda activate Tanyue; python server.py"'
```

### API

健康检查：

```bash
curl -k https://frp-run.com:56330/health
```

流式 TTS：

```bash
curl -k -N -X POST https://frp-run.com:56330/tts/stream \
  -H "Content-Type: application/json" \
  -d '{"text":"你好，我现在可以开始说话了。"}' \
  | ffplay -autoexit -nodisp -f s16le -ar 24000 -ch_layout mono -
```

请求体字段：

- `text`：必填，要合成的文本。
- `mode`：可选，`auto`、`cross_lingual` 或 `instruct2`，默认 `auto`。
- `instruct_text`：可选，仅 `instruct2` 模式使用。
- `speed`：可选，默认 `1.0`。

默认 `auto` 策略：没有 `--emotion` 时使用 `cross_lingual`，优先保证准确朗读 `text`；有 `--emotion` 时使用 `instruct2`，用情绪指令控制语气，并自动加上 CosyVoice2 需要的 `<|endofprompt|>`。`instruct2` 的表现会比 `cross_lingual` 更有语气起伏，但文本严格一致性仍可能略弱。

### 本地三个脚本

1. 输入文本和情绪，生成音频文件：

```bash
python voice/scripts/remote_tts_save.py \
  --text "我刚刚有点想你。" \
  --emotion "温柔、害羞、带一点撒娇" \
  --emotion-strength strong \
  --output output/tender.wav
```

情绪强度可选：`light`、`strong`、`max`。如果想更有感情：

```bash
python voice/scripts/remote_tts_save.py \
  --text "我刚刚有点想你。" \
  --emotion "温柔、害羞、带一点撒娇" \
  --emotion-strength max \
  --output output/tender.wav
```

建议 `--emotion` 使用短标签，不要写完整句子。脚本会自动生成类似 `温柔 / 害羞 / 带一点撒娇 / 亲近 / 起伏 / 轻声<|endofprompt|>` 的纯风格提示，降低把指令读出来的概率。

保存脚本默认直接保存服务端返回的原始 `24kHz/16-bit PCM WAV`，这是最快路径，不做重采样或转码。只有需要 macOS/QuickTime 兼容格式时才添加 `--convert`，它会转成 minimal `44.1kHz/16-bit WAV` 或 `.m4a`。

如果 macOS 仍然对 `.wav` 报 `-12842`，直接输出 `.m4a`：

```bash
python voice/scripts/remote_tts_save.py \
  --text "我刚刚有点想你。" \
  --emotion "温柔、害羞、带一点撒娇" \
  --output output/tender.m4a \
  --convert
```

2. 实时交互输入并播放：

```bash
python voice/scripts/remote_tts_chat.py \
  --emotion "温柔、亲近" \
  --emotion-strength strong
```

交互时可以直接输入要朗读的文本，也可以输入命令即时调参：

```bash
/emotion 开心、轻快
/strength max
/speed 0.9
/mode auto
/status
/help
```

`/mode auto` 会在有情绪时自动使用 `instruct2`，没有情绪时使用 `cross_lingual`。如果你想绝对稳定读原文，可以切 `/mode cross_lingual`；如果你想强制情绪控制，可以切 `/mode instruct2`。

3. Agent 调用脚本：

```bash
python voice/scripts/agent_remote_tts.py \
  --text "我在听。" \
  --emotion "认真、温柔" \
  | ffplay -autoexit -nodisp -f s16le -ar 24000 -ch_layout mono -
```

Agent 也可以直接 import：

```python
from voice.scripts.agent_remote_tts import create_client, build_request

client = create_client()
request = build_request(
    text="我在听。",
    emotion="认真、温柔",
    emotion_strength="strong",
)

for pcm_chunk in client.stream_pcm(request):
    audio_output.write(pcm_chunk)
```

也可以直接使用便捷函数：

```python
from voice.scripts.agent_remote_tts import stream_speech

for pcm_chunk in stream_speech("我在听。", emotion="认真、温柔", emotion_strength="strong"):
    audio_output.write(pcm_chunk)
```

客户端播放依赖 `ffplay`，本机需要安装 ffmpeg。所有流式接口返回 `s16le mono PCM, 24000Hz`。

默认情况下，本地 Python 客户端不会使用 `HTTP_PROXY/HTTPS_PROXY` 环境变量，因为 Sakura FRP 的自签 HTTPS 和非标准端口经代理时可能出现 TLS EOF。只有明确需要代理时才加：

```bash
python voice/scripts/remote_tts_save.py --use-env-proxy ...
```

如果仍然出现 `SSL: UNEXPECTED_EOF_WHILE_READING`，客户端会默认 fallback 到远端确认可用的入口 IP `183.131.59.150`，同时保留 `frp-run.com` 作为 TLS SNI/Host。也可以手动指定：

```bash
python voice/scripts/remote_tts_save.py \
  --resolve-ip 183.131.59.150 \
  --text "我刚刚有点想你。" \
  --emotion "温柔、害羞、带一点撒娇" \
  --output output/tender.wav
```

### 服务端管理

查看状态：

```bash
ssh WSL-Sakura 'curl -sS http://127.0.0.1:8891/health'
```

查看进程和端口：

```bash
ssh WSL-Sakura 'ss -ltnp | grep 8891; pgrep -af "python server.py"'
```

### 防火墙检查

我已确认服务监听在 `0.0.0.0:8891`。远端 `ufw status` 需要 sudo 密码，普通 SSH 用户无法读取完整防火墙规则。你可以在远端执行：

```bash
sudo ufw status verbose
sudo ufw allow 8891/tcp
```

如果公网 `https://frp-run.com:56330/health` 无法访问，优先检查：

- frp 是否把公网 `56330` 转发到远端 `8891`。
- WSL/宿主机防火墙是否允许 `8891/tcp`。
- 服务端是否仍在监听：`ssh WSL-Sakura 'ss -ltnp | grep 8891'`。

## English

### Current Deployment

- Remote host: `WSL-Sakura`
- Service directory: `/home/heihe/Competitions/tanyue_robot/voice_server`
- Conda environment: `Tanyue`
- Model: `iic/CosyVoice2-0.5B`
- Reference audio: `reference_voice.mp3`
- Local service URL: `http://127.0.0.1:8891`
- Public URL: `https://frp-run.com:56330`

The server preloads CosyVoice2 and runs one warmup pass with `reference_voice.mp3` during startup. It is currently running inside a detached `screen` session named `tanyue_voice`.

### Screen Management

List sessions:

```bash
ssh WSL-Sakura 'screen -ls'
```

Attach:

```bash
ssh WSL-Sakura
screen -r tanyue_voice
```

Detach without stopping: press `Ctrl-a`, then `d`.

Stop:

```bash
ssh WSL-Sakura 'screen -S tanyue_voice -X quit'
```

Start in the background:

```bash
ssh WSL-Sakura 'cd /home/heihe/Competitions/tanyue_robot/voice_server && screen -dmS tanyue_voice bash -lc "source /home/heihe/.pyenv/versions/anaconda3-2024.10-1/etc/profile.d/conda.sh; conda activate Tanyue; python server.py"'
```

### API

Health check:

```bash
curl -k https://frp-run.com:56330/health
```

Streaming TTS:

```bash
curl -k -N -X POST https://frp-run.com:56330/tts/stream \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello, I can speak now."}' \
  | ffplay -autoexit -nodisp -f s16le -ar 24000 -ch_layout mono -
```

The stream is raw PCM: signed 16-bit little-endian, mono, 24000 Hz.

The default `auto` strategy uses `cross_lingual` when no `--emotion` is provided, prioritizing exact text reading. When `--emotion` is provided, it uses `instruct2` with CosyVoice2's required `<|endofprompt|>` marker. `instruct2` gives more expressive prosody, but exact text stability can be slightly weaker than `cross_lingual`.

### Local Scripts

1. Save text plus emotion to a WAV file:

```bash
python voice/scripts/remote_tts_save.py \
  --text "I missed you a little." \
  --emotion "soft, shy, slightly playful" \
  --emotion-strength strong \
  --output output/tender.wav
```

Emotion strength options: `light`, `strong`, and `max`. Prefer short style tags instead of full instruction sentences. The client turns them into a tag-style prompt ending with `<|endofprompt|>` to reduce instruction leakage.

The save script keeps the server's original 24 kHz / 16-bit PCM WAV by default. This is the fastest path and avoids resampling/transcoding. Use `--convert` only when you need a macOS/QuickTime-friendly 44.1 kHz WAV or `.m4a`.

If macOS still reports `-12842` for `.wav`, save as `.m4a` instead:

```bash
python voice/scripts/remote_tts_save.py \
  --text "I missed you a little." \
  --emotion "soft, shy, slightly playful" \
  --output output/tender.m4a \
  --convert
```

2. Interactive streaming playback:

```bash
python voice/scripts/remote_tts_chat.py \
  --emotion "soft and close" \
  --emotion-strength strong
```

Runtime commands:

```bash
/emotion happy, playful
/strength max
/speed 0.9
/mode auto
/status
/help
```

`/mode auto` uses `instruct2` when emotion is set and `cross_lingual` otherwise. Use `/mode cross_lingual` for maximum text stability, or `/mode instruct2` for forced expressive control.

3. Agent bridge:

```bash
python voice/scripts/agent_remote_tts.py --text "I am listening." \
  | ffplay -autoexit -nodisp -f s16le -ar 24000 -ch_layout mono -
```

Python import:

```python
from voice.scripts.agent_remote_tts import create_client, build_request

client = create_client()
request = build_request(
    text="I am listening.",
    emotion="warm",
    emotion_strength="strong",
)

for pcm_chunk in client.stream_pcm(request):
    audio_output.write(pcm_chunk)
```

Convenience function:

```python
from voice.scripts.agent_remote_tts import stream_speech

for pcm_chunk in stream_speech("I am listening.", emotion="warm", emotion_strength="strong"):
    audio_output.write(pcm_chunk)
```

The client requires `ffplay`, provided by ffmpeg. The stream format is raw signed 16-bit little-endian mono PCM at 24000 Hz.

The Python clients ignore `HTTP_PROXY/HTTPS_PROXY` by default because Sakura FRP self-signed HTTPS on a non-standard port may fail through proxies with TLS EOF errors. Use `--use-env-proxy` only when a proxy is required.

If `SSL: UNEXPECTED_EOF_WHILE_READING` still appears, the clients fall back to the confirmed Sakura FRP entry IP `183.131.59.150` while preserving `frp-run.com` as TLS SNI/Host. You can also set it explicitly:

```bash
python voice/scripts/remote_tts_save.py \
  --resolve-ip 183.131.59.150 \
  --text "I missed you a little." \
  --emotion "soft, shy, slightly playful" \
  --output output/tender.wav
```

### Firewall

The service is confirmed to listen on `0.0.0.0:8891`. Full `ufw` status requires sudo on the remote host. If the public URL is unavailable, check frp forwarding, host firewall rules, and:

```bash
ssh WSL-Sakura 'ss -ltnp | grep 8891'
```

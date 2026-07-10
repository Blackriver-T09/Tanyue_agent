# Tanyue Robot Voice

宇树机器人发声装置开发目录。当前阶段先保存官方资料、SDK 源码和接口调研结论，后续在这里实现从 Tanyue 语音流到宇树 G1 扬声器的播放链路。

## Local References

- `docs/unitree_vui_client_service.html`
  - 原始 URL: `https://support.unitree.com/home/zh/G1_developer/VuiClient_Service`
  - 当前命令行抓取结果为 Tencent EdgeOne 567 拦截页，保留用于记录抓取状态。
- `docs/unitree_vui_client_service_en.html`
  - 英文同页抓取尝试，同样被拦截。
- `references/unitree_github_repos.json`
  - Unitree Robotics GitHub 组织 repo 列表。
- `references/unitree_sdk2_python/`
  - 官方 Python SDK2 浅克隆。
- `references/unitree_sdk2/`
  - 官方 C++ SDK2 浅克隆。
- `docs/unitree_voice_research.md`
  - 当前对 G1 AudioClient / VUI / 音频播放接口的本地总结。

## Working Direction

优先走 G1 的 `AudioClient`，而不是 Go2/B2 的 `VuiClient`：

- G1 发声服务名是 `voice`
- 支持内置 TTS
- 支持音量读取/设置
- 支持 RGB LED 控制
- 支持 16 kHz mono PCM 流式播放

`/Tanyue/voice` 目录只作为音频流参考，不在这里修改。

## Implemented Prototype

当前已经从 `/voice` 复制并本地化了远程 CosyVoice 流式 TTS 客户端，并增加了 G1 播放链路：

- `remote_tts_client.py`
  - 从 `/voice/tanyue_voice_remote/agent.py` 复制/裁剪而来
  - 请求远程 `/tts/stream`
  - 输出 `24 kHz / mono / s16le` PCM 流
- `pcm_resampler.py`
  - 使用 `ffmpeg` 将 `24 kHz / mono / s16le` 流式重采样为 G1 需要的 `16 kHz / mono / s16le`
- `unitree_g1_voice.py`
  - 包装官方 `unitree_sdk2py.g1.audio.g1_audio_client.AudioClient`
  - 自动优先使用本目录下浅克隆的 `references/unitree_sdk2_python`
  - 支持音量、LED、内置 TTS、PCM 流播放
- `stream_tts_to_robot.py`
  - 终端交互入口
  - 输入一句话，按回车后远程 TTS 开始流式生成，并通过 G1 `PlayStream` 播放

## Run

在连接 G1 的控制机上运行。`interface` 是连接机器人的网卡名，例如官方示例里的 `enp2s0`。

```bash
cd /Users/heihe/Desktop/Project/Tanyue
python robot_voice/stream_tts_to_robot.py enp2s0 --volume 85
```

进入交互后：

```text
> 你好，我是檀月。现在开始测试宇树机器人发声。
```

单句测试后退出：

```bash
python robot_voice/stream_tts_to_robot.py enp2s0 \
  --text "你好，我是檀月。现在开始测试宇树机器人发声。" \
  --volume 85
```

常用交互命令：

```text
/emotion 温柔 害羞
/strength light|strong|max
/speed 0.8
/mode auto|cross_lingual|instruct2
/volume 0-100
/led 255 80 120
/builtin 使用机器人内置 TTS 说这句话
/status
/help
```

## Runtime Requirements

本机已验证：

- Python 语法编译通过
- CLI help 正常
- `ffmpeg` 24k -> 16k 流式重采样正常

真实机器人播放还需要控制机具备：

- 能通过指定网卡访问 G1
- `ffmpeg`
- `unitree_sdk2py`
- `cyclonedds`

如果没有全局安装 `unitree_sdk2py`，脚本会尝试使用：

```text
robot_voice/references/unitree_sdk2_python
```

但 `cyclonedds` 仍需要在控制机环境中可用。安装方式见：

```text
robot_voice/references/unitree_sdk2_python/README.md
```

## Audio Format

远程 TTS 输出：

```text
24 kHz / mono / signed 16-bit little-endian PCM
```

G1 `AudioClient.PlayStream` 目标格式：

```text
16 kHz / mono / signed 16-bit little-endian PCM
```

当前默认重采样后每次读取 `3200 bytes`，约等于 `100 ms` 音频；发送间隔默认 `40 ms`，可以通过参数调整：

```bash
python robot_voice/stream_tts_to_robot.py enp2s0 --send-interval-ms 60
```

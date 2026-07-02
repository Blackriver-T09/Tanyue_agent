# Local LiveKit Server

## 中文

LiveKit 在本项目里只负责 RTC：浏览器、Agent worker、音频流和房间连接。STT、LLM、TTS 尽量走阿里云 API。

启动本地 LiveKit Server：

```bash
cd LiveKit
docker compose up
```

本地开发配置：

```bash
LIVEKIT_URL=ws://127.0.0.1:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=devsecret
```

端口：

- `7880`：LiveKit WebSocket / HTTP
- `7881`：RTC TCP fallback
- `50000-50100/udp`：RTC UDP media port range

开发阶段可以使用这里的 `devkey/devsecret`。正式部署时必须替换为强随机密钥，并按实际网络环境配置公网 IP、TLS、TURN 或反向代理。

## English

LiveKit is used as the local RTC layer: browser connection, agent worker connection, rooms, and realtime audio transport. STT, LLM, and TTS should be backed by Aliyun APIs where possible.

Start the local server:

```bash
cd LiveKit
docker compose up
```

Local development environment:

```bash
LIVEKIT_URL=ws://127.0.0.1:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=devsecret
```

Replace `devkey/devsecret` before any real deployment.


# Agent Hearing Channel

## 中文说明

`agent_hearing.py` 是给恋爱 agent 使用的模块化实时听觉通道。它保留独立命令行测试能力，同时提供三种 agent 接入方式：

- Python 模块：直接 `import AgentHearing`，通过回调或队列获取事件
- JSONL：命令行打印一行一个 JSON，适合子进程读取
- WebSocket：本地广播 `ws://127.0.0.1:8765`，适合多模块订阅

### 安装与环境

```sh
conda activate Tanyue
pip install -r hear/requirements-aliyun.txt
export DASHSCOPE_API_KEY="sk-..."
```

北京和新加坡 API Key 不同。默认使用北京 endpoint；如果你的 Key 属于新加坡：

```sh
export DASHSCOPE_REGION=singapore
```

### 独立测试

Fun-ASR：低延迟转写，返回句级/字级时间戳。

```sh
python hear/agent_hearing.py --backend funasr --stdout
```

Qwen-ASR：返回 7 类情绪标签。

```sh
export DASHSCOPE_WORKSPACE_ID="your-workspace-id"
python hear/agent_hearing.py --backend qwen --stdout
```

启动本地 WebSocket 广播：

```sh
python hear/agent_hearing.py --backend qwen --websocket --stdout
```

订阅地址：

```text
ws://127.0.0.1:8765
```

### Python 模块调用

```python
import os
from hear.agent_hearing import AgentHearing, HearingConfig

def on_hearing_event(event):
    if event["type"] == "transcription":
        print(event["final"], event["text"], event.get("emotion"))

config = HearingConfig(
    api_key=os.environ["DASHSCOPE_API_KEY"],
    backend="qwen",
    workspace=os.environ["DASHSCOPE_WORKSPACE_ID"],
    emit_stdout=False,
)

hearing = AgentHearing(config, on_event=on_hearing_event)
hearing.start_background()

# 在 agent 主循环中也可以拉取队列事件：
# event = hearing.get_event(timeout=0.5)
```

停止：

```python
hearing.stop()
```

### 事件结构

转写事件：

```json
{
  "type": "transcription",
  "source": "aliyun",
  "agent_id": "tanyue",
  "backend": "qwen",
  "model": "qwen3-asr-flash-realtime",
  "language": "zh",
  "final": false,
  "text": "我今天有点开心",
  "emotion": "happy",
  "tone": {
    "available": true,
    "source": "qwen3-asr-flash-realtime",
    "emotion": "happy",
    "labels": ["surprised", "neutral", "happy", "sad", "disgusted", "angry", "fearful"]
  },
  "timestamps": null,
  "received_at": 1782650000.0
}
```

Fun-ASR 的 `emotion` 为空，但会返回 `timestamps.words`：

```json
{
  "type": "transcription",
  "backend": "funasr",
  "final": true,
  "text": "好，我知道了",
  "emotion": null,
  "timestamps": {
    "begin_time_ms": 170,
    "end_time_ms": 920,
    "words": [
      {"begin_time": 170, "end_time": 295, "text": "好", "punctuation": "，"}
    ]
  }
}
```

### 选型建议

- 需要快速准确转写、字幕、对齐：使用 `--backend funasr`
- 需要情绪/语气标签：使用 `--backend qwen`
- agent 只需要单进程内消费：用 Python 回调或 `get_event`
- 多个模块同时消费：用 `--websocket`

## English Guide

`agent_hearing.py` is the modular realtime hearing channel for the love agent. The previous standalone test script remains unchanged. This script supports:

- Python module integration with callbacks or an event queue
- JSONL output for subprocess-based agents
- Local WebSocket broadcasting at `ws://127.0.0.1:8765`

### Setup

```sh
conda activate Tanyue
pip install -r hear/requirements-aliyun.txt
export DASHSCOPE_API_KEY="sk-..."
```

Beijing and Singapore use different API keys. The default endpoint is Beijing. For Singapore:

```sh
export DASHSCOPE_REGION=singapore
```

### Standalone Test

Fun-ASR gives low-latency transcription and word/sentence timestamps:

```sh
python hear/agent_hearing.py --backend funasr --stdout
```

Qwen-ASR gives 7-class emotion labels:

```sh
export DASHSCOPE_WORKSPACE_ID="your-workspace-id"
python hear/agent_hearing.py --backend qwen --stdout
```

Start a local WebSocket broadcaster:

```sh
python hear/agent_hearing.py --backend qwen --websocket --stdout
```

Subscribe to:

```text
ws://127.0.0.1:8765
```

### Python Integration

```python
import os
from hear.agent_hearing import AgentHearing, HearingConfig

def on_hearing_event(event):
    if event["type"] == "transcription":
        print(event["final"], event["text"], event.get("emotion"))

config = HearingConfig(
    api_key=os.environ["DASHSCOPE_API_KEY"],
    backend="qwen",
    workspace=os.environ["DASHSCOPE_WORKSPACE_ID"],
    emit_stdout=False,
)

hearing = AgentHearing(config, on_event=on_hearing_event)
hearing.start_background()

# You can also consume from the queue:
# event = hearing.get_event(timeout=0.5)
```

Stop it with:

```python
hearing.stop()
```

### Event Contract

All realtime payloads are JSON objects. Key fields:

- `type`: `transcription`, `vad`, `status`, or `error`
- `final`: whether this is a final utterance
- `text`: transcript text
- `emotion`: Qwen emotion label when available
- `tone`: normalized tone/emotion metadata
- `timestamps`: Fun-ASR sentence and word timestamps when available
- `raw`: raw provider payload when enabled

Use `funasr` for fast transcription and timestamps. Use `qwen` when the agent needs emotion/tone labels.

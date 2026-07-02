# Hearing

Realtime microphone transcription for the Tanyue love agent.

## Aliyun Realtime ASR

This is the current recommended path. It uses Alibaba Cloud Model Studio / DashScope realtime speech recognition from the `Tanyue` Conda environment.

```sh
conda activate Tanyue
pip install -r hear/requirements-aliyun.txt
export DASHSCOPE_API_KEY="sk-..."
python hear/aliyun_realtime_transcribe.py
```

For agent integration, use the modular channel in `agent_hearing.py` instead of the standalone test script:

```sh
python hear/agent_hearing.py --backend qwen --websocket --stdout
```

See `AGENT_HEARING.md` for Chinese and English integration docs.

Default mode is `fun-asr-realtime`: fast streaming transcription with structured sentence and word timestamps in JSON mode.

```sh
python hear/aliyun_realtime_transcribe.py --backend funasr --json
```

For faster turn ending in conversational use:

```sh
python hear/aliyun_realtime_transcribe.py --vad-silence-ms 300 --chunk-ms 50
```

Use Qwen-ASR when the love agent needs 7-class emotion output (`surprised`, `neutral`, `happy`, `sad`, `disgusted`, `angry`, `fearful`). Qwen realtime requires a Model Studio workspace URL or workspace id:

```sh
export DASHSCOPE_WORKSPACE_ID="your-workspace-id"
python hear/aliyun_realtime_transcribe.py --backend qwen --json
```

Chinese and English hints:

```sh
python hear/aliyun_realtime_transcribe.py --language zh
python hear/aliyun_realtime_transcribe.py --language en
```

If the SDK cannot connect to `dashscope.aliyuncs.com:443`, test the alternate endpoint preset:

```sh
python hear/aliyun_realtime_transcribe.py --region singapore
```

Or pass the exact WebSocket endpoint from your Model Studio console:

```sh
python hear/aliyun_realtime_transcribe.py --funasr-url "wss://..."
```

Beijing and Singapore use different API keys. Make sure `DASHSCOPE_API_KEY` belongs to the same region as the endpoint.

Useful output fields:

- `text`: cleaned transcript
- `final`: whether this is a final sentence
- `backend`: `funasr` or `qwen`
- `sentence`: Fun-ASR raw sentence object, including sentence and word timestamps when returned
- `emotion`: Qwen-ASR emotion label when using `--backend qwen`
- `event`: raw Qwen realtime event

The Alibaba documentation notes that Qwen-ASR realtime currently does not return timestamps. Use Fun-ASR when timestamp alignment matters; use Qwen-ASR when emotion matters.

## OpenAI Realtime

The OpenAI implementation is kept as `GPT_whisper_realtime_transcribe.py`. It follows OpenAI's Realtime transcription guide:

- 24 kHz mono PCM input
- short-lived transcription session token from `/v1/realtime/client_secrets`
- WebSocket connection to `/v1/realtime` using that transcription session token
- `session.update` with `type: "transcription"`
- `gpt-realtime-whisper` as the streaming transcription model
- `input_audio_buffer.append` for audio chunks
- manual `input_audio_buffer.commit` after local silence detection
- transcript delta and completion event handling

## Environment

Use the existing Conda environment:

```sh
conda activate Tanyue
pip install -r hear/requirements.txt
```

Set your API key:

```sh
export OPENAI_API_KEY="sk-..."
```

## Run

```sh
conda activate Tanyue
python hear/GPT_whisper_realtime_transcribe.py
```

The default language hint is Chinese (`zh`) and the default delay is `high` for better accuracy. For lower latency:

```sh
python hear/GPT_whisper_realtime_transcribe.py --delay medium
```

Do not connect to `/v1/realtime` with your normal API key for this transcription-only path. That creates a regular realtime session, and OpenAI will reject the transcription session update. The script creates a short-lived transcription client secret first, then uses that token for the WebSocket connection.

List microphone devices:

```sh
python -m sounddevice
```

Use a specific input device:

```sh
python hear/aliyun_realtime_transcribe.py --device 1
```

Press `Ctrl+C` to stop.

## Deprecated Local Route

The local SenseVoice + FunASR route was dropped for now. `requirements-sensevoice.txt` is kept only for reference.

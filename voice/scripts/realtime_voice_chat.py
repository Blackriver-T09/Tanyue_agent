#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:  # noqa: E402
    from Config import API_KEY as CONFIG_API_KEY  # type: ignore
except Exception:  # noqa: BLE001
    CONFIG_API_KEY = None
from voice.tanyue_voice_chat import VoiceConversationAgent, VoiceConversationConfig  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Realtime voice chat: microphone -> Qwen Flash -> remote TTS")
    parser.add_argument("--api-key", default=None, help="Bailian / DashScope API key. Defaults to Config.py.")
    parser.add_argument("--asr-backend", choices=("funasr", "qwen"), default="funasr")
    parser.add_argument("--asr-language", default="zh")
    parser.add_argument("--asr-device", default=None)
    parser.add_argument("--asr-chunk-ms", type=int, default=60)
    parser.add_argument("--asr-vad-silence-ms", type=int, default=320)
    parser.add_argument("--asr-vad-threshold", type=float, default=0.2)
    parser.add_argument("--workspace", default=os.environ.get("DASHSCOPE_WORKSPACE_ID"))
    parser.add_argument("--qwen-base-url", default="https://dashscope.aliyuncs.com/compatible-mode/v1")
    parser.add_argument("--qwen-model", default="qwen3.6-flash")
    parser.add_argument("--tts-api", default="https://frp-run.com:56330")
    parser.add_argument("--tts-emotion", default="温柔、亲近")
    parser.add_argument("--tts-emotion-strength", choices=("light", "strong", "max"), default="strong")
    parser.add_argument("--tts-mode", choices=("auto", "cross_lingual", "instruct2"), default="auto")
    parser.add_argument("--tts-speed", type=float, default=1.0)
    parser.add_argument("--tts-use-env-proxy", action="store_true")
    parser.add_argument("--tts-resolve-ip", default="183.131.59.150")
    parser.add_argument("--tts-segment-min-chars", type=int, default=12)
    parser.add_argument("--tts-segment-max-chars", type=int, default=28)
    parser.add_argument("--tts-segment-flush-seconds", type=float, default=0.9)
    parser.add_argument("--post-tts-cooldown-seconds", type=float, default=1.5)
    parser.add_argument("--qwen-max-tokens", type=int, default=192)
    parser.add_argument("--history-turns", type=int, default=8)
    parser.add_argument(
        "--system-prompt",
        default=(
            "你是Tanyue的语音对话助手。请用自然、简洁、口语化的中文回答，"
            "优先输出一到三句话，不要故意展开成长篇说明。"
        ),
    )
    args = parser.parse_args()

    api_key = args.api_key or CONFIG_API_KEY
    if not api_key:
        raise SystemExit("API key not found. Put it in Config.py or pass --api-key.")

    config = VoiceConversationConfig(
        api_key=api_key,
        hearing_backend=args.asr_backend,
        hearing_language=args.asr_language or None,
        hearing_device=args.asr_device,
        hearing_chunk_ms=args.asr_chunk_ms,
        hearing_vad_silence_ms=args.asr_vad_silence_ms,
        hearing_vad_threshold=args.asr_vad_threshold,
        hearing_workspace=args.workspace,
        qwen_base_url=args.qwen_base_url,
        qwen_model=args.qwen_model,
        tts_api_base=args.tts_api,
        tts_emotion=args.tts_emotion,
        tts_emotion_strength=args.tts_emotion_strength,
        tts_mode=args.tts_mode,
        tts_speed=args.tts_speed,
        tts_use_env_proxy=args.tts_use_env_proxy,
        tts_resolve_ip=args.tts_resolve_ip or None,
        tts_segment_min_chars=args.tts_segment_min_chars,
        tts_segment_max_chars=args.tts_segment_max_chars,
        tts_segment_flush_seconds=args.tts_segment_flush_seconds,
        post_tts_cooldown_seconds=args.post_tts_cooldown_seconds,
        qwen_max_tokens=args.qwen_max_tokens,
        history_turns=args.history_turns,
        system_prompt=args.system_prompt,
    )
    VoiceConversationAgent(config).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tanyue_voice_remote import RemoteTTSClient, RemoteTTSConfig, TTSRequest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a WAV file with the remote CosyVoice2 API.")
    parser.add_argument("--text", required=True, help="Text to speak.")
    parser.add_argument("--emotion", default="", help="Emotion/style prompt, e.g. 温柔、害羞、带一点撒娇.")
    parser.add_argument("--emotion-strength", choices=["light", "strong", "max"], default="strong")
    parser.add_argument("--output", required=True, help="Output WAV path.")
    parser.add_argument("--api", default="https://frp-run.com:56330", help="API base URL.")
    parser.add_argument("--mode", choices=["auto", "cross_lingual", "instruct2"], default="auto")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--instruct-text", help="Override the auto prompt generated from --emotion.")
    parser.add_argument("--use-env-proxy", action="store_true", help="Use HTTP_PROXY/HTTPS_PROXY from the environment.")
    parser.add_argument("--resolve-ip", default="183.131.59.150", help="Connect to this IP while keeping frp-run.com as TLS SNI/Host. Use empty string to disable.")
    parser.add_argument("--convert", action="store_true", help="Convert to a macOS-friendly 44.1 kHz WAV or M4A after generation.")
    args = parser.parse_args()

    client = RemoteTTSClient(
        RemoteTTSConfig(
            api_base=args.api,
            use_env_proxy=args.use_env_proxy,
            resolve_ip=args.resolve_ip or None,
        )
    )
    req = TTSRequest(
        text=args.text,
        emotion=args.emotion,
        emotion_strength=args.emotion_strength,
        mode=args.mode,
        speed=args.speed,
        instruct_text=args.instruct_text,
    )
    started = time.perf_counter()
    output = client.save_wav(req, args.output, compatible=args.convert)
    elapsed = time.perf_counter() - started
    print(f"output={output}")
    print(f"generation_seconds={elapsed:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tanyue_voice_remote import RemoteTTSClient, RemoteTTSConfig, TTSRequest  # noqa: E402


def create_client(
    api: str = "https://frp-run.com:56330",
    use_env_proxy: bool = False,
    resolve_ip: str | None = "183.131.59.150",
) -> RemoteTTSClient:
    return RemoteTTSClient(RemoteTTSConfig(api_base=api, use_env_proxy=use_env_proxy, resolve_ip=resolve_ip))


def build_request(
    text: str,
    emotion: str = "",
    emotion_strength: str = "strong",
    mode: str = "auto",
    speed: float = 1.0,
) -> TTSRequest:
    return TTSRequest(text=text, emotion=emotion, emotion_strength=emotion_strength, mode=mode, speed=speed)


def stream_speech(
    text: str,
    emotion: str = "",
    emotion_strength: str = "strong",
    api: str = "https://frp-run.com:56330",
    mode: str = "auto",
    speed: float = 1.0,
    use_env_proxy: bool = False,
    resolve_ip: str | None = "183.131.59.150",
):
    client = create_client(api=api, use_env_proxy=use_env_proxy, resolve_ip=resolve_ip)
    return client.stream_pcm(build_request(text, emotion, emotion_strength, mode, speed))


def save_speech(
    text: str,
    output: str | Path,
    emotion: str = "",
    emotion_strength: str = "strong",
    api: str = "https://frp-run.com:56330",
    mode: str = "auto",
    speed: float = 1.0,
    use_env_proxy: bool = False,
    resolve_ip: str | None = "183.131.59.150",
    compatible: bool = False,
) -> Path:
    client = create_client(api=api, use_env_proxy=use_env_proxy, resolve_ip=resolve_ip)
    return client.save_wav(build_request(text, emotion, emotion_strength, mode, speed), output, compatible=compatible)


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent-facing remote TTS bridge.")
    parser.add_argument("--text", required=True)
    parser.add_argument("--emotion", default="")
    parser.add_argument("--emotion-strength", choices=["light", "strong", "max"], default="strong")
    parser.add_argument("--api", default="https://frp-run.com:56330")
    parser.add_argument("--mode", choices=["auto", "cross_lingual", "instruct2"], default="auto")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--output", help="If set, save WAV instead of writing raw PCM to stdout.")
    parser.add_argument("--use-env-proxy", action="store_true", help="Use HTTP_PROXY/HTTPS_PROXY from the environment.")
    parser.add_argument("--resolve-ip", default="183.131.59.150", help="Connect to this IP while keeping frp-run.com as TLS SNI/Host. Use empty string to disable.")
    parser.add_argument("--convert", action="store_true", help="Convert saved output to a macOS-friendly 44.1 kHz WAV or M4A.")
    args = parser.parse_args()

    if args.output:
        path = save_speech(
            args.text,
            args.output,
            args.emotion,
            args.emotion_strength,
            args.api,
            args.mode,
            args.speed,
            args.use_env_proxy,
            args.resolve_ip or None,
            args.convert,
        )
        print(path)
        return 0

    for chunk in stream_speech(
        args.text,
        args.emotion,
        args.emotion_strength,
        args.api,
        args.mode,
        args.speed,
        args.use_env_proxy,
        args.resolve_ip or None,
    ):
        sys.stdout.buffer.write(chunk)
        sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

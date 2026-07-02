#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tanyue_voice_remote import RemoteTTSClient, RemoteTTSConfig, TTSRequest  # noqa: E402
from tanyue_voice_remote.agent import SAMPLE_RATE  # noqa: E402


VALID_STRENGTHS = {"light", "strong", "max"}
VALID_MODES = {"auto", "cross_lingual", "instruct2"}


def play_stream(client: RemoteTTSClient, req: TTSRequest) -> int:
    ffplay = shutil.which("ffplay")
    if not ffplay:
        raise RuntimeError("ffplay not found. Install ffmpeg first.")
    player = subprocess.Popen(
        [
            ffplay,
            "-autoexit",
            "-nodisp",
            "-f",
            "s16le",
            "-ar",
            str(SAMPLE_RATE),
            "-ch_layout",
            "mono",
            "-",
        ],
        stdin=subprocess.PIPE,
    )
    try:
        for chunk in client.stream_pcm(req):
            if player.stdin:
                try:
                    player.stdin.write(chunk)
                    player.stdin.flush()
                except BrokenPipeError:
                    break
    finally:
        if player.stdin:
            try:
                player.stdin.close()
            except BrokenPipeError:
                pass
    return player.wait()


def print_help() -> None:
    print(
        "Commands: /emotion TEXT | /strength light|strong|max | /speed 0.5-2.0 | "
        "/mode auto|cross_lingual|instruct2 | /status | /help | empty line exits"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Interactive remote CosyVoice2 streaming TTS.")
    parser.add_argument("--api", default="https://frp-run.com:56330", help="API base URL.")
    parser.add_argument("--emotion", default="", help="Default emotion/style prompt.")
    parser.add_argument("--emotion-strength", choices=["light", "strong", "max"], default="strong")
    parser.add_argument("--mode", choices=["auto", "cross_lingual", "instruct2"], default="auto")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--use-env-proxy", action="store_true", help="Use HTTP_PROXY/HTTPS_PROXY from the environment.")
    parser.add_argument("--resolve-ip", default="183.131.59.150", help="Connect to this IP while keeping frp-run.com as TLS SNI/Host. Use empty string to disable.")
    args = parser.parse_args()

    client = RemoteTTSClient(
        RemoteTTSConfig(
            api_base=args.api,
            use_env_proxy=args.use_env_proxy,
            resolve_ip=args.resolve_ip or None,
        )
    )
    emotion = args.emotion
    emotion_strength = args.emotion_strength
    mode = args.mode
    speed = args.speed
    print("Input text and press Enter.")
    print_help()
    while True:
        text = input("> ").strip()
        if not text:
            return 0
        if text.startswith("/emotion "):
            emotion = text[len("/emotion ") :].strip()
            print(f"emotion={emotion or '(default)'}")
            continue
        if text.startswith("/strength "):
            value = text[len("/strength ") :].strip()
            if value not in VALID_STRENGTHS:
                print("strength must be one of: light, strong, max")
                continue
            emotion_strength = value
            print(f"emotion_strength={emotion_strength}")
            continue
        if text.startswith("/speed "):
            value = text[len("/speed ") :].strip()
            try:
                new_speed = float(value)
            except ValueError:
                print("speed must be a number from 0.5 to 2.0")
                continue
            if not 0.5 <= new_speed <= 2.0:
                print("speed must be from 0.5 to 2.0")
                continue
            speed = new_speed
            print(f"speed={speed}")
            continue
        if text.startswith("/mode "):
            value = text[len("/mode ") :].strip()
            if value not in VALID_MODES:
                print("mode must be one of: auto, cross_lingual, instruct2")
                continue
            mode = value
            print(f"mode={mode}")
            continue
        if text == "/status":
            print(f"emotion={emotion or '(default)'} strength={emotion_strength} mode={mode} speed={speed}")
            continue
        if text == "/help":
            print_help()
            continue
        play_stream(
            client,
            TTSRequest(
                text=text,
                emotion=emotion,
                emotion_strength=emotion_strength,
                mode=mode,
                speed=speed,
            ),
        )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import ssl
import subprocess
import sys
from urllib import request


def stream_to_ffplay(api_base: str, text: str, mode: str, instruct_text: str, speed: float) -> int:
    ffplay = shutil.which("ffplay")
    if not ffplay:
        raise RuntimeError("ffplay not found. Install ffmpeg first, then retry.")

    payload = json.dumps(
        {
            "text": text,
            "mode": mode,
            "instruct_text": instruct_text,
            "speed": speed,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = request.Request(
        api_base.rstrip("/") + "/tts/stream",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    player = subprocess.Popen(
        [
            ffplay,
            "-autoexit",
            "-nodisp",
            "-f",
            "s16le",
            "-ar",
            "24000",
            "-ch_layout",
            "mono",
            "-",
        ],
        stdin=subprocess.PIPE,
    )
    try:
        context = ssl._create_unverified_context() if api_base.startswith("https://") else None
        with request.urlopen(req, timeout=120, context=context) as response:
            while True:
                chunk = response.read(8192)
                if not chunk:
                    break
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Stream TTS from the remote Tanyue CosyVoice2 API.")
    parser.add_argument("--api", default="https://frp-run.com:56330", help="Remote API base URL.")
    parser.add_argument("--text", help="Text to synthesize. If omitted, starts an interactive loop.")
    parser.add_argument("--mode", choices=["cross_lingual", "instruct2"], default="cross_lingual")
    parser.add_argument("--instruct-text", default="用自然、亲近、温柔的语气说话。")
    parser.add_argument("--speed", type=float, default=1.0)
    args = parser.parse_args()

    if args.text:
        return stream_to_ffplay(args.api, args.text, args.mode, args.instruct_text, args.speed)

    print("Type text and press Enter. Empty line exits.")
    while True:
        text = input("> ").strip()
        if not text:
            return 0
        stream_to_ffplay(args.api, text, args.mode, args.instruct_text, args.speed)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)

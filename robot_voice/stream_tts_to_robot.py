#!/usr/bin/env python3
from __future__ import annotations

import argparse
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from robot_voice.pcm_resampler import resample_s16le_mono_stream
from robot_voice.remote_tts_client import RemoteTTSClient, RemoteTTSConfig, TTSRequest
from robot_voice.unitree_g1_voice import UnitreeG1Voice


VALID_STRENGTHS = {"light", "strong", "max"}
VALID_MODES = {"auto", "cross_lingual", "instruct2"}


def print_help() -> None:
    print(
        "Commands: /emotion TEXT | /strength light|strong|max | /speed 0.5-2.0 | "
        "/mode auto|cross_lingual|instruct2 | /volume 0-100 | /led R G B | "
        "/builtin TEXT | /status | /help | empty line exits"
    )


def stream_text_to_robot(
    tts: RemoteTTSClient,
    robot: UnitreeG1Voice,
    text: str,
    emotion: str,
    emotion_strength: str,
    mode: str,
    speed: float,
    app_name: str,
    send_interval_ms: float,
    verbose: bool,
) -> None:
    req = TTSRequest(
        text=text,
        emotion=emotion,
        emotion_strength=emotion_strength,
        mode=mode,
        speed=speed,
    )
    pcm24 = tts.stream_pcm(req)
    pcm16 = resample_s16le_mono_stream(pcm24, input_rate=24000, output_rate=16000, read_size=3200)
    robot.play_pcm16_16k_mono_stream(
        pcm16,
        app_name=app_name,
        stream_id=str(int(time.time() * 1000)),
        send_interval_ms=send_interval_ms,
        verbose=verbose,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Stream remote TTS to Unitree G1 speaker.")
    parser.add_argument("interface", nargs="?", help="Network interface connected to the robot, e.g. enp2s0.")
    parser.add_argument("--api", default="https://frp-run.com:56330", help="Remote TTS API base URL.")
    parser.add_argument("--text", help="Speak one sentence and exit. If omitted, starts an interactive loop.")
    parser.add_argument("--emotion", default="", help="Default emotion/style prompt.")
    parser.add_argument("--emotion-strength", choices=["light", "strong", "max"], default="strong")
    parser.add_argument("--mode", choices=["auto", "cross_lingual", "instruct2"], default="auto")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--volume", type=int, help="Set robot volume on startup.")
    parser.add_argument("--app-name", default="tanyue")
    parser.add_argument("--send-interval-ms", type=float, default=40.0)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--use-env-proxy", action="store_true")
    parser.add_argument("--resolve-ip", default="183.131.59.150", help="Use empty string to disable direct-IP fallback.")
    parser.add_argument("--list-interfaces", action="store_true", help="List local network interfaces and exit.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.list_interfaces:
        for _index, name in socket.if_nameindex():
            print(name)
        return 0

    if not args.interface:
        parser.error("interface is required unless --list-interfaces is used")

    robot = UnitreeG1Voice(args.interface, timeout=args.timeout)
    print(f"[robot] connecting on interface={args.interface} ...")
    robot.connect()
    if args.volume is not None:
        robot.set_volume(args.volume)
        print(f"[robot] volume set to {args.volume}")

    tts = RemoteTTSClient(
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

    if args.text:
        stream_text_to_robot(
            tts,
            robot,
            args.text,
            emotion,
            emotion_strength,
            mode,
            speed,
            args.app_name,
            args.send_interval_ms,
            args.verbose,
        )
        return 0

    print("Input text and press Enter. The robot will start speaking as the TTS stream arrives.")
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
            try:
                speed = float(text[len("/speed ") :].strip())
            except ValueError:
                print("speed must be a number")
                continue
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
        if text.startswith("/volume "):
            try:
                volume = int(text[len("/volume ") :].strip())
            except ValueError:
                print("volume must be an integer 0-100")
                continue
            robot.set_volume(volume)
            print(f"volume={volume}")
            continue
        if text.startswith("/led "):
            parts = text[len("/led ") :].split()
            if len(parts) != 3:
                print("usage: /led R G B")
                continue
            robot.led(int(parts[0]), int(parts[1]), int(parts[2]))
            continue
        if text.startswith("/builtin "):
            robot.say_builtin(text[len("/builtin ") :].strip())
            continue
        if text == "/status":
            print(f"emotion={emotion or '(default)'} strength={emotion_strength} mode={mode} speed={speed}")
            continue
        if text == "/help":
            print_help()
            continue

        stream_text_to_robot(
            tts,
            robot,
            text,
            emotion,
            emotion_strength,
            mode,
            speed,
            args.app_name,
            args.send_interval_ms,
            args.verbose,
        )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)

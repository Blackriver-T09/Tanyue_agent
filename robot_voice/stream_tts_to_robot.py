#!/usr/bin/env python3
from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from robot_voice.pcm_resampler import resample_s16le_mono_stream
from robot_voice.unitree_g1_voice import UnitreeG1Voice, apply_gain_s16le_stream
from robot_voice.voice_registry import load_voice_registry, resolve_voice, unique_voice_entries
from voice.tanyue_livekit.aliyun_cosyvoice import AliyunCosyVoiceTTS, config_from_env


VALID_STRENGTHS = {"light", "strong", "max"}
VALID_MODES = {"auto", "cross_lingual", "instruct2"}


def print_interfaces() -> None:
    try:
        result = subprocess.run(["ifconfig"], check=False, capture_output=True, text=True)
    except OSError:
        for _index, name in socket.if_nameindex():
            print(name)
        return

    if result.returncode != 0 or not result.stdout:
        for _index, name in socket.if_nameindex():
            print(name)
        return

    current = None
    blocks: dict[str, list[str]] = {}
    for line in result.stdout.splitlines():
        if line and not line.startswith(("\t", " ")) and ":" in line:
            current = line.split(":", 1)[0]
            blocks[current] = [line]
        elif current:
            blocks[current].append(line)

    for _index, name in socket.if_nameindex():
        lines = blocks.get(name, [])
        status = "unknown"
        inet_values = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("status:"):
                status = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("inet "):
                parts = stripped.split()
                if len(parts) >= 2:
                    inet_values.append(parts[1])
        inet_text = ",".join(inet_values) if inet_values else "-"
        print(f"{name:10s} status={status:8s} inet={inet_text}")


def print_help() -> None:
    print(
        "Commands: /emotion TEXT | /strength light|strong|max | /speed 0.5-2.0 | "
        "/mode auto|cross_lingual|instruct2 | /volume 0-100 | /led R G B | "
        "/gain DB | /voice ID | /voices | /builtin TEXT | /status | /help | empty line exits"
    )


def print_voices() -> None:
    for entry in unique_voice_entries():
        voice_id = entry.registered_voice_id or "(unregistered)"
        print(f"{entry.key:10s} voice_id={voice_id:48s} source={entry.source_file_name}")


def stream_text_to_robot(
    tts: AliyunCosyVoiceTTS,
    robot: UnitreeG1Voice,
    text: str,
    emotion: str,
    emotion_strength: str,
    mode: str,
    speed: float,
    voice_id: str,
    app_name: str,
    send_interval_ms: float | None,
    tail_wait_ms: float,
    gain_db: float,
    trim_start_ms: float,
    robot_chunk_bytes: int,
    verbose: bool,
) -> None:
    pcm24 = tts.stream_pcm_bytes(
        text,
        voice_id=voice_id,
        emotion=emotion,
        emotion_strength=emotion_strength,
        mode=mode,
        speed=speed,
    )
    pcm24 = trim_pcm_stream(pcm24, sample_rate=24000, trim_start_ms=trim_start_ms)
    pcm16 = resample_s16le_mono_stream(pcm24, input_rate=24000, output_rate=16000, read_size=3200)
    pcm16 = apply_gain_s16le_stream(pcm16, gain_db)
    robot.play_pcm16_16k_mono_stream(
        pcm16,
        app_name=app_name,
        stream_id=str(int(time.time() * 1000)),
        send_interval_ms=send_interval_ms,
        tail_wait_ms=tail_wait_ms,
        robot_chunk_bytes=robot_chunk_bytes,
        verbose=verbose,
    )


def trim_pcm_stream(chunks, sample_rate: int, trim_start_ms: float):
    bytes_to_skip = int(sample_rate * 2 * max(trim_start_ms, 0.0) / 1000.0)
    if bytes_to_skip <= 0:
        yield from chunks
        return
    remaining = bytes_to_skip
    for chunk in chunks:
        if remaining >= len(chunk):
            remaining -= len(chunk)
            continue
        if remaining:
            chunk = chunk[remaining:]
            remaining = 0
        yield chunk


def main() -> int:
    parser = argparse.ArgumentParser(description="Stream voice CosyVoice TTS to Unitree G1 speaker.")
    parser.add_argument("interface", nargs="?", help="Network interface connected to the robot, e.g. enp2s0.")
    parser.add_argument("--text", help="Speak one sentence and exit. If omitted, starts an interactive loop.")
    parser.add_argument("--voice", default="default", help="Voice key or registered voice_id. Use --list-voices to inspect.")
    parser.add_argument("--emotion", default="", help="Default emotion/style prompt.")
    parser.add_argument("--emotion-strength", choices=["light", "strong", "max"], default="strong")
    parser.add_argument("--mode", choices=["auto", "cross_lingual", "instruct2"], default="auto")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--volume", type=int, help="Set robot volume on startup.")
    parser.add_argument("--app-name", default="tanyue")
    parser.add_argument(
        "--send-interval-ms",
        type=float,
        help="Delay after each robot chunk. Default follows chunk audio duration, like Unitree examples.",
    )
    parser.add_argument("--tail-wait-ms", type=float, default=1000.0)
    parser.add_argument("--robot-chunk-bytes", type=int, default=96000, help="Bytes per PlayStream call. Unitree examples use 96000.")
    parser.add_argument("--gain-db", type=float, default=0.0, help="PCM gain before sending to robot. Try 3-9 if robot is quiet.")
    parser.add_argument("--trim-start-ms", type=float, default=0.0, help="Drop this many milliseconds from the start of synthesized PCM.")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--list-interfaces", action="store_true", help="List local network interfaces with status/IP and exit.")
    parser.add_argument("--list-voices", action="store_true", help="List local registered voices and exit.")
    parser.add_argument("--check", action="store_true", help="Connect to the robot, print the current volume, and exit.")
    parser.add_argument("--builtin-text", help="Use the robot built-in TTS once and exit.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.list_interfaces:
        print_interfaces()
        return 0

    if args.list_voices:
        print_voices()
        return 0

    if not args.interface:
        parser.error("interface is required unless --list-interfaces or --list-voices is used")

    registry = load_voice_registry()
    try:
        voice = resolve_voice(args.voice, registry)
    except ValueError as exc:
        parser.error(str(exc))

    robot = UnitreeG1Voice(args.interface, timeout=args.timeout)
    print(f"[robot] connecting on interface={args.interface} ...")
    robot.connect()
    if args.volume is not None:
        robot.set_volume(args.volume)
        print(f"[robot] volume set to {args.volume}")

    if args.check:
        print(f"[robot] connected. volume={robot.get_volume()}")
        return 0

    if args.builtin_text:
        robot.say_builtin(args.builtin_text)
        return 0

    tts = AliyunCosyVoiceTTS(config_from_env())
    if tts.config.clone_enabled:
        tts.ensure_cloned_voice()

    emotion = args.emotion
    emotion_strength = args.emotion_strength
    mode = args.mode
    speed = args.speed
    gain_db = args.gain_db
    voice_id = voice.registered_voice_id

    if args.text:
        stream_text_to_robot(
            tts,
            robot,
            args.text,
            emotion,
            emotion_strength,
            mode,
            speed,
            voice_id,
            args.app_name,
            args.send_interval_ms,
            args.tail_wait_ms,
            args.gain_db,
            args.trim_start_ms,
            args.robot_chunk_bytes,
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
        if text.startswith("/voice "):
            value = text[len("/voice ") :].strip()
            try:
                voice = resolve_voice(value, registry)
            except ValueError as exc:
                print(exc)
                continue
            voice_id = voice.registered_voice_id
            print(f"voice={voice.key} voice_id={voice_id} source={voice.source_file_name}")
            continue
        if text == "/voices":
            print_voices()
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
        if text.startswith("/gain "):
            try:
                gain_db = float(text[len("/gain ") :].strip())
            except ValueError:
                print("gain must be a number, for example: /gain 6")
                continue
            print(f"gain_db={gain_db}")
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
            print(
                f"emotion={emotion or '(default)'} strength={emotion_strength} "
                f"mode={mode} speed={speed} gain_db={gain_db} voice_id={voice_id}"
            )
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
            voice_id,
            args.app_name,
            args.send_interval_ms,
            args.tail_wait_ms,
            gain_db,
            args.trim_start_ms,
            args.robot_chunk_bytes,
            args.verbose,
        )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .agent import PunGenAgent
from .unitree_io import (
    G1BuiltinVoiceClient,
    G1MotionOutput,
    G1MusicOutput,
    G1VoiceOutput,
    LowLevelAccordionRunner,
    TANYUE_ROOT,
    connect_g1,
)
from .unitree_runtime import PunGenUnitreeRuntime


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Realtime microphone -> PunGen meme recognition -> Unitree G1 voice/action runtime."
    )
    parser.add_argument("interface", help="Network interface connected to G1, e.g. en7 or enp2s0.")
    parser.add_argument("--backend", choices=("funasr", "qwen"), default="funasr")
    parser.add_argument("--device", help="Microphone device index or name.")
    parser.add_argument("--region", choices=("beijing", "singapore"), default="beijing")
    parser.add_argument("--vad-silence-ms", type=int, default=350)
    parser.add_argument("--trump-wav", type=Path, help="Licensed 16 kHz mono PCM16 Trump voice pack WAV.")
    parser.add_argument("--ymca-wav", type=Path, help="Licensed 16 kHz mono PCM16 YMCA excerpt WAV.")
    parser.add_argument("--volume", type=int, default=85)
    parser.add_argument("--accordion-bin", type=Path, help="Compiled low-level G1 accordion executable.")
    parser.add_argument(
        "--enable-low-level-accordion",
        action="store_true",
        help="Explicitly allow the low-level arm controller. Requires a clear robot workspace.",
    )
    parser.add_argument("--text", help="Skip microphone and execute one text turn for hardware smoke testing.")
    return parser


def create_runtime(args: argparse.Namespace) -> PunGenUnitreeRuntime:
    audio, loco = connect_g1(args.interface)
    audio.SetVolume(max(0, min(100, args.volume)))
    robot_voice = G1BuiltinVoiceClient(audio)
    voice_tracks = {"cyber_trump": args.trump_wav} if args.trump_wav else {}
    music_tracks = {"ymca": args.ymca_wav} if args.ymca_wav else {}
    accordion_runner = None
    if args.accordion_bin:
        accordion_runner = LowLevelAccordionRunner(
            args.accordion_bin,
            args.interface,
            enabled=args.enable_low_level_accordion,
        )
    return PunGenUnitreeRuntime(
        agent=PunGenAgent.from_default_library(),
        voice=G1VoiceOutput(robot_voice, voice_pack_tracks=voice_tracks),
        motion=G1MotionOutput(loco, accordion_runner=accordion_runner),
        music=G1MusicOutput(robot_voice, music_tracks),
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    runtime = create_runtime(args)
    if args.text:
        print(json.dumps(runtime.handle_transcript(args.text), ensure_ascii=False, indent=2))
        return 0

    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("ALIYUN_API_KEY")
    if not api_key:
        raise SystemExit("Set DASHSCOPE_API_KEY before starting realtime ASR.")
    tanyue_path = str(TANYUE_ROOT)
    if tanyue_path not in sys.path:
        sys.path.insert(0, tanyue_path)
    from hear.agent_hearing import AgentHearing, HearingConfig

    def on_event(event: dict[str, Any]) -> None:
        if event.get("type") == "transcription":
            print(json.dumps(event, ensure_ascii=False), flush=True)
        result = runtime.handle_hearing_event(event)
        if result is not None:
            print(json.dumps(result, ensure_ascii=False), flush=True)

    device: int | str | None = args.device
    if isinstance(device, str) and device.isdigit():
        device = int(device)
    hearing = AgentHearing(
        HearingConfig(
            api_key=api_key,
            backend=args.backend,
            device=device,
            region=args.region,
            vad_silence_ms=args.vad_silence_ms,
            chunk_ms=50,
            semantic_punctuation=True,
            emit_stdout=False,
            agent_id="pungen-unitree",
        ),
        on_event=on_event,
    )
    hearing.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

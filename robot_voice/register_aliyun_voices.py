#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from robot_voice.aliyun_cosyvoice_client import config_from_project
from robot_voice.voice_registry import REGISTRY_PATH, update_registered_voice_id, unique_voice_entries


def parse_pair(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected KEY=VALUE")
    key, item = value.split("=", 1)
    key = key.strip()
    item = item.strip()
    if not key or not item:
        raise argparse.ArgumentTypeError("expected non-empty KEY=VALUE")
    return key, item


def main() -> int:
    parser = argparse.ArgumentParser(description="Register Aliyun CosyVoice cloned voices and update robot_voice/voice_registry.json.")
    parser.add_argument("--url", action="append", type=parse_pair, default=[], help="Public audio URL as key=https://...")
    parser.add_argument("--set-voice-id", action="append", type=parse_pair, default=[], help="Manually write an existing voice_id as key=voice_id.")
    parser.add_argument("--target-model", default=None, help="Defaults to TANYUE_COSYVOICE_MODEL or cosyvoice-v3.5-plus.")
    parser.add_argument("--max-seconds", type=float, default=20.0)
    parser.add_argument("--language-hint", default="zh", help="Single language hint required by Aliyun, for example zh or en.")
    parser.add_argument("--list", action="store_true", help="List local registry and exit.")
    args = parser.parse_args()

    if args.list:
        print_registry()
        return 0

    for key, voice_id in args.set_voice_id:
        update_registered_voice_id(key, voice_id)
        print(f"{key}: registered_voice_id={voice_id}")

    if args.url:
        from dashscope.audio.tts_v2 import VoiceEnrollmentService

        config = config_from_project()
        service = VoiceEnrollmentService(api_key=config.api_key, workspace=config.workspace_id)
        target_model = args.target_model or config.model
        for key, url in args.url:
            prefix = normalize_prefix(key)
            voice_id = service.create_voice(
                target_model=target_model,
                prefix=prefix,
                url=url,
                language_hints=[args.language_hint] if args.language_hint else None,
                max_prompt_audio_length=args.max_seconds,
            )
            update_registered_voice_id(key, voice_id)
            print(f"{key}: registered_voice_id={voice_id}")

    print(f"updated: {REGISTRY_PATH}")
    print_registry()
    return 0


def print_registry() -> None:
    for entry in unique_voice_entries():
        voice_id = entry.registered_voice_id or "(unregistered)"
        print(f"{entry.key:10s} voice_id={voice_id} source={entry.source_file_name}")


def normalize_prefix(value: str) -> str:
    normalized = "".join(ch for ch in value.lower() if ch.isdigit() or ("a" <= ch <= "z"))
    return (normalized or "tanyue")[:9]


if __name__ == "__main__":
    raise SystemExit(main())

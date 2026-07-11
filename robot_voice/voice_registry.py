from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REGISTRY_PATH = ROOT / "voice_registry.json"


@dataclass(frozen=True)
class VoiceEntry:
    key: str
    registered_voice_id: str
    source_file_name: str
    display_name: str
    notes: str = ""
    trim_start_ms: float = 0.0


def load_voice_registry(path: Path = REGISTRY_PATH) -> dict[str, VoiceEntry]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries: dict[str, VoiceEntry] = {}
    for item in payload["voices"]:
        entry = VoiceEntry(
            key=item["key"],
            registered_voice_id=item["registered_voice_id"],
            source_file_name=item["source_file_name"],
            display_name=item.get("display_name", item["key"]),
            notes=item.get("notes", ""),
            trim_start_ms=float(item.get("trim_start_ms", 0.0) or 0.0),
        )
        entries[entry.key] = entry
        entries[entry.registered_voice_id] = entry
    return entries


def resolve_voice(value: str | None, registry: dict[str, VoiceEntry] | None = None) -> VoiceEntry:
    entries = registry or load_voice_registry()
    key = (value or "default").strip() or "default"
    try:
        entry = entries[key]
    except KeyError as exc:
        choices = sorted({entry.key for entry in entries.values()})
        raise ValueError(f"Unknown voice {key!r}. Available voices: {', '.join(choices)}") from exc
    if not entry.registered_voice_id:
        raise ValueError(
            f"Voice {entry.key!r} is not registered yet. "
            f"Source file: {entry.source_file_name}. Run robot_voice/register_aliyun_voices.py with a public audio URL."
        )
    return entry


def unique_voice_entries(registry: dict[str, VoiceEntry] | None = None) -> list[VoiceEntry]:
    entries = registry or load_voice_registry()
    seen = set()
    result = []
    for entry in entries.values():
        if entry.key in seen:
            continue
        seen.add(entry.key)
        result.append(entry)
    return sorted(result, key=lambda item: item.key)


def update_registered_voice_id(key: str, voice_id: str, path: Path = REGISTRY_PATH) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    for item in payload["voices"]:
        if item["key"] == key:
            item["registered_voice_id"] = voice_id
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return
    raise KeyError(f"Unknown voice key: {key}")

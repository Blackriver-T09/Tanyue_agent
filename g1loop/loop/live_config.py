"""Live hardware configuration loading."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LiveConfig:
    """Runtime config for first-on-robot execution."""

    network_interface: str = ""
    enable_hands: bool = True
    hand_joint: str = "L10"
    can: str = "can0"
    modbus: str = "None"
    intensity: str = "low"
    repeat: int = 1
    use_live: bool = False


DEFAULT_CONFIG = LiveConfig()


def load_live_config(path: str | None = None) -> LiveConfig:
    """Load live config JSON, falling back to defaults."""

    if not path:
        return DEFAULT_CONFIG
    file_path = Path(path)
    payload: dict[str, Any] = json.loads(file_path.read_text(encoding="utf-8"))
    return LiveConfig(
        network_interface=str(payload.get("network_interface", DEFAULT_CONFIG.network_interface)),
        enable_hands=payload.get("enable_hands", DEFAULT_CONFIG.enable_hands),
        hand_joint=payload.get("hand_joint", DEFAULT_CONFIG.hand_joint),
        can=payload.get("can", DEFAULT_CONFIG.can),
        modbus=payload.get("modbus", DEFAULT_CONFIG.modbus),
        intensity=payload.get("intensity", DEFAULT_CONFIG.intensity),
        repeat=int(payload.get("repeat", DEFAULT_CONFIG.repeat)),
        use_live=payload.get("use_live", DEFAULT_CONFIG.use_live),
    )


def dump_default_config(path: str) -> None:
    """Write a starter live config file."""

    file_path = Path(path)
    file_path.write_text(
        json.dumps(asdict(DEFAULT_CONFIG), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .action_library import load_action_library
from .execution import ExecutionModule
from .recognizer import load_meme_library


def build_system_status_payload(execution_module: ExecutionModule) -> dict[str, Any]:
    summary: dict[str, int] = {}
    for event in execution_module.recorder.list_events():
        level = event.evidence_level.value
        summary[level] = summary.get(level, 0) + 1
    return {
        "protocol_version": "pungen-system/v0",
        "runtime": {"status": "ready", "safety_mode": "safe_no_contact"},
        "knowledge": {
            "meme_count": len(load_meme_library()),
            "action_count": len(load_action_library()),
        },
        "adapters": execution_module.describe_adapters(),
        "devices": {
            "unitree_body": {"status": "not_configured", "evidence_level": None},
            "robot_arm": {"status": "not_configured", "evidence_level": None},
            "dexterous_hand": {"status": "not_configured", "evidence_level": None},
        },
        "evidence_summary": summary,
    }


def build_meme_catalog_payload() -> dict[str, Any]:
    return {
        "protocol_version": "pungen-memes/v0",
        "memes": [asdict(meme) for meme in load_meme_library()],
    }

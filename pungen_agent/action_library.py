from __future__ import annotations

import json
from pathlib import Path
from pathlib import Path
from typing import Any


def load_action_library(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    if path is None:
        raw = (Path(__file__).resolve().parent / "data" / "action_library.json").read_text(
            encoding="utf-8"
        )
    else:
        raw = Path(path).read_text(encoding="utf-8")
    actions = json.loads(raw)
    return {str(action["action_id"]): action for action in actions}


def build_action_library_payload(
    path: str | Path | None = None,
) -> dict[str, Any]:
    actions_by_id = load_action_library(path)
    return {
        "protocol_version": "pungen-actions/v0",
        "actions": list(actions_by_id.values()),
    }

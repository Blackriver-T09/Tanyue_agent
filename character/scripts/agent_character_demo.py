#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tanyue_character import CharacterAgent, CharacterAgentConfig


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a demo command sequence to the Tanyue character page")
    parser.add_argument("--bridge", default="http://127.0.0.1:8893")
    parser.add_argument("--motion", default="waving")
    parser.add_argument("--expression", default="happy")
    args = parser.parse_args()

    agent = CharacterAgent(CharacterAgentConfig(base_url=args.bridge))
    print(agent.health())
    agent.set_pose("happy")
    agent.set_expression(args.expression)
    agent.play_motion(args.motion, loop=False, speed=1.0)
    time.sleep(2.0)
    agent.set_lip_sync_level(0.75)
    time.sleep(0.25)
    agent.set_lip_sync_level(0.2)
    time.sleep(0.4)
    agent.stop_motion()
    agent.listening()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

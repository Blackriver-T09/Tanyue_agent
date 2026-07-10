"""Small demo script for controlling the Unitree G1 MuJoCo model."""

from __future__ import annotations

import argparse
import time

from .controller import G1MujocoController
from .model import MODEL_VARIANTS
from .runtime import G1MujocoRuntime
from ..motions.emote_library import normalize_emote


def build_parser() -> argparse.ArgumentParser:
    """Create demo parser."""

    parser = argparse.ArgumentParser(description="Run a demo action on the Unitree G1 MuJoCo model.")
    parser.add_argument("--action", choices=["home", "wave_left_arm", "twist_waist", "arms_open"], default="wave_left_arm")
    parser.add_argument("--emote", choices=["惊讶", "求饶", "轻蔑"], help="Run one abstract emote instead of a raw demo action")
    parser.add_argument("--model", choices=MODEL_VARIANTS, default="default", help="Select the MJCF model variant")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--hold-steps", type=int, default=240, help="Extra sim steps to hold the final pose")
    return parser


def main() -> int:
    """Execute one demo action."""

    args = build_parser().parse_args()
    runtime = G1MujocoRuntime(model_name=args.model, gui=not args.headless)
    print(f"[loop.sim] model={args.model} path={runtime.model_path}")
    controller = G1MujocoController(runtime)
    try:
        runtime.launch()
        controller.move_to_home_pose(step_count=180)
        if args.emote:
            canonical = normalize_emote(args.emote)
            if canonical == "惊讶":
                controller.wave_left_arm(step_count=160)
                controller.arms_open(step_count=150)
            elif canonical == "求饶":
                controller.twist_waist(step_count=120)
                controller.arms_open(step_count=160)
            else:
                controller.twist_waist(step_count=120)
                controller.arms_open(step_count=140)
        elif args.action == "home":
            controller.arms_open(step_count=180)
            runtime.step(args.hold_steps)
            controller.move_to_home_pose(step_count=220)
        elif args.action == "wave_left_arm":
            controller.wave_left_arm(step_count=170)
        elif args.action == "twist_waist":
            controller.twist_waist(step_count=140)
        else:
            controller.arms_open(step_count=190)
        runtime.step(args.hold_steps)
        if args.headless:
            runtime.step(args.hold_steps)
        else:
            time.sleep(0.25)
            runtime.run_forever()
    finally:
        runtime.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

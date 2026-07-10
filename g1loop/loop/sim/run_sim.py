"""Standalone MuJoCo launcher for Unitree G1."""

from __future__ import annotations

import argparse

from .model import MODEL_VARIANTS, get_default_urdf_path
from .runtime import G1MujocoRuntime


def build_parser() -> argparse.ArgumentParser:
    """Create the simulation launcher parser."""

    parser = argparse.ArgumentParser(description="Launch Unitree G1 MuJoCo simulation.")
    parser.add_argument("--model", choices=MODEL_VARIANTS, default="default", help="Select the MJCF model variant")
    parser.add_argument("--headless", action="store_true", help="Run without opening a viewer")
    parser.add_argument("--steps", type=int, default=1000, help="Headless mode step count")
    return parser


def main() -> int:
    """Launch the standalone simulation runtime."""

    args = build_parser().parse_args()
    runtime = G1MujocoRuntime(model_name=args.model, gui=not args.headless)
    print(f"[loop.sim] model={args.model} path={runtime.model_path} urdf={get_default_urdf_path()}")
    try:
        if args.headless:
            runtime.step(args.steps)
        else:
            runtime.run_forever()
    finally:
        runtime.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

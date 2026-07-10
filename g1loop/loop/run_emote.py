"""Single-shot command-line entry point."""

from __future__ import annotations

import argparse

from .live_config import dump_default_config, load_live_config
from .service import EmoteService


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""

    parser = argparse.ArgumentParser(description="Run one abstract Unitree G1 emote.")
    parser.add_argument("--name", required=True, help="Emote name, e.g. 惊讶")
    parser.add_argument("--intensity", default="medium", choices=["low", "medium", "high"])
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--live", action="store_true", help="Use real Unitree G1 and LinkerHand adapters")
    parser.add_argument("--disable-hands", action="store_true", help="Skip real LinkerHand initialization in live mode")
    parser.add_argument("--config", help="Path to a JSON live config file")
    parser.add_argument("--write-example-config", help="Write a starter config JSON to the given path and exit")
    return parser


def main() -> int:
    """Execute one emote request."""

    args = build_parser().parse_args()
    if args.write_example_config:
        dump_default_config(args.write_example_config)
        print(f"wrote example config to {args.write_example_config}")
        return 0
    config = load_live_config(args.config)
    live = args.live or config.use_live
    enable_hands = (not args.disable_hands) and config.enable_hands
    service = (
        EmoteService.create_live(
            network_interface=config.network_interface,
            enable_hands=enable_hands,
            hand_joint=config.hand_joint,
            can=config.can,
            modbus=config.modbus,
        )
        if live
        else EmoteService()
    )
    try:
        result = service.perform_emote(
            name=args.name,
            intensity=args.intensity or config.intensity,
            repeat=args.repeat or config.repeat,
            dry_run=args.dry_run or (not live),
        )
    finally:
        service.shutdown()
    print(f"status={result.status}")
    print(f"trace={result.trace_path}")
    if result.error:
        print(f"error={result.error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

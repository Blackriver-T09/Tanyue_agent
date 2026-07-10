from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from .hyper3d import Hyper3DClient, Hyper3DConfig, Hyper3DError, Hyper3DSubmission


def _add_generation_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--quality",
        choices=["high", "medium", "low", "extra-low"],
        default="medium",
    )
    parser.add_argument("--mesh-mode", choices=["Quad", "Raw"], default="Quad")
    parser.add_argument(
        "--format",
        dest="geometry_file_format",
        choices=["glb", "usdz", "fbx", "obj", "stl"],
        default="glb",
    )
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=5.0)
    parser.add_argument("--max-polls", type=int, default=120)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Use Hyper3D Rodin from PunGen Agent.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("balance", help="Check remaining Hyper3D credits.")

    text_parser = subparsers.add_parser("text", help="Submit a Text-to-3D task.")
    text_parser.add_argument("prompt")
    _add_generation_options(text_parser)

    image_parser = subparsers.add_parser("image", help="Submit an Image-to-3D task.")
    image_parser.add_argument("image_path", type=Path)
    image_parser.add_argument("--prompt", default="")
    _add_generation_options(image_parser)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    client: Hyper3DClient | None = None,
    output: Callable[[str], None] = print,
) -> int:
    args = build_parser().parse_args(argv)
    try:
        active_client = client or Hyper3DClient(Hyper3DConfig.from_env())
        if args.command == "balance":
            output(json.dumps({"balance": active_client.check_balance()}))
            return 0

        options = {
            "quality": args.quality,
            "mesh_mode": args.mesh_mode,
            "geometry_file_format": args.geometry_file_format,
        }
        if args.command == "image":
            submission = active_client.submit_image(
                args.image_path,
                prompt=args.prompt,
                **options,
            )
        else:
            submission = active_client.submit_text(args.prompt, **options)
        payload = _submission_payload(active_client, submission, args)
        output(json.dumps(payload, ensure_ascii=False))
        return 0
    except (Hyper3DError, ValueError) as exc:
        output(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2


def _submission_payload(
    client: Hyper3DClient,
    submission: Hyper3DSubmission,
    args: argparse.Namespace,
) -> dict:
    payload = {"status": "submitted", **asdict(submission)}
    if not args.wait:
        return payload
    jobs = client.wait_for_completion(
        submission.subscription_key,
        poll_interval_s=args.poll_interval,
        max_polls=args.max_polls,
    )
    payload.update(
        {
            "status": "done",
            "jobs": jobs,
            "downloads": client.list_downloads(submission.task_uuid),
        }
    )
    return payload


if __name__ == "__main__":
    raise SystemExit(main())

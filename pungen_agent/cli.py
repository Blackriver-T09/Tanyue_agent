from __future__ import annotations

import argparse
import json
import sys

from .agent import PunGenAgent
from .azure_llm import azure_inference


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the PunGen Agent MVP.")
    parser.add_argument("text", help="User utterance or meme cue.")
    parser.add_argument("--scene", default="", help="Optional scene/context hint.")
    parser.add_argument(
        "--use-azure-llm",
        action="store_true",
        help="Attach live Azure OpenAI annotation using environment variables.",
    )
    args = parser.parse_args(argv)

    llm_inference = azure_inference if args.use_azure_llm else None
    agent = PunGenAgent.from_default_library(llm_inference=llm_inference)
    payload = agent.respond(args.text, scene=args.scene)
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

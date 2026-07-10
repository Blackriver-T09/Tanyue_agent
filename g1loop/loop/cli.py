"""Interactive CLI for local emote testing."""

from __future__ import annotations

from .service import EmoteService


def main() -> int:
    """Run a minimal REPL for local testing."""

    service = EmoteService()
    print("Loop CLI ready. Commands: 惊讶, 求饶, 轻蔑, list, quit")
    try:
        while True:
            raw = input("loop> ").strip()
            if not raw:
                continue
            if raw in {"quit", "exit"}:
                break
            if raw == "list":
                print(", ".join(service.list_emotes()))
                continue
            result = service.perform_emote(raw, dry_run=True)
            print(f"status={result.status} trace={result.trace_path}")
            if result.error:
                print(f"error={result.error}")
    finally:
        service.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

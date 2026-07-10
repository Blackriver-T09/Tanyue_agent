#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse


class EventHub:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._events: list[tuple[int, dict[str, Any]]] = []
        self._acknowledgements: dict[int, dict[str, Any]] = {}
        self._next_id = 1

    def publish(self, event: dict[str, Any]) -> int:
        with self._condition:
            event_id = self._next_id
            self._next_id += 1
            self._events.append((event_id, event))
            self._events = self._events[-500:]
            self._condition.notify_all()
            return event_id

    def acknowledge(self, event_id: int, acknowledgement: dict[str, Any]) -> bool:
        with self._condition:
            if not any(candidate_id == event_id for candidate_id, _ in self._events):
                return False
            self._acknowledgements[event_id] = dict(acknowledgement)
            self._condition.notify_all()
            return True

    def wait_for_ack(self, event_id: int, timeout: float = 3.0) -> dict[str, Any] | None:
        deadline = time.monotonic() + timeout
        with self._condition:
            while event_id not in self._acknowledgements:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._condition.wait(remaining)
            return dict(self._acknowledgements[event_id])

    def wait_after(self, last_id: int, timeout: float = 15.0) -> list[tuple[int, dict[str, Any]]]:
        deadline = time.monotonic() + timeout
        with self._condition:
            while True:
                pending = [(event_id, event) for event_id, event in self._events if event_id > last_id]
                if pending:
                    return pending
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return []
                self._condition.wait(remaining)

    def latest_id(self) -> int:
        with self._condition:
            if not self._events:
                return 0
            return self._events[-1][0]


class CharacterBridgeHandler(BaseHTTPRequestHandler):
    server_version = "TanyueCharacterBridge/1.0"

    def do_OPTIONS(self) -> None:
        self._send_headers(HTTPStatus.NO_CONTENT)

    def do_GET(self) -> None:
        if self.path == "/" or self.path.startswith("/health"):
            self._send_json(
                {
                    "ok": True,
                    "service": "tanyue-character-bridge",
                    "events": len(self.server.hub._events),  # type: ignore[attr-defined]
                }
            )
            return

        if self.path.startswith("/events"):
            self._stream_events()
            return

        self._send_json({"ok": False, "error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/ack":
            self._receive_ack()
            return
        if parsed.path != "/api/command":
            self._send_json({"ok": False, "error": "not found"}, status=HTTPStatus.NOT_FOUND)
            return

        try:
            payload = self._read_json()
            if isinstance(payload, list):
                payload = {"type": "batch", "commands": payload}
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object or array")
            if "type" not in payload and "action" not in payload:
                raise ValueError("command must contain type or action")
        except Exception as error:
            self._send_json({"ok": False, "error": str(error)}, status=HTTPStatus.BAD_REQUEST)
            return

        event_id = self.server.hub.publish(payload)  # type: ignore[attr-defined]
        should_wait = (parse_qs(parsed.query).get("wait") or [""])[0] in {"1", "true"}
        ack = self.server.hub.wait_for_ack(event_id) if should_wait else None  # type: ignore[attr-defined]
        self._send_json({"ok": True, "id": event_id, "command": payload, "ack": ack})

    def _receive_ack(self) -> None:
        try:
            payload = self._read_json()
            event_id = int(payload.get("event_id"))
            acknowledgement = payload.get("ack")
            if not isinstance(acknowledgement, dict):
                raise ValueError("ack must be an object")
            accepted = self.server.hub.acknowledge(event_id, acknowledgement)  # type: ignore[attr-defined]
            if not accepted:
                self._send_json({"ok": False, "error": "unknown event_id"}, status=HTTPStatus.NOT_FOUND)
                return
            self._send_json({"ok": True, "event_id": event_id})
        except Exception as error:
            self._send_json({"ok": False, "error": str(error)}, status=HTTPStatus.BAD_REQUEST)

    def log_message(self, format: str, *args: Any) -> None:
        if getattr(self.server, "quiet", False):  # type: ignore[attr-defined]
            return
        super().log_message(format, *args)

    def _stream_events(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        last_id = self.server.hub.latest_id()  # type: ignore[attr-defined]
        try:
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                pending = self.server.hub.wait_after(last_id)  # type: ignore[attr-defined]
                if not pending:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                for event_id, event in pending:
                    last_id = event_id
                    data = json.dumps(event, ensure_ascii=False)
                    self.wfile.write(f"id: {event_id}\n".encode("utf-8"))
                    self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return

    def _read_json(self) -> Any:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length)
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send_headers(status, content_type="application/json; charset=utf-8", content_length=len(body))
        self.wfile.write(body)

    def _send_headers(
        self,
        status: HTTPStatus,
        *,
        content_type: str | None = None,
        content_length: int | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        if content_type:
            self.send_header("Content-Type", content_type)
        if content_length is not None:
            self.send_header("Content-Length", str(content_length))
        self.end_headers()


class CharacterBridgeServer(ThreadingHTTPServer):
    hub: EventHub
    quiet: bool

    def handle_error(self, request: Any, client_address: Any) -> None:
        error_type, _, _ = sys.exc_info()
        if error_type in {BrokenPipeError, ConnectionResetError}:
            return
        if self.quiet:
            return
        super().handle_error(request, client_address)


def main() -> int:
    parser = argparse.ArgumentParser(description="Tanyue browser character bridge")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8893)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    server = CharacterBridgeServer((args.host, args.port), CharacterBridgeHandler)
    server.hub = EventHub()  # type: ignore[attr-defined]
    server.quiet = args.quiet  # type: ignore[attr-defined]
    print(f"character_bridge=http://{args.host}:{args.port}")
    print("events=/events api=/api/command health=/health")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\ncharacter_bridge stopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

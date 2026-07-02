from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from typing import Any, Iterator
from urllib import error, request


DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


@dataclass(frozen=True)
class QwenFlashConfig:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = "qwen3.6-flash"
    timeout: float = 120.0
    temperature: float = 0.7
    top_p: float = 0.8
    max_tokens: int | None = None


class QwenFlashClient:
    def __init__(self, config: QwenFlashConfig) -> None:
        self.config = config

    def stream_chat(self, messages: list[dict[str, Any]]) -> Iterator[tuple[str, dict[str, Any]]]:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "stream": True,
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
        }
        if self.config.max_tokens is not None:
            payload["max_tokens"] = self.config.max_tokens

        response = self._request(payload)
        try:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                if line.startswith(":") or line.startswith("event:"):
                    continue
                if line.startswith("data:"):
                    line = line[5:].strip()
                if line == "[DONE]":
                    break
                if not line.startswith("{"):
                    continue

                event = self._parse_event(line)
                delta = self._extract_delta(event)
                if delta:
                    yield delta, event
        finally:
            response.close()

    def chat(self, messages: list[dict[str, Any]]) -> str:
        text = []
        for delta, _event in self.stream_chat(messages):
            text.append(delta)
        return "".join(text).strip()

    def _request(self, payload: dict[str, Any]):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        target = request.Request(
            self._url("/chat/completions"),
            data=data,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        opener = request.build_opener(request.ProxyHandler({}), request.HTTPSHandler(context=ssl.create_default_context()))
        try:
            return opener.open(target, timeout=self.config.timeout)
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Qwen Flash request failed: HTTP {exc.code}: {detail}") from exc
        except (error.URLError, OSError, ssl.SSLError) as exc:
            raise RuntimeError(
                f"Could not connect to Qwen Flash API at {self.config.base_url}. "
                "Check network access and the API key in Config.py."
            ) from exc

    def _parse_event(self, line: str) -> dict[str, Any]:
        try:
            return json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid streaming response chunk: {line}") from exc

    def _extract_delta(self, event: dict[str, Any]) -> str:
        choices = event.get("choices") or []
        if not choices:
            return ""

        choice = choices[0] or {}
        delta = choice.get("delta") or {}
        if isinstance(delta, dict):
            content = delta.get("content")
            if content:
                return str(content)

        message = choice.get("message") or {}
        if isinstance(message, dict):
            content = message.get("content")
            if content:
                return str(content)
        return ""

    def _url(self, path: str) -> str:
        return self.config.base_url.rstrip("/") + path

from __future__ import annotations

import http.client
import json
import ssl
from dataclasses import dataclass
from typing import Iterator
from urllib import error, request as urllib_request
from urllib.parse import urlparse


DEFAULT_API_BASE = "https://frp-run.com:56330"
SAMPLE_RATE = 24000
CHANNELS = 1
SAMPLE_WIDTH = 2


@dataclass(frozen=True)
class RemoteTTSConfig:
    api_base: str = DEFAULT_API_BASE
    timeout: float = 120.0
    chunk_size: int = 8192
    use_env_proxy: bool = False
    resolve_ip: str | None = "183.131.59.150"


@dataclass(frozen=True)
class TTSRequest:
    text: str
    voice_id: str = "default"
    emotion: str = ""
    emotion_strength: str = "strong"
    mode: str = "auto"
    speed: float = 1.0
    instruct_text: str | None = None


class RemoteTTSClient:
    """Copied from /voice and kept local for robot playback work."""

    def __init__(self, config: RemoteTTSConfig | None = None) -> None:
        self.config = config or RemoteTTSConfig()

    def health(self) -> dict:
        response = self._request("GET", "/health", timeout=15)
        try:
            return json.loads(response.read().decode("utf-8"))
        finally:
            response.close()

    def stream_pcm(self, req: TTSRequest) -> Iterator[bytes]:
        body = json.dumps(self._payload(req), ensure_ascii=False).encode("utf-8")
        try:
            response = self._request(
                "POST",
                "/tts/stream",
                body=body,
                headers={"Content-Type": "application/json"},
                timeout=self.config.timeout,
            )
            try:
                while True:
                    chunk = response.read(self.config.chunk_size)
                    if not chunk:
                        break
                    yield chunk
            finally:
                response.close()
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"TTS request failed: HTTP {exc.code}: {detail}") from exc
        except (error.URLError, OSError, ssl.SSLError, http.client.HTTPException) as exc:
            raise RuntimeError(
                f"Could not connect to TTS API {self.config.api_base}. "
                "Check DNS/network access, or test the health endpoint."
            ) from exc

    def _payload(self, req: TTSRequest) -> dict:
        text = req.text.strip()
        if not text:
            raise ValueError("text must not be empty")
        resolved_mode = resolve_mode(req.mode, req.emotion, req.instruct_text)
        payload = {
            "text": text,
            "voice_id": req.voice_id,
            "mode": resolved_mode,
            "speed": req.speed,
        }
        if resolved_mode == "instruct2":
            payload["instruct_text"] = req.instruct_text or emotion_to_instruct(
                req.emotion,
                req.emotion_strength,
            )
        return payload

    def _url(self, path: str) -> str:
        return self.config.api_base.rstrip("/") + path

    def _ssl_context(self):
        if self.config.api_base.startswith("https://"):
            return ssl._create_unverified_context()
        return None

    def _request(
        self,
        method: str,
        path: str,
        body: bytes | None = None,
        headers: dict | None = None,
        timeout: float = 120,
    ):
        try:
            return self._urllib_request(method, path, body, headers, timeout)
        except (error.URLError, OSError, ssl.SSLError):
            if not self.config.resolve_ip:
                raise
            return self._direct_ip_request(method, path, body, headers, timeout)

    def _urllib_request(
        self,
        method: str,
        path: str,
        body: bytes | None,
        headers: dict | None,
        timeout: float,
    ):
        target = urllib_request.Request(
            self._url(path),
            data=body,
            headers=headers or {},
            method=method,
        )
        handlers = []
        if self.config.api_base.startswith("https://"):
            handlers.append(urllib_request.HTTPSHandler(context=self._ssl_context()))
        if not self.config.use_env_proxy:
            handlers.append(urllib_request.ProxyHandler({}))
        opener = urllib_request.build_opener(*handlers)
        return opener.open(target, timeout=timeout)

    def _direct_ip_request(
        self,
        method: str,
        path: str,
        body: bytes | None,
        headers: dict | None,
        timeout: float,
    ):
        parsed = urlparse(self.config.api_base)
        if parsed.scheme != "https":
            raise RuntimeError("--resolve-ip fallback only supports https API URLs")
        host = parsed.hostname or "frp-run.com"
        port = parsed.port or 443
        conn = _SNIHTTPSConnection(
            connect_host=self.config.resolve_ip,
            server_hostname=host,
            port=port,
            timeout=timeout,
            context=self._ssl_context(),
        )
        request_headers = {"Host": f"{host}:{port}", **(headers or {})}
        conn.request(method, path, body=body, headers=request_headers)
        response = conn.getresponse()
        if response.status >= 400:
            detail = response.read().decode("utf-8", errors="replace")
            response.close()
            raise RuntimeError(f"TTS request failed: HTTP {response.status}: {detail}")
        return response


class _SNIHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, connect_host: str | None, server_hostname: str, *args, **kwargs) -> None:
        self._connect_host = connect_host
        self._server_hostname = server_hostname
        super().__init__(server_hostname, *args, **kwargs)

    def connect(self) -> None:
        connect_host = self._connect_host or self.host
        sock = self._create_connection((connect_host, self.port), self.timeout, self.source_address)
        self.sock = self._context.wrap_socket(sock, server_hostname=self._server_hostname)


def emotion_to_instruct(emotion: str, strength: str = "strong") -> str:
    tags = normalize_emotion_tags(emotion, strength)
    if not tags:
        tags = ["自然", "亲近", "轻柔"]
    return " / ".join(tags) + "<|endofprompt|>"


def normalize_emotion_tags(emotion: str, strength: str = "strong") -> list[str]:
    raw = emotion.strip()
    if not raw:
        return []
    for sep in ["，", "、", ",", ";", "；", "/", "|"]:
        raw = raw.replace(sep, " ")
    tags = [tag.strip() for tag in raw.split() if tag.strip()]
    enhancers_by_strength = {
        "light": ["亲近"],
        "strong": ["亲近", "起伏", "轻声"],
        "max": ["亲近", "起伏", "轻声", "停顿", "尾音"],
    }
    enhancers = enhancers_by_strength.get(strength, enhancers_by_strength["strong"])
    for tag in enhancers:
        if tag not in tags:
            tags.append(tag)
    return tags[:8]


def resolve_mode(mode: str, emotion: str = "", instruct_text: str | None = None) -> str:
    if mode == "auto":
        return "instruct2" if emotion.strip() or instruct_text else "cross_lingual"
    return mode

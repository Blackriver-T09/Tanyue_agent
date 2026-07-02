from __future__ import annotations

import json
import http.client
import ssl
import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse
from urllib import error, request as urllib_request


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
    emotion: str = ""
    emotion_strength: str = "strong"
    mode: str = "auto"
    speed: float = 1.0
    instruct_text: str | None = None


class RemoteTTSClient:
    def __init__(self, config: RemoteTTSConfig | None = None) -> None:
        self.config = config or RemoteTTSConfig()

    def health(self) -> dict:
        response = self._request("GET", "/health", timeout=15)
        try:
            return json.loads(response.read().decode("utf-8"))
        finally:
            response.close()

    def stream_pcm(self, req: TTSRequest) -> Iterator[bytes]:
        payload = self._payload(req)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
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
                "The client disables environment proxies and, by default, falls back to the known Sakura FRP IP "
                f"{self.config.resolve_ip}. Check DNS/network access, or test: "
                "curl -k --resolve frp-run.com:56330:183.131.59.150 https://frp-run.com:56330/health"
            ) from exc

    def save_wav(self, req: TTSRequest, output: str | Path, compatible: bool = False) -> Path:
        output_path = Path(output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        raw_path = output_path
        if compatible:
            raw_path = output_path.with_suffix(output_path.suffix + ".raw24k.wav")

        with wave.open(str(raw_path), "wb") as wav:
            wav.setnchannels(CHANNELS)
            wav.setsampwidth(SAMPLE_WIDTH)
            wav.setframerate(SAMPLE_RATE)
            for chunk in self.stream_pcm(req):
                wav.writeframes(chunk)

        if compatible:
            self._convert_to_compatible_wav(raw_path, output_path)
            raw_path.unlink(missing_ok=True)
        return output_path

    def _payload(self, req: TTSRequest) -> dict:
        text = req.text.strip()
        if not text:
            raise ValueError("text must not be empty")
        resolved_mode = resolve_mode(req.mode, req.emotion, req.instruct_text)
        instruct_text = req.instruct_text or emotion_to_instruct(req.emotion, req.emotion_strength)
        payload = {
            "text": text,
            "mode": resolved_mode,
            "speed": req.speed,
        }
        if resolved_mode == "instruct2":
            payload["instruct_text"] = instruct_text
        return payload

    def _url(self, path: str) -> str:
        return self.config.api_base.rstrip("/") + path

    def _ssl_context(self):
        if self.config.api_base.startswith("https://"):
            return ssl._create_unverified_context()
        return None

    def _request(self, method: str, path: str, body: bytes | None = None, headers: dict | None = None, timeout: float = 120):
        try:
            return self._urllib_request(method, path, body, headers, timeout)
        except (error.URLError, OSError, ssl.SSLError):
            if not self.config.resolve_ip:
                raise
            return self._direct_ip_request(method, path, body, headers, timeout)

    def _urllib_request(self, method: str, path: str, body: bytes | None, headers: dict | None, timeout: float):
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

    def _direct_ip_request(self, method: str, path: str, body: bytes | None, headers: dict | None, timeout: float):
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

    def _convert_to_compatible_wav(self, source: Path, output: Path) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            output.unlink(missing_ok=True)
            if output.suffix.lower() == ".m4a":
                subprocess.run(
                    [
                        ffmpeg,
                        "-y",
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-i",
                        str(source),
                        "-ar",
                        "44100",
                        "-ac",
                        "1",
                        "-c:a",
                        "aac",
                        "-b:a",
                        "128k",
                        str(output),
                    ],
                    check=True,
                )
                return

            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(source),
                    "-map_metadata",
                    "-1",
                    "-fflags",
                    "+bitexact",
                    "-flags",
                    "bitexact",
                    "-bitexact",
                    "-ar",
                    "44100",
                    "-ac",
                    "1",
                    "-c:a",
                    "pcm_s16le",
                    str(output),
                ],
                check=True,
            )
            return

        afconvert = shutil.which("afconvert")
        if afconvert:
            output.unlink(missing_ok=True)
            subprocess.run(
                [afconvert, "-f", "WAVE", "-d", "LEI16@44100", str(source), str(output)],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return

        # Non-macOS fallback: keep the valid 24 kHz PCM WAV if afconvert is unavailable.
        source.replace(output)


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

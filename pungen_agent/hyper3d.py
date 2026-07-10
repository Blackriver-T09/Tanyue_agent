from __future__ import annotations

import json
import mimetypes
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "https://api.hyper3d.com/api/v2"
VALID_QUALITIES = {"high", "medium", "low", "extra-low"}
VALID_FORMATS = {"glb", "usdz", "fbx", "obj", "stl"}
VALID_MESH_MODES = {"Quad", "Raw"}


class Hyper3DError(RuntimeError):
    pass


@dataclass(frozen=True)
class Hyper3DConfig:
    api_key: str = field(repr=False)
    base_url: str = DEFAULT_BASE_URL
    timeout_s: float = 30.0

    def __post_init__(self) -> None:
        if not self.api_key.strip():
            raise ValueError("HYPER3D_API_KEY must not be empty.")
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        env_file: str | Path | bool | None = None,
    ) -> "Hyper3DConfig":
        values = dict(env if env is not None else os.environ)
        if env_file is not False:
            path = Path(env_file) if env_file is not None else Path.cwd() / ".env.local"
            for key, value in _read_env_file(path).items():
                values.setdefault(key, value)
        api_key = values.get("HYPER3D_API_KEY") or values.get("RODIN_API_KEY")
        if not api_key:
            raise ValueError("HYPER3D_API_KEY or RODIN_API_KEY is required.")
        base_url = values.get("HYPER3D_API_BASE", DEFAULT_BASE_URL)
        timeout_s = float(values.get("HYPER3D_TIMEOUT_S", "30"))
        return cls(api_key=api_key, base_url=base_url, timeout_s=timeout_s)


@dataclass(frozen=True)
class Hyper3DSubmission:
    task_uuid: str
    subscription_key: str
    message: str = ""


Transport = Callable[..., dict[str, Any]]
BinaryFetcher = Callable[[str, float], bytes]


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        if key:
            values[key] = value
    return values


class Hyper3DClient:
    def __init__(
        self,
        config: Hyper3DConfig,
        transport: Transport | None = None,
        binary_fetcher: BinaryFetcher | None = None,
    ):
        self.config = config
        self.transport = transport or _urllib_transport
        self.binary_fetcher = binary_fetcher or _download_binary

    def check_balance(self) -> int:
        payload = self._request("GET", "/check_balance")
        try:
            return int(payload["balance"])
        except (KeyError, TypeError, ValueError) as exc:
            raise Hyper3DError("Hyper3D balance response did not include a balance.") from exc

    def submit_image(
        self,
        image_path: str | Path,
        *,
        prompt: str = "",
        quality: str = "medium",
        mesh_mode: str = "Quad",
        geometry_file_format: str = "glb",
        material: str = "PBR",
    ) -> Hyper3DSubmission:
        path = Path(image_path)
        if not path.is_file():
            raise Hyper3DError(f"Image file does not exist: {path}")
        fields = self._generation_fields(
            prompt=prompt,
            quality=quality,
            mesh_mode=mesh_mode,
            geometry_file_format=geometry_file_format,
            material=material,
        )
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        payload = self._request(
            "POST",
            "/rodin",
            form_fields=fields,
            files=[("images", path.name, path.read_bytes(), content_type)],
        )
        return _parse_submission(payload)

    def submit_text(
        self,
        prompt: str,
        *,
        quality: str = "medium",
        mesh_mode: str = "Quad",
        geometry_file_format: str = "glb",
        material: str = "PBR",
    ) -> Hyper3DSubmission:
        if not isinstance(prompt, str) or not prompt.strip():
            raise Hyper3DError("Text-to-3D requires a non-empty prompt.")
        fields = self._generation_fields(
            prompt=prompt.strip(),
            quality=quality,
            mesh_mode=mesh_mode,
            geometry_file_format=geometry_file_format,
            material=material,
        )
        payload = self._request("POST", "/rodin", form_fields=fields)
        return _parse_submission(payload)

    def check_status(self, subscription_key: str) -> list[dict[str, Any]]:
        if not subscription_key:
            raise Hyper3DError("subscription_key must not be empty.")
        payload = self._request(
            "POST",
            "/status",
            json_body={"subscription_key": subscription_key},
        )
        jobs = payload.get("jobs")
        if not isinstance(jobs, list):
            raise Hyper3DError("Hyper3D status response did not include a jobs list.")
        return jobs

    def wait_for_completion(
        self,
        subscription_key: str,
        *,
        poll_interval_s: float = 5.0,
        max_polls: int = 120,
    ) -> list[dict[str, Any]]:
        if max_polls < 1:
            raise Hyper3DError("max_polls must be at least 1.")
        for poll_index in range(max_polls):
            jobs = self.check_status(subscription_key)
            if jobs and all(job.get("status") in {"Done", "Failed"} for job in jobs):
                failed = [job for job in jobs if job.get("status") == "Failed"]
                if failed:
                    failed_ids = ", ".join(str(job.get("uuid", "unknown")) for job in failed)
                    raise Hyper3DError(f"Hyper3D generation failed for jobs: {failed_ids}")
                return jobs
            if poll_index + 1 < max_polls and poll_interval_s > 0:
                time.sleep(poll_interval_s)
        raise Hyper3DError("Hyper3D generation did not finish before max_polls.")

    def list_downloads(self, task_uuid: str) -> list[dict[str, Any]]:
        if not task_uuid:
            raise Hyper3DError("task_uuid must not be empty.")
        payload = self._request(
            "POST",
            "/download",
            json_body={"task_uuid": task_uuid},
        )
        items = payload.get("list")
        if not isinstance(items, list):
            raise Hyper3DError("Hyper3D download response did not include a list.")
        return items

    def download_files(
        self,
        task_uuid: str,
        output_dir: str | Path,
    ) -> list[Path]:
        destination = Path(output_dir)
        destination.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for item in self.list_downloads(task_uuid):
            name = Path(str(item.get("name") or "")).name
            url = item.get("url")
            if not name or not isinstance(url, str) or not url:
                raise Hyper3DError("Hyper3D download item is missing name or url.")
            path = destination / name
            path.write_bytes(self.binary_fetcher(url, self.config.timeout_s))
            paths.append(path)
        return paths

    def _generation_fields(
        self,
        *,
        prompt: str,
        quality: str,
        mesh_mode: str,
        geometry_file_format: str,
        material: str,
    ) -> dict[str, str]:
        if quality not in VALID_QUALITIES:
            raise Hyper3DError(f"Unsupported quality: {quality}")
        if mesh_mode not in VALID_MESH_MODES:
            raise Hyper3DError(f"Unsupported mesh_mode: {mesh_mode}")
        if geometry_file_format not in VALID_FORMATS:
            raise Hyper3DError(
                f"Unsupported geometry_file_format: {geometry_file_format}"
            )
        fields = {
            "tier": "Gen-2",
            "quality": quality,
            "mesh_mode": mesh_mode,
            "geometry_file_format": geometry_file_format,
            "material": material,
        }
        if prompt.strip():
            fields["prompt"] = prompt.strip()
        return fields

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        form_fields: dict[str, str] | None = None,
        files: list[tuple[str, str, bytes, str]] | None = None,
    ) -> dict[str, Any]:
        payload = self.transport(
            method=method,
            url=f"{self.config.base_url}{path}",
            headers={"Authorization": f"Bearer {self.config.api_key}"},
            json_body=json_body,
            form_fields=form_fields,
            files=files,
            timeout_s=self.config.timeout_s,
        )
        error = payload.get("error")
        if error:
            message = payload.get("message") or "No details provided."
            raise Hyper3DError(f"Hyper3D API error {error}: {message}")
        return payload


def _parse_submission(payload: dict[str, Any]) -> Hyper3DSubmission:
    jobs = payload.get("jobs") or {}
    task_uuid = payload.get("uuid")
    subscription_key = jobs.get("subscription_key") if isinstance(jobs, dict) else None
    if not task_uuid or not subscription_key:
        raise Hyper3DError(
            "Hyper3D submission response did not include uuid and subscription_key."
        )
    return Hyper3DSubmission(
        task_uuid=str(task_uuid),
        subscription_key=str(subscription_key),
        message=str(payload.get("message") or ""),
    )


def _urllib_transport(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    json_body: dict[str, Any] | None,
    form_fields: dict[str, str] | None,
    files: list[tuple[str, str, bytes, str]] | None,
    timeout_s: float,
) -> dict[str, Any]:
    request_headers = dict(headers)
    body: bytes | None = None
    if form_fields is not None or files is not None:
        body, content_type = _encode_multipart(form_fields or {}, files or [])
        request_headers["Content-Type"] = content_type
    elif json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"

    request = Request(url, data=body, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=timeout_s) as response:
            raw = response.read()
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise Hyper3DError(f"Hyper3D HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise Hyper3DError(f"Could not reach Hyper3D API: {exc.reason}") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Hyper3DError("Hyper3D API returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise Hyper3DError("Hyper3D API returned a non-object JSON response.")
    return payload


def _download_binary(url: str, timeout_s: float) -> bytes:
    try:
        with urlopen(url, timeout=timeout_s) as response:
            return response.read()
    except HTTPError as exc:
        raise Hyper3DError(f"Hyper3D asset download returned HTTP {exc.code}.") from exc
    except URLError as exc:
        raise Hyper3DError(f"Could not download Hyper3D asset: {exc.reason}") from exc


def _encode_multipart(
    fields: dict[str, str],
    files: list[tuple[str, str, bytes, str]],
) -> tuple[bytes, str]:
    boundary = f"----pungen-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    for field_name, filename, content, content_type in files:
        safe_filename = Path(filename).name.replace('"', "")
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="{field_name}"; '
                    f'filename="{safe_filename}"\r\n'
                ).encode(),
                f"Content-Type: {content_type}\r\n\r\n".encode(),
                content,
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"

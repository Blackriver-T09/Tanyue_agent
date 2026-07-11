from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
import queue as sync_queue
import random
import threading
from dataclasses import dataclass, field
from typing import AsyncIterable, AsyncIterator, Iterable, Iterator


LOGGER = logging.getLogger("tanyue.aliyun_tts")
SAFE_MODEL = "cosyvoice-v3.5-plus"
SAFE_VOICE = "longxiaochun"
LEGACY_INVALID_MODEL = "cosyvoice-v3-flash"
LEGACY_INVALID_VOICE = "longanyang"
DEFAULT_CLONE_PREFIX = "tanyue"
DEFAULT_REFERENCE_AUDIO = "voice/reference.wav"
DEFAULT_CLONE_CACHE = "voice/.cosyvoice_voice_id"
DEFAULT_VOICE_REGISTRY = "voice/cosyvoice_voices.json"


@dataclass(frozen=True)
class AliyunCosyVoiceConfig:
    api_key: str
    workspace_id: str | None = None
    api_host: str | None = None
    region: str = "beijing"
    model: str = "cosyvoice-v3.5-plus"
    voice: str = "longxiaochun"
    sample_rate: int = 24000
    volume: int = 50
    speech_rate: float = 1.0
    pitch_rate: float = 1.0
    instruction: str | None = None
    language_hints: list[str] = field(default_factory=lambda: ["zh"])
    style_params_enabled: bool = False
    clone_enabled: bool = False
    reference_audio_path: Path | None = None
    cloned_voice_cache_path: Path | None = None
    clone_prefix: str = DEFAULT_CLONE_PREFIX
    clone_target_model: str | None = None
    clone_audio_url: str | None = None
    clone_max_prompt_audio_length: float | None = 20.0
    voice_registry_path: Path | None = None
    random_voice_enabled: bool = False
    voice_pool: tuple[str, ...] = ()

    @property
    def websocket_url(self) -> str | None:
        if self.api_host:
            return f"wss://{self.api_host}/api-ws/v1/inference"
        if not self.workspace_id:
            return None
        if self.region == "singapore":
            return f"wss://{self.workspace_id}.ap-southeast-1.maas.aliyuncs.com/api-ws/v1/inference"
        return f"wss://{self.workspace_id}.cn-beijing.maas.aliyuncs.com/api-ws/v1/inference"

    @property
    def http_base_url(self) -> str | None:
        if self.api_host:
            return f"https://{self.api_host}/api/v1"
        if not self.workspace_id:
            return None
        if self.region == "singapore":
            return f"https://{self.workspace_id}.ap-southeast-1.maas.aliyuncs.com/api/v1"
        return f"https://{self.workspace_id}.cn-beijing.maas.aliyuncs.com/api/v1"


class AliyunCosyVoiceTTS:
    sample_rate = 24000
    num_channels = 1

    def __init__(self, config: AliyunCosyVoiceConfig) -> None:
        self.config = config
        self.sample_rate = config.sample_rate
        self._bad_voice_ids: set[str] = set()
        self._voice_key_by_id: dict[str, str] = {}
        self._selected_voice_id: str | None = None
        self._selected_voice_key: str | None = None
        self._refresh_voice_lookup()

    def ensure_cloned_voice(self, *, force: bool = False) -> str:
        voice_ids = ensure_cosyvoice_voices(self.config, force=force)
        voice_id = voice_ids[0]
        self.config = dataclass_replace(self.config, voice=voice_id, voice_pool=tuple(voice_ids))
        self._refresh_voice_lookup(force=True)
        if len(voice_ids) > 1:
            LOGGER.info("Using Aliyun cloned voice pool: %s", ", ".join(voice_ids))
        return voice_id

    async def synthesize_frames(self, text: AsyncIterable[str]) -> AsyncIterator["rtc.AudioFrame"]:
        from livekit import rtc

        chunks: list[str] = []
        async for chunk in text:
            if chunk and chunk.strip():
                chunks.append(chunk.strip())
        if not chunks:
            return

        candidates = self._voice_candidates()
        last_error: BaseException | None = None
        for voice, voice_key in candidates:
            self._selected_voice_id = voice
            self._selected_voice_key = voice_key
            try:
                async for frame in self._synthesize_frames_once(rtc, chunks, voice):
                    yield frame
                return
            except AliyunCosyVoiceRetryableError as exc:
                self._bad_voice_ids.add(voice)
                last_error = exc
                LOGGER.warning(
                    "Aliyun CosyVoice voice failed before audio: voice=%s error=%s, retrying",
                    voice,
                    exc,
                )
                continue
            except BaseException as exc:  # noqa: BLE001
                last_error = exc
                break

        if last_error:
            raise last_error

    def stream_pcm_bytes(
        self,
        text: str | Iterable[str],
        *,
        voice_id: str | None = None,
        emotion: str = "",
        emotion_strength: str = "strong",
        mode: str = "auto",
        speed: float | None = None,
        instruct_text: str | None = None,
    ) -> Iterator[bytes]:
        chunks: list[str]
        if isinstance(text, str):
            chunks = [text.strip()] if text.strip() else []
        else:
            chunks = [chunk.strip() for chunk in text if chunk and str(chunk).strip()]
        if not chunks:
            return

        if voice_id:
            self._selected_voice_id = voice_id
            self._selected_voice_key = self._voice_key_for_id(voice_id)
            yield from self._stream_pcm_bytes(
                chunks,
                voice_id,
                emotion=emotion,
                emotion_strength=emotion_strength,
                mode=mode,
                speed=speed,
                instruct_text=instruct_text,
            )
            return

        candidates = self._voice_candidates()
        last_error: BaseException | None = None
        for voice, voice_key in candidates:
            self._selected_voice_id = voice
            self._selected_voice_key = voice_key
            try:
                yield from self._stream_pcm_bytes(
                    chunks,
                    voice,
                    emotion=emotion,
                    emotion_strength=emotion_strength,
                    mode=mode,
                    speed=speed,
                    instruct_text=instruct_text,
                )
                return
            except AliyunCosyVoiceRetryableError as exc:
                self._bad_voice_ids.add(voice)
                last_error = exc
                LOGGER.warning(
                    "Aliyun CosyVoice voice failed before audio: voice=%s error=%s, retrying",
                    voice,
                    exc,
                )
                continue
            except BaseException as exc:  # noqa: BLE001
                last_error = exc
                break

        if last_error:
            raise last_error

    async def _synthesize_frames_once(
        self,
        rtc,
        chunks: list[str],
        voice: str,
        *,
        emotion: str = "",
        emotion_strength: str = "strong",
        mode: str = "auto",
        speed: float | None = None,
        instruct_text: str | None = None,
    ) -> AsyncIterator["rtc.AudioFrame"]:
        async for pcm in self._stream_pcm_bytes_async(
            chunks,
            voice,
            emotion=emotion,
            emotion_strength=emotion_strength,
            mode=mode,
            speed=speed,
            instruct_text=instruct_text,
        ):
            yield self._pcm_to_frame(rtc, pcm)

    async def _stream_pcm_bytes_async(
        self,
        chunks: list[str],
        voice: str,
        *,
        emotion: str = "",
        emotion_strength: str = "strong",
        mode: str = "auto",
        speed: float | None = None,
        instruct_text: str | None = None,
    ) -> AsyncIterator[bytes]:
        audio_queue: asyncio.Queue[bytes | BaseException | None] = asyncio.Queue()
        text_queue: sync_queue.Queue[str | None] = sync_queue.Queue()
        loop = asyncio.get_running_loop()

        def put_threadsafe(item: bytes | BaseException | None) -> None:
            loop.call_soon_threadsafe(audio_queue.put_nowait, item)

        def synthesize_worker() -> None:
            try:
                import dashscope
                from dashscope.audio.tts_v2 import AudioFormat, ResultCallback, SpeechSynthesizer

                dashscope.api_key = self.config.api_key
                if self.config.websocket_url:
                    dashscope.base_websocket_api_url = self.config.websocket_url

                class Callback(ResultCallback):
                    def on_data(self, data: bytes) -> None:
                        nonlocal first_audio
                        if first_audio:
                            LOGGER.info("Aliyun CosyVoice first audio chunk received")
                            first_audio = False
                        put_threadsafe(data)

                    def on_error(self, message: str) -> None:
                        if first_audio:
                            put_threadsafe(
                                AliyunCosyVoiceRetryableError(
                                    f"Aliyun CosyVoice TTS error before audio: {message}"
                                )
                            )
                        else:
                            put_threadsafe(RuntimeError(f"Aliyun CosyVoice TTS error: {message}"))

                    def on_complete(self) -> None:
                        put_threadsafe(None)

                kwargs = {
                    "model": self.config.model,
                    "voice": voice,
                    "format": AudioFormat.PCM_24000HZ_MONO_16BIT,
                    "volume": self.config.volume,
                    "speech_rate": speed or self.config.speech_rate,
                    "pitch_rate": self.config.pitch_rate,
                    "workspace": self.config.workspace_id,
                    "url": self.config.websocket_url,
                    "callback": Callback(),
                }
                if self.config.style_params_enabled or mode == "instruct2":
                    kwargs["instruction"] = instruct_text or self.config.instruction
                    kwargs["language_hints"] = self.config.language_hints or ["zh"]

                LOGGER.info(
                    "Aliyun CosyVoice stream opening: model=%s voice=%s url=%s",
                    self.config.model,
                    voice,
                    self.config.websocket_url or "dashscope-default",
                )
                synthesizer = SpeechSynthesizer(**kwargs)
                LOGGER.info("Aliyun CosyVoice stream ready")

                sent_text = False
                while True:
                    chunk = text_queue.get()
                    if chunk is None:
                        break
                    chunk = chunk.strip()
                    if chunk:
                        if not sent_text:
                            LOGGER.info("Aliyun CosyVoice first text chunk sent")
                            sent_text = True
                        synthesizer.streaming_call(chunk)
                if sent_text:
                    synthesizer.streaming_complete()
                else:
                    put_threadsafe(None)
            except BaseException as exc:  # noqa: BLE001
                if first_audio:
                    put_threadsafe(
                        AliyunCosyVoiceRetryableError(f"Aliyun CosyVoice TTS error before audio: {exc}")
                    )
                else:
                    put_threadsafe(exc)

        def feed_chunks() -> None:
            try:
                for chunk in chunks:
                    text_queue.put(chunk)
            except BaseException as exc:  # noqa: BLE001
                put_threadsafe(exc)
            finally:
                text_queue.put(None)

        first_audio = True
        worker = threading.Thread(target=synthesize_worker, daemon=True)
        worker.start()
        producer = threading.Thread(target=feed_chunks, daemon=True)
        producer.start()

        try:
            while True:
                item = await audio_queue.get()
                if item is None:
                    break
                if isinstance(item, BaseException):
                    raise item
                if first_audio:
                    first_audio = False
                yield item
        finally:
            if producer.is_alive():
                text_queue.put(None)
            producer.join(timeout=3)
            worker.join(timeout=3)

    def _stream_pcm_bytes(
        self,
        chunks: list[str],
        voice: str,
        *,
        emotion: str = "",
        emotion_strength: str = "strong",
        mode: str = "auto",
        speed: float | None = None,
        instruct_text: str | None = None,
    ) -> Iterator[bytes]:
        audio_queue: sync_queue.Queue[bytes | BaseException | None] = sync_queue.Queue()
        text_queue: sync_queue.Queue[str | None] = sync_queue.Queue()

        def put_threadsafe(item: bytes | BaseException | None) -> None:
            audio_queue.put(item)

        def synthesize_worker() -> None:
            try:
                import dashscope
                from dashscope.audio.tts_v2 import AudioFormat, ResultCallback, SpeechSynthesizer

                dashscope.api_key = self.config.api_key
                if self.config.websocket_url:
                    dashscope.base_websocket_api_url = self.config.websocket_url

                class Callback(ResultCallback):
                    def on_data(self, data: bytes) -> None:
                        nonlocal first_audio
                        if first_audio:
                            LOGGER.info("Aliyun CosyVoice first audio chunk received")
                            first_audio = False
                        put_threadsafe(data)

                    def on_error(self, message: str) -> None:
                        if first_audio:
                            put_threadsafe(
                                AliyunCosyVoiceRetryableError(
                                    f"Aliyun CosyVoice TTS error before audio: {message}"
                                )
                            )
                        else:
                            put_threadsafe(RuntimeError(f"Aliyun CosyVoice TTS error: {message}"))

                    def on_complete(self) -> None:
                        put_threadsafe(None)

                kwargs = {
                    "model": self.config.model,
                    "voice": voice,
                    "format": AudioFormat.PCM_24000HZ_MONO_16BIT,
                    "volume": self.config.volume,
                    "speech_rate": speed or self.config.speech_rate,
                    "pitch_rate": self.config.pitch_rate,
                    "workspace": self.config.workspace_id,
                    "url": self.config.websocket_url,
                    "callback": Callback(),
                }
                if self.config.style_params_enabled or mode == "instruct2":
                    kwargs["instruction"] = instruct_text or self.config.instruction
                    kwargs["language_hints"] = self.config.language_hints or ["zh"]

                LOGGER.info(
                    "Aliyun CosyVoice stream opening: model=%s voice=%s url=%s",
                    self.config.model,
                    voice,
                    self.config.websocket_url or "dashscope-default",
                )
                synthesizer = SpeechSynthesizer(**kwargs)
                LOGGER.info("Aliyun CosyVoice stream ready")

                sent_text = False
                while True:
                    chunk = text_queue.get()
                    if chunk is None:
                        break
                    chunk = chunk.strip()
                    if chunk:
                        if not sent_text:
                            LOGGER.info("Aliyun CosyVoice first text chunk sent")
                            sent_text = True
                        synthesizer.streaming_call(chunk)
                if sent_text:
                    synthesizer.streaming_complete()
                else:
                    put_threadsafe(None)
            except BaseException as exc:  # noqa: BLE001
                if first_audio:
                    put_threadsafe(
                        AliyunCosyVoiceRetryableError(f"Aliyun CosyVoice TTS error before audio: {exc}")
                    )
                else:
                    put_threadsafe(exc)

        def feed_chunks() -> None:
            try:
                for chunk in chunks:
                    text_queue.put(chunk)
            except BaseException as exc:  # noqa: BLE001
                put_threadsafe(exc)
            finally:
                text_queue.put(None)

        first_audio = True
        worker = threading.Thread(target=synthesize_worker, daemon=True)
        worker.start()
        producer = threading.Thread(target=feed_chunks, daemon=True)
        producer.start()

        try:
            while True:
                item = audio_queue.get()
                if item is None:
                    break
                if isinstance(item, BaseException):
                    raise item
                if first_audio:
                    first_audio = False
                yield item
        finally:
            if producer.is_alive():
                text_queue.put(None)
            producer.join(timeout=3)
            worker.join(timeout=3)

    def _pcm_to_frame(self, rtc, data: bytes):
        samples_per_channel = len(data) // 2
        return rtc.AudioFrame(
            data=bytearray(data),
            sample_rate=self.sample_rate,
            num_channels=self.num_channels,
            samples_per_channel=samples_per_channel,
        )

    def _refresh_voice_lookup(self, *, force: bool = False) -> None:
        self._voice_key_by_id = {}
        registry_path = self.config.voice_registry_path
        if registry_path and registry_path.exists():
            try:
                for item in load_voice_registry(registry_path):
                    voice_id = str(item.get("registered_voice_id") or "").strip()
                    key = str(item.get("key") or "").strip()
                    if voice_id and key:
                        self._voice_key_by_id[voice_id] = key
            except Exception as exc:  # noqa: BLE001
                LOGGER.debug("Could not refresh voice lookup: %s", exc)

    def _voice_key_for_id(self, voice_id: str) -> str | None:
        return self._voice_key_by_id.get(voice_id)

    def _voice_candidates(self) -> list[tuple[str, str | None]]:
        pool = [item for item in self.config.voice_pool if item and item not in self._bad_voice_ids]
        if self.config.voice and self.config.voice not in pool and self.config.voice not in self._bad_voice_ids:
            pool.append(self.config.voice)
        if SAFE_VOICE not in pool and SAFE_VOICE not in self._bad_voice_ids:
            pool.append(SAFE_VOICE)
        if not pool:
            pool = [self.config.voice or SAFE_VOICE]
        deduped: list[tuple[str, str | None]] = []
        seen: set[str] = set()
        for voice_id in pool:
            if voice_id in seen:
                continue
            seen.add(voice_id)
            deduped.append((voice_id, self._voice_key_for_id(voice_id)))
        if self.config.random_voice_enabled and len(pool) > 1:
            random.shuffle(deduped)
        return deduped

    @property
    def selected_voice_id(self) -> str | None:
        return self._selected_voice_id

    @property
    def selected_voice_key(self) -> str | None:
        return self._selected_voice_key


class AliyunCosyVoiceRetryableError(RuntimeError):
    pass


def config_from_env(api_key: str | None = None) -> AliyunCosyVoiceConfig:
    model = os.environ.get("TANYUE_COSYVOICE_MODEL", SAFE_MODEL)
    voice = os.environ.get("TANYUE_COSYVOICE_VOICE", SAFE_VOICE)
    if (
        model == LEGACY_INVALID_MODEL
        or voice == LEGACY_INVALID_VOICE
    ) and os.environ.get("TANYUE_COSYVOICE_ALLOW_LEGACY", "0") not in {"1", "true", "True"}:
        LOGGER.warning(
            "Ignoring legacy CosyVoice config model=%s voice=%s; using model=%s voice=%s",
            model,
            voice,
            SAFE_MODEL,
            SAFE_VOICE,
        )
        model = SAFE_MODEL
        voice = SAFE_VOICE

    instruction = os.environ.get("TANYUE_COSYVOICE_INSTRUCTION") or ""
    reference_audio = resolve_project_path(
        os.environ.get("TANYUE_COSYVOICE_REFERENCE_AUDIO", DEFAULT_REFERENCE_AUDIO)
    )
    clone_enabled = env_bool(
        "TANYUE_COSYVOICE_CLONE_ENABLED",
        reference_audio.exists(),
    )

    return AliyunCosyVoiceConfig(
        api_key=api_key or os.environ["DASHSCOPE_API_KEY"],
        workspace_id=os.environ.get("DASHSCOPE_WORKSPACE_ID"),
        api_host=os.environ.get("DASHSCOPE_API_HOST") or os.environ.get("API_HOST"),
        region=os.environ.get("DASHSCOPE_REGION", "beijing"),
        model=model,
        voice=voice,
        instruction=instruction,
        style_params_enabled=env_bool("TANYUE_COSYVOICE_ENABLE_STYLE_PARAMS", False),
        clone_enabled=clone_enabled,
        reference_audio_path=reference_audio,
        cloned_voice_cache_path=resolve_project_path(
            os.environ.get("TANYUE_COSYVOICE_CLONE_CACHE", DEFAULT_CLONE_CACHE)
        ),
        clone_prefix=os.environ.get("TANYUE_COSYVOICE_CLONE_PREFIX", DEFAULT_CLONE_PREFIX),
        clone_target_model=os.environ.get("TANYUE_COSYVOICE_CLONE_TARGET_MODEL", model),
        clone_audio_url=os.environ.get("TANYUE_COSYVOICE_CLONE_AUDIO_URL"),
        clone_max_prompt_audio_length=float(os.environ.get("TANYUE_COSYVOICE_CLONE_MAX_SECONDS", "20")),
        voice_registry_path=resolve_project_path(
            os.environ.get("TANYUE_COSYVOICE_VOICE_REGISTRY", DEFAULT_VOICE_REGISTRY)
        ),
        random_voice_enabled=env_bool("TANYUE_COSYVOICE_RANDOM_VOICE_ENABLED", True),
    )


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value in {"1", "true", "True", "yes", "YES", "on", "ON"}


def dataclass_replace(config: AliyunCosyVoiceConfig, **changes) -> AliyunCosyVoiceConfig:
    from dataclasses import replace

    return replace(config, **changes)


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_project_path(value: str | os.PathLike[str] | None) -> Path:
    if not value:
        return project_root() / DEFAULT_REFERENCE_AUDIO
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return project_root() / path


def ensure_cosyvoice_clone(config: AliyunCosyVoiceConfig, *, force: bool = False) -> str:
    return ensure_cosyvoice_voices(config, force=force)[0]


def ensure_cosyvoice_voices(config: AliyunCosyVoiceConfig, *, force: bool = False) -> list[str]:
    if not config.clone_enabled:
        return [config.voice]

    if config.clone_target_model and config.clone_target_model != config.model:
        raise RuntimeError(
            "CosyVoice clone target_model must match TTS model: "
            f"target_model={config.clone_target_model}, model={config.model}"
        )

    registry_path = config.voice_registry_path
    if registry_path and registry_path.exists() and not force:
        entries = load_voice_registry(registry_path)
        voice_ids = [item["registered_voice_id"] for item in entries if item.get("registered_voice_id")]
        if voice_ids:
            LOGGER.info("Using Aliyun cloned voice registry=%s count=%d", registry_path, len(voice_ids))
            return voice_ids

    cache_path = config.cloned_voice_cache_path
    if cache_path and cache_path.exists() and not force:
        voice_id = cache_path.read_text(encoding="utf-8").strip()
        if voice_id:
            LOGGER.info("Using cached Aliyun cloned voice_id=%s", voice_id)
            return [voice_id]

    audio_url = config.clone_audio_url
    if not audio_url:
        raise RuntimeError(
            "Creating an Aliyun cloned voice requires a public audio URL. "
            "Set TANYUE_COSYVOICE_CLONE_AUDIO_URL, or keep a cached voice_id in "
            f"{config.cloned_voice_cache_path}."
        )

    prefix = normalize_clone_prefix(config.clone_prefix)
    LOGGER.info(
        "Creating Aliyun cloned voice: target_model=%s prefix=%s audio=%s",
        config.model,
        prefix,
        audio_url,
    )
    voice_id = create_cosyvoice_clone_http(
        config,
        prefix=prefix,
        audio_url=audio_url,
    )
    LOGGER.info("Created Aliyun cloned voice_id=%s", voice_id)

    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(f"{voice_id}\n", encoding="utf-8")
    return [voice_id]


def load_voice_registry(path: Path) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    voices = payload.get("voices", [])
    if not isinstance(voices, list):
        raise RuntimeError(f"Invalid CosyVoice registry: {path}")
    result = []
    for item in voices:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        voice_id = str(item.get("registered_voice_id") or "").strip()
        source_file_name = str(item.get("source_file_name") or "").strip()
        display_name = str(item.get("display_name") or key).strip()
        if key:
            result.append(
                {
                    "key": key,
                    "registered_voice_id": voice_id,
                    "source_file_name": source_file_name,
                    "display_name": display_name,
                }
            )
    return result


def save_voice_registry(path: Path, entries: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "voices": entries}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_voice_registry_entry(path: Path, key: str, voice_id: str, source_file_name: str = "") -> None:
    entries = load_voice_registry(path) if path.exists() else []
    for item in entries:
        if item["key"] == key:
            item["registered_voice_id"] = voice_id
            if source_file_name:
                item["source_file_name"] = source_file_name
            save_voice_registry(path, entries)
            return
    entries.append(
        {
            "key": key,
            "registered_voice_id": voice_id,
            "source_file_name": source_file_name,
            "display_name": key,
        }
    )
    save_voice_registry(path, entries)


def normalize_clone_prefix(prefix: str) -> str:
    normalized = "".join(ch for ch in prefix.lower() if ch.isdigit() or ("a" <= ch <= "z"))
    normalized = normalized[:9]
    if not normalized:
        normalized = DEFAULT_CLONE_PREFIX
    return normalized


def create_cosyvoice_clone_http(
    config: AliyunCosyVoiceConfig,
    *,
    prefix: str,
    audio_url: str,
) -> str:
    import httpx

    endpoint = clone_endpoint(config)
    body = {
        "model": "voice-enrollment",
        "input": {
            "action": "create_voice",
            "target_model": config.model,
            "prefix": prefix,
            "url": audio_url,
        },
    }
    if config.language_hints:
        body["input"]["language_hints"] = config.language_hints
    if config.clone_max_prompt_audio_length is not None:
        body["input"]["max_prompt_audio_length"] = config.clone_max_prompt_audio_length

    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    if config.workspace_id:
        headers["X-DashScope-WorkSpace"] = config.workspace_id

    with httpx.Client(trust_env=False, timeout=120) as client:
        response = client.post(endpoint, headers=headers, json=body)
    if response.status_code != 200:
        raise RuntimeError(
            "Aliyun CosyVoice clone failed: "
            f"status={response.status_code}, body={response.text[:1000]}"
        )

    payload = response.json()
    try:
        return payload["output"]["voice_id"]
    except KeyError as exc:
        raise RuntimeError(f"Aliyun CosyVoice clone response missing voice_id: {payload}") from exc


def clone_endpoint(config: AliyunCosyVoiceConfig) -> str:
    if config.api_host:
        return f"https://{config.api_host}/api/v1/services/audio/tts/customization"
    return "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/customization"

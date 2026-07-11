#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import logging
import os
import sys
import uuid
from pathlib import Path

LOGGER = logging.getLogger("tanyue.web")
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
except Exception:  # noqa: BLE001
    load_dotenv = None

if load_dotenv:
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(PROJECT_ROOT / "voice" / ".env")

os.environ.setdefault("LIVEKIT_LOG_LEVEL", "info")
os.environ.setdefault("LIVEKIT_URL", "ws://127.0.0.1:7880")
os.environ.setdefault("LIVEKIT_API_KEY", "devkey")
os.environ.setdefault("LIVEKIT_API_SECRET", "devsecret")


def load_project_config():
    try:
        return importlib.import_module("Config")
    except Exception:  # noqa: BLE001
        return None


def ensure_dashscope_env() -> str:
    config = load_project_config()
    api_key = os.environ.get("DASHSCOPE_API_KEY") or getattr(config, "API_KEY", None)
    if not api_key:
        raise RuntimeError("Missing DashScope API key. Set DASHSCOPE_API_KEY or Config.py API_KEY.")
    os.environ["DASHSCOPE_API_KEY"] = api_key

    workspace_id = (
        os.environ.get("DASHSCOPE_WORKSPACE_ID")
        or getattr(config, "DASHSCOPE_WORKSPACE_ID", None)
        or getattr(config, "WORKSPACE_ID", None)
        or getattr(config, "WORKSAPCE_ID", None)
    )
    if workspace_id:
        os.environ["DASHSCOPE_WORKSPACE_ID"] = workspace_id

    api_host = os.environ.get("DASHSCOPE_API_HOST") or getattr(config, "API_HOST", None)
    if api_host:
        os.environ["DASHSCOPE_API_HOST"] = api_host

    region = os.environ.get("DASHSCOPE_REGION") or getattr(config, "DASHSCOPE_REGION", None)
    if region:
        os.environ["DASHSCOPE_REGION"] = region
    return api_key


def run_livekit_agent() -> None:
    from livekit import agents

    from voice.scripts.livekit_voice_agent import build_server

    _, server = build_server()
    agents.cli.run_app(server)


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing {name}. Put it in .env or voice/.env.")
    return value


def create_app():
    from fastapi import FastAPI
    from fastapi import Body
    from fastapi.responses import HTMLResponse, Response
    from fastapi.staticfiles import StaticFiles
    from livekit.api import (
        AccessToken,
        CreateAgentDispatchRequest,
        LiveKitAPI,
        VideoGrants,
    )

    app = FastAPI(title="Tanyue LiveKit Voice Agent")
    index_path = PROJECT_ROOT / "web" / "tanyue_livekit.html"
    character_path = PROJECT_ROOT / "character"
    app.mount("/character", StaticFiles(directory=character_path, html=True), name="character")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return index_path.read_text(encoding="utf-8")

    @app.get("/favicon.ico")
    def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/api/livekit-token")
    def livekit_token(room: str = "tanyue-room", name: str = "user") -> dict[str, str]:
        api_key = require_env("LIVEKIT_API_KEY")
        api_secret = require_env("LIVEKIT_API_SECRET")
        livekit_url = require_env("LIVEKIT_URL")
        identity = f"{name}-{uuid.uuid4().hex[:8]}"
        token = (
            AccessToken(api_key, api_secret)
            .with_identity(identity)
            .with_name(name)
            .with_grants(
                VideoGrants(
                    room_join=True,
                    room=room,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=True,
                )
            )
            .to_jwt()
        )
        return {"url": livekit_url, "token": token, "room": room, "identity": identity}

    @app.post("/api/dispatch-agent")
    async def dispatch_agent(
        room: str = "tanyue-room",
        replace: bool = True,
    ) -> dict[str, str | list[str]]:
        agent_name = os.environ.get("TANYUE_LIVEKIT_AGENT_NAME", "tanyue")
        metadata = json.dumps({"mode": "meme_play"}, ensure_ascii=False)
        livekit = LiveKitAPI(
            require_env("LIVEKIT_URL"),
            require_env("LIVEKIT_API_KEY"),
            require_env("LIVEKIT_API_SECRET"),
        )
        try:
            deleted_dispatches: list[str] = []
            for item in await livekit.agent_dispatch.list_dispatch(room):
                if item.agent_name == agent_name or not item.agent_name:
                    if replace:
                        try:
                            await livekit.agent_dispatch.delete_dispatch(item.id, room)
                            deleted_dispatches.append(item.id)
                        except Exception:
                            pass
                        continue
                    return {
                        "status": "existing",
                        "agent_name": agent_name,
                        "room": room,
                        "dispatch_id": item.id,
                        "deleted_dispatches": deleted_dispatches,
                    }
            dispatch = await livekit.agent_dispatch.create_dispatch(
                CreateAgentDispatchRequest(
                    agent_name=agent_name,
                    room=room,
                    metadata=metadata,
                )
            )
            return {
                "status": "replaced" if deleted_dispatches else "dispatched",
                "agent_name": agent_name,
                "room": room,
                "mode": "meme_play",
                "dispatch_id": dispatch.id,
                "deleted_dispatches": deleted_dispatches,
            }
        finally:
            await livekit.aclose()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    def get_robot_runtime():
        interface = (
            os.environ.get("TANYUE_ROBOT_INTERFACE")
            or os.environ.get("TANYUE_ROBOT_DEFAULT_INTERFACE")
            or "en7"
        ).strip()
        if not interface:
            return None
        runtime = getattr(app.state, "robot_runtime", None)
        if runtime is not None:
            return runtime

        from robot_voice.unitree_g1_voice import UnitreeG1Voice, apply_gain_s16le_stream
        from robot_voice.stream_tts_to_robot import stream_text_to_robot
        from robot_voice.voice_registry import load_voice_registry, resolve_voice
        from voice.tanyue_livekit.aliyun_cosyvoice import AliyunCosyVoiceTTS, config_from_env

        api_key = ensure_dashscope_env()
        robot = UnitreeG1Voice(interface, timeout=float(os.environ.get("TANYUE_ROBOT_TIMEOUT", "5.0")))
        robot.connect()
        try:
            current_volume = robot.get_volume()
            LOGGER.info("Robot voice volume before playback: %s", current_volume)
            if current_volume <= 0:
                fallback_volume = int(float(os.environ.get("TANYUE_ROBOT_DEFAULT_VOLUME", "85")))
                robot.set_volume(fallback_volume)
                LOGGER.info("Robot voice volume auto-raised to: %s", fallback_volume)
        except Exception as exc:  # noqa: BLE001
            LOGGER.info("Could not query robot volume: %s", exc)
        volume = os.environ.get("TANYUE_ROBOT_VOLUME")
        target_volume = max(0, min(100, int(float(volume)))) if volume is not None and volume.strip() else 100
        robot.set_volume(target_volume)
        LOGGER.info("Robot voice volume set to: %s", target_volume)

        tts = AliyunCosyVoiceTTS(config_from_env(api_key=api_key))
        if tts.config.clone_enabled:
            tts.ensure_cloned_voice()
        default_voice_key = os.environ.get("TANYUE_ROBOT_VOICE", "default")
        default_voice = resolve_voice(default_voice_key, load_voice_registry())

        runtime = {
            "interface": interface,
            "robot": robot,
            "tts": tts,
            "voice_id": default_voice.registered_voice_id,
            "voice_key": default_voice.key,
            "app_name": os.environ.get("TANYUE_ROBOT_APP_NAME", "tanyue"),
            "emotion": os.environ.get("TANYUE_ROBOT_EMOTION", ""),
            "emotion_strength": os.environ.get("TANYUE_ROBOT_EMOTION_STRENGTH", "strong"),
            "mode": os.environ.get("TANYUE_ROBOT_TTS_MODE", "auto"),
            "speed": float(os.environ.get("TANYUE_ROBOT_SPEED", "1.0")),
            "gain_db": float(os.environ.get("TANYUE_ROBOT_GAIN_DB", "6.0")),
            "trim_start_ms": float(os.environ.get("TANYUE_ROBOT_TRIM_START_MS", "0.0")),
            "robot_chunk_bytes": int(os.environ.get("TANYUE_ROBOT_CHUNK_BYTES", "96000")),
            "tail_wait_ms": float(os.environ.get("TANYUE_ROBOT_TAIL_WAIT_MS", "1000.0")),
            "send_interval_ms": (
                float(os.environ["TANYUE_ROBOT_SEND_INTERVAL_MS"])
                if os.environ.get("TANYUE_ROBOT_SEND_INTERVAL_MS")
                else None
            ),
            "gain": apply_gain_s16le_stream,
            "stream_text_to_robot": stream_text_to_robot,
            "verbose": os.environ.get("TANYUE_ROBOT_VERBOSE", "0") in {"1", "true", "True", "yes", "on"},
        }
        app.state.robot_runtime = runtime
        return runtime

    def resolve_robot_voice(value: str | None, fallback_id: str, fallback_key: str) -> tuple[str, str]:
        value = str(value or "").strip()
        if not value:
            return fallback_id, fallback_key
        try:
            from robot_voice.voice_registry import load_voice_registry, resolve_voice

            entry = resolve_voice(value, load_voice_registry())
            return entry.registered_voice_id, entry.key
        except Exception:
            pass

        voice_registry_path = PROJECT_ROOT / "voice" / "cosyvoice_voices.json"
        try:
            payload = json.loads(voice_registry_path.read_text(encoding="utf-8"))
            for item in payload.get("voices", []):
                key = str(item.get("key") or "").strip()
                voice_id = str(item.get("registered_voice_id") or "").strip()
                if value in {key, voice_id} and voice_id:
                    return voice_id, key or value
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("Could not resolve voice from %s: %s", voice_registry_path, exc)

        if value.startswith("cosyvoice-"):
            return value, value
        return fallback_id, fallback_key

    @app.post("/api/robot-playback")
    async def robot_playback(payload: dict[str, Any] = Body(default_factory=dict)) -> dict[str, Any]:
        text = str(payload.get("text") or "").strip()
        if not text:
            return {"status": "ignored", "reason": "empty text"}
        try:
            runtime = get_robot_runtime()
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Robot runtime init failed")
            return {
                "status": "error",
                "stage": "init",
                "reason": f"{type(exc).__name__}: {exc}",
            }
        if runtime is None:
            return {"status": "disabled", "reason": "robot interface is not configured"}
        requested_voice = (
            payload.get("voice_id")
            or payload.get("voiceId")
            or payload.get("voice_key")
            or payload.get("voiceKey")
        )
        voice_id, voice_key = resolve_robot_voice(
            str(requested_voice or ""),
            runtime["voice_id"],
            runtime["voice_key"],
        )

        def _play() -> None:
            LOGGER.info(
                "Robot playback start: interface=%s voice=%s text=%s",
                runtime["interface"],
                voice_key,
                text[:120],
            )
            runtime["stream_text_to_robot"](
                runtime["tts"],
                runtime["robot"],
                text,
                runtime["emotion"],
                runtime["emotion_strength"],
                runtime["mode"],
                runtime["speed"],
                voice_id,
                runtime["app_name"],
                runtime["send_interval_ms"],
                runtime["tail_wait_ms"],
                runtime["gain_db"],
                runtime["trim_start_ms"],
                runtime["robot_chunk_bytes"],
                runtime["verbose"],
            )
            LOGGER.info("Robot playback finished: text=%s", text[:120])

        try:
            await asyncio.to_thread(_play)
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Robot playback failed")
            return {
                "status": "error",
                "stage": "playback",
                "reason": f"{type(exc).__name__}: {exc}",
                "interface": runtime["interface"],
                "voice": voice_key,
            }
        return {
            "status": "ok",
            "text": text[:80],
            "volume": runtime["robot"].get_volume(),
            "interface": runtime["interface"],
            "voice": voice_key,
        }

    @app.get("/api/livekit-status")
    async def livekit_status(room: str = "tanyue-room") -> dict:
        return await collect_livekit_status(room)

    return app


async def collect_livekit_status(room: str = "tanyue-room") -> dict:
    from livekit.api import (
        ListParticipantsRequest,
        ListRoomsRequest,
        LiveKitAPI,
    )

    livekit = LiveKitAPI(
        require_env("LIVEKIT_URL"),
        require_env("LIVEKIT_API_KEY"),
        require_env("LIVEKIT_API_SECRET"),
    )
    try:
        rooms_res = await livekit.room.list_rooms(ListRoomsRequest(names=[room]))
        dispatches = await livekit.agent_dispatch.list_dispatch(room)
        participants_res = None
        participant_error = None
        try:
            participants_res = await livekit.room.list_participants(
                ListParticipantsRequest(room=room)
            )
        except Exception as exc:  # noqa: BLE001
            participant_error = str(exc)

        return {
            "livekit_url": require_env("LIVEKIT_URL"),
            "room": room,
            "rooms": [
                {
                    "name": item.name,
                    "sid": item.sid,
                    "num_participants": item.num_participants,
                }
                for item in rooms_res.rooms
            ],
            "participants": [
                {
                    "identity": item.identity,
                    "name": item.name,
                    "sid": item.sid,
                    "kind": str(item.kind),
                }
                for item in (participants_res.participants if participants_res else [])
            ],
            "participant_error": participant_error,
            "dispatches": [
                summarize_dispatch(item)
                for item in dispatches
            ],
        }
    finally:
        await livekit.aclose()


def summarize_dispatch(item) -> dict[str, str]:
    jobs = list(getattr(item, "jobs", []))
    if jobs:
        job = jobs[-1]
        state = getattr(job, "state", None)
        status = str(getattr(state, "status", "unknown")).split(".")[-1]
        participant_identity = getattr(state, "participant_identity", "")
        worker_id = getattr(state, "worker_id", "")
        job_id = getattr(job, "id", "")
        summary = status
        if participant_identity:
            summary += f" participant={participant_identity}"
        if worker_id:
            summary += f" worker={worker_id}"
        return {
            "id": item.id,
            "agent_name": item.agent_name,
            "room": item.room,
            "state": summary,
            "job_id": job_id,
            "participant_identity": participant_identity,
            "metadata": getattr(item, "metadata", ""),
        }

    created_at = getattr(item, "created_at", "")
    return {
        "id": item.id,
        "agent_name": item.agent_name,
        "room": item.room,
        "state": f"created_at={created_at}" if created_at else "created",
        "job_id": "",
        "participant_identity": "",
        "metadata": getattr(item, "metadata", ""),
    }


def run_status(args: argparse.Namespace) -> None:
    status = asyncio.run(collect_livekit_status(args.room))
    print(f"livekit_url={status['livekit_url']}")
    print(f"room={status['room']}")
    print("rooms:")
    for room in status["rooms"]:
        print(f"  - {room['name']} sid={room['sid']} participants={room['num_participants']}")
    if not status["rooms"]:
        print("  - none")
    print("participants:")
    for participant in status["participants"]:
        print(
            f"  - {participant['identity']} name={participant['name']} "
            f"sid={participant['sid']} kind={participant['kind']}"
        )
    if not status["participants"]:
        print("  - none")
    if status["participant_error"]:
        print(f"participant_error={status['participant_error']}")
    print("dispatches:")
    for dispatch in status["dispatches"]:
        metadata = f" metadata={dispatch['metadata']}" if dispatch.get("metadata") else ""
        print(
            f"  - id={dispatch['id']} agent={dispatch['agent_name']} "
            f"room={dispatch['room']} state={dispatch['state']}{metadata}"
        )
    if not status["dispatches"]:
        print("  - none")


def run_clone_voice(args: argparse.Namespace) -> None:
    from voice.scripts.livekit_voice_agent import dashscope_api_key
    from voice.tanyue_livekit.aliyun_cosyvoice import (
        AliyunCosyVoiceTTS,
        config_from_env,
        create_cosyvoice_clone_http,
        dataclass_replace,
        load_voice_registry,
        normalize_clone_prefix,
        update_voice_registry_entry,
    )

    api_key = dashscope_api_key()
    config = config_from_env(api_key=api_key)
    registry_path = config.voice_registry_path
    if args.list_voices:
        if registry_path and registry_path.exists():
            for item in load_voice_registry(registry_path):
                voice_id = item.get("registered_voice_id") or "(unregistered)"
                print(f"{item['key']:12s} voice_id={voice_id} source={item.get('source_file_name', '')}")
        else:
            print(f"voice registry not found: {registry_path}")
        return

    if args.set_voice_id:
        if not registry_path:
            raise RuntimeError("Missing TANYUE_COSYVOICE_VOICE_REGISTRY path.")
        for key, voice_id in args.set_voice_id:
            update_voice_registry_entry(registry_path, key, voice_id)
            print(f"{key}: registered_voice_id={voice_id}")

    if args.url:
        if not registry_path:
            raise RuntimeError("Missing TANYUE_COSYVOICE_VOICE_REGISTRY path.")
        for key, url in args.url:
            prefix = normalize_clone_prefix(key)
            source_file_name = Path(url.split("?", 1)[0]).name
            voice_id = create_cosyvoice_clone_http(
                dataclass_replace(
                    config,
                    clone_prefix=prefix,
                    clone_audio_url=url,
                    clone_max_prompt_audio_length=args.max_seconds,
                ),
                prefix=prefix,
                audio_url=url,
            )
            update_voice_registry_entry(registry_path, key, voice_id, source_file_name=source_file_name)
            print(f"{key}: registered_voice_id={voice_id}")

    if args.list_voices or args.set_voice_id or args.url:
        print(f"updated: {registry_path}")
        if registry_path and registry_path.exists():
            for item in load_voice_registry(registry_path):
                voice_id = item.get("registered_voice_id") or "(unregistered)"
                print(f"{item['key']:12s} voice_id={voice_id} source={item.get('source_file_name', '')}")
        return

    tts = AliyunCosyVoiceTTS(config)
    voice_id = tts.ensure_cloned_voice(force=args.force)
    print(f"voice_id={voice_id}")


def parse_pair(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("expected KEY=VALUE")
    key, item = value.split("=", 1)
    key = key.strip()
    item = item.strip()
    if not key or not item:
        raise argparse.ArgumentTypeError("expected non-empty KEY=VALUE")
    return key, item


def run_web(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run(
        create_app(),
        host=args.host,
        port=args.port,
        log_level="info",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Tanyue voice agent root entrypoint. Use 'web' for the browser UI; all other args are forwarded to LiveKit Agents.",
    )
    subparsers = parser.add_subparsers(dest="command")
    web_parser = subparsers.add_parser("web", help="Start the local web UI and LiveKit token service.")
    web_parser.add_argument("--host", default="127.0.0.1")
    web_parser.add_argument("--port", type=int, default=8894)
    status_parser = subparsers.add_parser("status", help="Print LiveKit room, participant, and agent dispatch status.")
    status_parser.add_argument("--room", default="tanyue-room")
    clone_parser = subparsers.add_parser("clone-voice", help="Create or refresh the Aliyun CosyVoice cloned voice.")
    clone_parser.add_argument("--force", action="store_true", help="Ignore the cached voice_id and create a new cloned voice.")
    clone_parser.add_argument("--list-voices", action="store_true", help="List registered cloned voices.")
    clone_parser.add_argument("--url", action="append", type=parse_pair, default=[], help="Register a voice from public audio URL: key=https://...")
    clone_parser.add_argument("--set-voice-id", action="append", type=parse_pair, default=[], help="Write an existing voice_id into the registry: key=voice_id.")
    clone_parser.add_argument("--max-seconds", type=float, default=20.0, help="Max prompt audio length for Aliyun voice enrollment.")

    if len(sys.argv) == 1 or sys.argv[1] in {"-h", "--help"}:
        parser.print_help()
        print("\nLiveKit commands are also forwarded: console, start, dev, connect, download-files.")
        print("Examples:")
        print("  python tanyue_agent.py web")
        print("  python tanyue_agent.py console")
        print("  python tanyue_agent.py start")
        return 0

    if sys.argv[1] == "web":
        args = parser.parse_args()
        run_web(args)
        return 0

    if sys.argv[1] == "status":
        args = parser.parse_args()
        run_status(args)
        return 0

    if sys.argv[1] == "clone-voice":
        args = parser.parse_args()
        run_clone_voice(args)
        return 0

    run_livekit_agent()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

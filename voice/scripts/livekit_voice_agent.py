#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import asyncio
import importlib
import json
import logging
import math
import struct
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
except Exception:  # noqa: BLE001
    load_dotenv = None

if load_dotenv:
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(ROOT / ".env")

os.environ.setdefault("LIVEKIT_URL", "ws://127.0.0.1:7880")
os.environ.setdefault("LIVEKIT_API_KEY", "devkey")
os.environ.setdefault("LIVEKIT_API_SECRET", "devsecret")

try:
    CONFIG = importlib.import_module("Config")
except Exception:  # noqa: BLE001
    CONFIG = None

CONFIG_API_KEY = getattr(CONFIG, "API_KEY", None)
CONFIG_WORKSPACE_ID = (
    getattr(CONFIG, "DASHSCOPE_WORKSPACE_ID", None)
    or getattr(CONFIG, "WORKSPACE_ID", None)
    or getattr(CONFIG, "WORKSAPCE_ID", None)
)
CONFIG_API_HOST = getattr(CONFIG, "API_HOST", None)
CONFIG_REGION = getattr(CONFIG, "DASHSCOPE_REGION", None)

from voice.tanyue_livekit import AliyunCosyVoiceTTS, AliyunRealtimeSTT
from voice.tanyue_livekit.aliyun_cosyvoice import config_from_env
from voice.tanyue_livekit.aliyun_stt import config_from_env as stt_config_from_env
from pungen_agent.recognizer import MemeRecognizer, load_meme_library

LOGGER = logging.getLogger("tanyue.livekit")

FALLBACK_EXPRESSIONS = {"neutral", "happy", "relaxed", "sad", "surprised", "angry"}
NON_EMOTION_EXPRESSIONS = {"aa", "ih", "ou", "ee", "oh", "blink", "blinkLeft", "blinkRight"}
DEFAULT_MEME_SCENE = "玩梗实时对话"
MEME_ASSISTANT_PROMPT = (
    "你是一个配合玩家玩梗的实时语音数字人，任务是在听懂用户原话后接住梗、补梗、轻轻吐槽或给出短促舞台反应。"
    "回复要像朋友一起玩梗：自然、有节奏、不过度解释。"
    "如果识别到了梗，要优先围绕该梗回应；如果没识别到明确梗，就正常接话，并尽量给用户留下继续抛梗的空间。"
    "不要把“识别结果”“meme_id”“confidence”等内部字段说出来。"
    "不要输出角色扮演系统设定，不要攻击用户。"
    "默认只说一句，尽量不超过30个汉字；需要包袱时可以短一点。"
)
DEFAULT_REPLY_MOTION_CANDIDATES = [
    "talking_on_phone",
    "pointing",
    "pointing_forward",
    "waving",
    "standing",
    "female_standing_pose",
    "catwalk_idle_to_twist_r",
]


def dashscope_api_key() -> str:
    api_key = os.environ.get("DASHSCOPE_API_KEY") or CONFIG_API_KEY
    if not api_key:
        raise RuntimeError("Missing DashScope API key. Set DASHSCOPE_API_KEY or Config.py API_KEY.")
    os.environ["DASHSCOPE_API_KEY"] = api_key
    if CONFIG_WORKSPACE_ID and not os.environ.get("DASHSCOPE_WORKSPACE_ID"):
        os.environ["DASHSCOPE_WORKSPACE_ID"] = CONFIG_WORKSPACE_ID
    if CONFIG_API_HOST and not os.environ.get("DASHSCOPE_API_HOST"):
        os.environ["DASHSCOPE_API_HOST"] = CONFIG_API_HOST
    if CONFIG_REGION and not os.environ.get("DASHSCOPE_REGION"):
        os.environ["DASHSCOPE_REGION"] = CONFIG_REGION
    return api_key


def today_context() -> str:
    now = datetime.now()
    return now.strftime("%Y-%m-%d %A")


def env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value in {"1", "true", "True", "yes", "YES", "on", "ON"}


def qwen_extra_body() -> dict[str, object]:
    extra: dict[str, object] = {
        "enable_thinking": env_bool("TANYUE_QWEN_ENABLE_THINKING", False),
    }
    return extra


def load_motion_manifest() -> dict[str, Any]:
    manifest_path = PROJECT_ROOT / "character" / "motions" / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Could not load character motion manifest: %s", exc)
        return {"version": 1, "defaultIdleMotion": "angry", "motions": []}
    if isinstance(manifest, list):
        return {"version": 0, "defaultIdleMotion": "angry", "motions": manifest}
    return manifest


def motion_prompt(manifest: dict[str, Any]) -> str:
    motions = []
    for motion in manifest.get("motions", []):
        if not motion.get("id"):
            continue
        motions.append(
            {
                "id": motion.get("id"),
                "label": motion.get("label", motion.get("id")),
                "description": motion.get("description", ""),
                "situations": motion.get("situations", []),
                "mood": motion.get("mood", []),
                "tags": motion.get("tags", []),
            }
        )
    payload = {
        "defaultIdleMotion": manifest.get("defaultIdleMotion", "angry"),
        "motions": motions,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def load_character_expressions() -> set[str]:
    configured = os.environ.get("TANYUE_CHARACTER_EXPRESSIONS")
    if configured:
        expressions = {item.strip() for item in configured.split(",") if item.strip()}
        return expressions or FALLBACK_EXPRESSIONS

    model_path = Path(os.environ.get("TANYUE_CHARACTER_MODEL", PROJECT_ROOT / "character" / "models" / "LiuRuYan.vrm"))
    try:
        data = model_path.read_bytes()
        if data[:4] != b"glTF":
            return FALLBACK_EXPRESSIONS
        offset = 12
        while offset + 8 <= len(data):
            chunk_length, chunk_type = struct.unpack_from("<II", data, offset)
            offset += 8
            chunk = data[offset : offset + chunk_length]
            offset += chunk_length
            if chunk_type != 0x4E4F534A:
                continue
            gltf = json.loads(chunk.decode("utf-8"))
            vrm1 = gltf.get("extensions", {}).get("VRMC_vrm", {}).get("expressions", {})
            preset = set((vrm1.get("preset") or {}).keys())
            custom = set((vrm1.get("custom") or {}).keys())
            vrm0_groups = (
                gltf.get("extensions", {})
                .get("VRM", {})
                .get("blendShapeMaster", {})
                .get("blendShapeGroups", [])
            )
            vrm0 = {
                str(group.get("name") or group.get("presetName") or "").strip()
                for group in vrm0_groups
            }
            expressions = {item for item in preset | custom | vrm0 if item and item not in NON_EMOTION_EXPRESSIONS}
            return expressions or FALLBACK_EXPRESSIONS
    except Exception as exc:  # noqa: BLE001
        LOGGER.info("Could not read VRM expression presets: %s", exc)
    return FALLBACK_EXPRESSIONS


def expression_prompt(expressions: set[str]) -> str:
    preferred_order = ["neutral", "relaxed", "happy", "surprised", "sad", "angry"]
    ordered = [item for item in preferred_order if item in expressions]
    ordered.extend(sorted(expressions - set(ordered)))
    return json.dumps(ordered, ensure_ascii=False, separators=(",", ":"))


def select_reply_fallback_motion(valid_motions: set[str], default_motion: str) -> str:
    for motion in DEFAULT_REPLY_MOTION_CANDIDATES:
        if motion in valid_motions:
            return motion
    for motion in sorted(valid_motions):
        if motion != default_motion:
            return motion
    return default_motion


def load_meme_recognizer() -> MemeRecognizer:
    return MemeRecognizer(load_meme_library())


def message_text(item: Any) -> str:
    text_content = getattr(item, "text_content", None)
    if text_content:
        return str(text_content).strip()
    content = getattr(item, "content", None)
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [str(part) for part in content if isinstance(part, str)]
        return "\n".join(parts).strip()
    return ""


def latest_user_text(chat_ctx: Any) -> str:
    items = list(getattr(chat_ctx, "items", []) or [])
    for item in reversed(items):
        if getattr(item, "type", "") != "message":
            continue
        if getattr(item, "role", "") != "user":
            continue
        text = message_text(item)
        if text:
            return text
    return ""


def compact_meme_result(recognition: dict[str, Any]) -> dict[str, Any]:
    candidates = []
    for item in recognition.get("candidates", [])[:3]:
        if not isinstance(item, dict):
            continue
        candidates.append(
            {
                "meme_id": item.get("meme_id"),
                "meme_name": item.get("meme_name"),
                "character_id": item.get("character_id"),
                "confidence": item.get("confidence"),
                "match_type": item.get("match_type"),
                "matched_symbols": item.get("matched_symbols", []),
                "matched_aliases": item.get("matched_aliases", []),
                "matched_lines": item.get("matched_lines", []),
                "line": item.get("line", ""),
                "reason": item.get("reason", ""),
            }
        )
    return {
        "meme_id": recognition.get("meme_id"),
        "meme_name": recognition.get("meme_name"),
        "character_id": recognition.get("character_id", ""),
        "confidence": recognition.get("confidence", 0.0),
        "match_type": recognition.get("match_type", "none"),
        "matched_symbols": recognition.get("matched_symbols", []),
        "matched_aliases": recognition.get("matched_aliases", []),
        "matched_lines": recognition.get("matched_lines", []),
        "line": recognition.get("line", ""),
        "reason": recognition.get("reason", ""),
        "candidates": candidates,
    }


def meme_context_prompt(user_text: str, recognition: dict[str, Any]) -> str:
    payload = {
        "user_text": user_text,
        "meme_recognition": compact_meme_result(recognition),
        "instruction": (
            "请结合 user_text 和 meme_recognition 回复用户。"
            "若 meme_id 不为空，优先接住这个梗或顺着它补一句。"
            "若 meme_id 为空，不要硬编梗，正常接话即可。"
        ),
    }
    return "本轮梗识别上下文：\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def parse_assistant_payload(
    raw: str,
    valid_motions: set[str],
    valid_expressions: set[str],
    default_motion: str,
    default_expression: str = "relaxed",
) -> tuple[str, str, str]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()

    candidates = [text]
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        reply = str(payload.get("reply") or payload.get("text") or "").strip()
        motion = str(payload.get("motion") or payload.get("action") or default_motion).strip()
        expression = str(payload.get("expression") or payload.get("face") or default_expression).strip()
        if motion not in valid_motions:
            motion = default_motion
        if expression not in valid_expressions:
            expression = default_expression
        if reply:
            return reply, motion, expression

    LOGGER.warning("Could not parse assistant motion payload, speaking raw text: %s", raw[:300])
    return raw.strip(), default_motion, default_expression


def audio_frame_lip_level(frame: Any, *, gain: float = 7.0, noise_floor: float = 0.01) -> float:
    data = bytes(getattr(frame, "data", b""))
    if len(data) < 2:
        return 0.0
    if len(data) % 2:
        data = data[:-1]
    samples = memoryview(data).cast("h")
    if not samples:
        return 0.0
    # CosyVoice emits 16-bit PCM. RMS gives a stable mouth-open envelope for VRM expressions.
    square_sum = 0
    for sample in samples:
        square_sum += sample * sample
    rms = math.sqrt(square_sum / len(samples)) / 32768.0
    return min(1.0, max(0.0, (rms - noise_floor) * gain))


class TanyueAssistant:
    def __init__(self, motion_manifest: dict[str, Any]):
        from livekit.agents import Agent

        motion_manifest_text = motion_prompt(motion_manifest)
        valid_expressions = load_character_expressions()
        expression_manifest_text = expression_prompt(valid_expressions)
        valid_motions = {
            item.get("id")
            for item in motion_manifest.get("motions", [])
            if isinstance(item, dict) and item.get("id")
        }
        default_motion = motion_manifest.get("defaultIdleMotion", "angry")
        if default_motion not in valid_motions:
            default_motion = "angry" if "angry" in valid_motions else next(iter(valid_motions), "angry")
        reply_fallback_motion = select_reply_fallback_motion(valid_motions, default_motion)

        class _Assistant(Agent):
            def __init__(self, tts: AliyunCosyVoiceTTS, room=None) -> None:
                self._aliyun_tts = tts
                self._character = build_character_agent()
                self._room = room
                self._meme_recognizer = load_meme_recognizer()
                self._valid_motions = valid_motions
                self._valid_expressions = valid_expressions
                self._default_motion = default_motion
                self._reply_fallback_motion = reply_fallback_motion
                self._speaking_expression = "relaxed"
                self._lip_sync_enabled = env_bool("TANYUE_CHARACTER_LIP_SYNC_ENABLED", False)
                self._lip_sync_interval = float(os.environ.get("TANYUE_CHARACTER_LIP_SYNC_INTERVAL", "0.08"))
                self._lip_sync_gain = float(os.environ.get("TANYUE_CHARACTER_LIP_SYNC_GAIN", "7.0"))
                self._lip_sync_noise_floor = float(os.environ.get("TANYUE_CHARACTER_LIP_SYNC_NOISE_FLOOR", "0.01"))
                self._expression_tail_seconds = float(
                    os.environ.get("TANYUE_CHARACTER_EXPRESSION_TAIL_SECONDS", "0.9")
                )
                self._expression_max_hold_seconds = float(
                    os.environ.get("TANYUE_CHARACTER_EXPRESSION_MAX_HOLD_SECONDS", "12.0")
                )
                self._last_lip_sync_at = 0.0
                self._last_lip_sync_level = 0.0
                self._pending_character_motion: str | None = None
                self._pending_character_expression: str | None = None
                self._pending_reply_text: str = ""
                self._pending_voice_key: str | None = None
                self._voice_model_active = False
                super().__init__(
                    instructions=(
                        "你是Tanyue的实时语音数字人。"
                        f"{MEME_ASSISTANT_PROMPT}"
                        "不要追问，不要输出列表，不要解释系统实现。"
                        "你必须只输出一个JSON对象，不要使用Markdown代码块。"
                        "JSON格式：{\"reply\":\"要说给用户的话\",\"motion\":\"动作id\",\"expression\":\"表情id\"}。"
                        "reply会被朗读，motion和expression只用于控制数字人，不能把动作id或表情id说出来。"
                        "reply中禁止包含方括号动作标记，禁止把舞台提示念出来。"
                        f"expression只能从这些VRM预设表情中选择：{expression_manifest_text}。"
                        "表情要贴合回复语气，并和动作一起开始播放，持续到语音播放结束。"
                        f"可选动作清单：{motion_manifest_text}。"
                        f"没有明确更合适动作时使用兜底动作：{reply_fallback_motion}。"
                        f"{default_motion}只作为无语音待机动作，不要把它当作普通回复动作。"
                        f"当前日期上下文：{today_context()}。"
                    )
                )

            async def llm_node(self, chat_ctx, tools, model_settings):
                from livekit.agents import Agent

                user_text = latest_user_text(chat_ctx)
                meme_chat_ctx = chat_ctx
                if user_text:
                    recognition = self._meme_recognizer.recognize(user_text, scene=DEFAULT_MEME_SCENE)
                    LOGGER.info(
                        "Tanyue meme recognition: text=%s meme=%s character=%s confidence=%.3f match=%s",
                        user_text[:80],
                        recognition.get("meme_id"),
                        recognition.get("character_id") or "none",
                        float(recognition.get("confidence") or 0.0),
                        recognition.get("match_type"),
                    )
                    character_id = str(recognition.get("character_id") or "").strip().lower()
                    self._pending_voice_key = character_id or None
                    try:
                        meme_chat_ctx = chat_ctx.copy()
                    except Exception:  # noqa: BLE001
                        meme_chat_ctx = chat_ctx
                    try:
                        meme_chat_ctx.add_message(
                            role="system",
                            content=meme_context_prompt(user_text, recognition),
                        )
                    except Exception as exc:  # noqa: BLE001
                        LOGGER.info("Could not attach meme context to chat: %s", exc)

                chunks: list[str] = []
                async for chunk in Agent.default.llm_node(self, meme_chat_ctx, tools, model_settings):
                    if isinstance(chunk, str):
                        chunks.append(chunk)
                        continue
                    content = getattr(getattr(chunk, "delta", None), "content", None)
                    if content:
                        chunks.append(content)

                reply, motion, expression = parse_assistant_payload(
                    "".join(chunks),
                    self._valid_motions,
                    self._valid_expressions,
                    self._reply_fallback_motion,
                )
                if motion == self._default_motion and self._reply_fallback_motion != self._default_motion:
                    motion = self._reply_fallback_motion
                LOGGER.info(
                    "Tanyue character command: motion=%s expression=%s reply=%s",
                    motion,
                    expression,
                    reply[:80],
                )
                self._speaking_expression = expression
                self._pending_character_motion = motion
                self._pending_character_expression = expression
                self._pending_reply_text = reply
                self._aliyun_tts.set_voice_key(self._pending_voice_key)
                yield reply

            async def tts_node(self, text, model_settings):
                await self._publish_voice_state(True)
                tts_started_at = time.monotonic()
                audio_seconds = 0.0
                was_cancelled = False
                motion_started = False
                try:
                    async for frame in self._aliyun_tts.synthesize_frames(text):
                        if not motion_started:
                            await self._publish_voice_state(
                                True,
                                voice_key=self._aliyun_tts.selected_voice_key,
                                voice_id=self._aliyun_tts.selected_voice_id,
                                reply_text=self._pending_reply_text,
                            )
                            self._start_pending_character_motion(
                                model_key=self._aliyun_tts.selected_voice_key,
                            )
                            motion_started = True
                        audio_seconds += self._frame_duration_seconds(frame)
                        self._send_lip_sync_frame(frame)
                        yield frame
                except asyncio.CancelledError:
                    was_cancelled = True
                    raise
                finally:
                    if not motion_started:
                        self._clear_pending_character_motion()
                    if not was_cancelled:
                        await self._hold_expression_until_playout_finishes(audio_seconds, tts_started_at)
                    self._send_lip_sync_level(0.0, force=True)
                    self._reset_character_face()
                    self._restore_character_model()
                    self._play_character_idle()
                    self._aliyun_tts.clear_voice_key()
                    self._pending_voice_key = None
                    await self._publish_voice_state(False)

            def _start_pending_character_motion(self, model_key: str | None = None) -> None:
                motion = self._pending_character_motion
                expression = self._pending_character_expression or self._speaking_expression or "relaxed"
                self._pending_character_motion = None
                self._pending_character_expression = None
                if not motion:
                    return
                self._play_character_motion(motion, expression, model_key=model_key)
                self._pending_reply_text = ""

            def _clear_pending_character_motion(self) -> None:
                self._pending_character_motion = None
                self._pending_character_expression = None

            def _play_character_motion(self, motion: str, expression: str, model_key: str | None = None) -> None:
                if not self._character:
                    return
                try:
                    commands: list[dict[str, Any]] = []
                    if model_key:
                        LOGGER.info("Tanyue character model switch: %s", model_key)
                        commands.append({"type": "setModel", "model": model_key})
                        self._voice_model_active = True
                    commands.append(
                        {
                            "type": "setState",
                            "payload": {
                                "expression": expression,
                                "expressionIntensity": 1.0,
                                "motionLoop": motion == self._default_motion,
                                "motionSpeed": 1.0,
                            },
                        }
                    )
                    commands.append({"type": "playMotion", "motion": motion})
                    self._character.batch(commands)
                except Exception as exc:  # noqa: BLE001
                    LOGGER.info("Character motion command skipped: %s", exc)
                else:
                    if model_key:
                        self._voice_model_active = True

            def _play_character_idle(self) -> None:
                if not self._character:
                    return
                try:
                    commands = [{"type": "setExpression", "expression": "relaxed", "value": 1.0}]
                    if self._lip_sync_enabled:
                        commands.insert(0, {"type": "setLipSyncLevel", "level": 0.0})
                    commands.append({"type": "playIdleMotion"})
                    self._character.batch(commands)
                except Exception as exc:  # noqa: BLE001
                    LOGGER.info("Character idle command skipped: %s", exc)

            def _reset_character_face(self) -> None:
                if not self._character:
                    return
                try:
                    commands = []
                    if self._lip_sync_enabled:
                        commands.extend(
                            [
                                {"type": "setLipSyncLevel", "level": 0.0},
                                {"type": "setMouth", "aa": 0.0, "oh": 0.0},
                            ]
                        )
                    commands.append({"type": "setExpression", "expression": "relaxed", "value": 1.0})
                    self._character.batch(commands)
                except Exception as exc:  # noqa: BLE001
                    LOGGER.debug("Character face reset skipped: %s", exc)

            def _restore_character_model(self) -> None:
                if not self._character or not self._voice_model_active:
                    return
                try:
                    LOGGER.info("Tanyue character model restore")
                    self._character.restore_model()
                except Exception as exc:  # noqa: BLE001
                    LOGGER.debug("Character model restore skipped: %s", exc)
                finally:
                    self._voice_model_active = False

            def _frame_duration_seconds(self, frame: Any) -> float:
                samples = getattr(frame, "samples_per_channel", 0) or 0
                sample_rate = getattr(frame, "sample_rate", 0) or getattr(self._aliyun_tts, "sample_rate", 24000)
                if sample_rate <= 0:
                    return 0.0
                return float(samples) / float(sample_rate)

            async def _hold_expression_until_playout_finishes(
                self,
                audio_seconds: float,
                started_at: float,
            ) -> None:
                elapsed = time.monotonic() - started_at
                remaining = max(0.0, audio_seconds - elapsed)
                hold_seconds = min(
                    remaining + self._expression_tail_seconds,
                    self._expression_max_hold_seconds,
                )
                if hold_seconds > 0:
                    await asyncio.sleep(hold_seconds)

            def _send_lip_sync_frame(self, frame: Any) -> None:
                if not self._lip_sync_enabled:
                    return
                level = audio_frame_lip_level(
                    frame,
                    gain=self._lip_sync_gain,
                    noise_floor=self._lip_sync_noise_floor,
                )
                self._send_lip_sync_level(level)

            def _send_lip_sync_level(self, level: float, *, force: bool = False) -> None:
                if not self._character or not self._lip_sync_enabled:
                    return
                now = time.monotonic()
                if not force:
                    if now - self._last_lip_sync_at < self._lip_sync_interval:
                        return
                    if abs(level - self._last_lip_sync_level) < 0.035:
                        return
                self._last_lip_sync_at = now
                self._last_lip_sync_level = level
                try:
                    self._character.set_lip_sync_level(level)
                except Exception as exc:  # noqa: BLE001
                    LOGGER.debug("Character lip sync command skipped: %s", exc)

            async def _publish_voice_state(
                self,
                speaking: bool,
                *,
                voice_key: str | None = None,
                voice_id: str | None = None,
                reply_text: str | None = None,
            ) -> None:
                try:
                    local_participant = getattr(self._room, "local_participant", None)
                    if not local_participant:
                        return
                    payload = {
                        "type": "assistant_speaking",
                        "speaking": speaking,
                    }
                    if voice_key:
                        payload["voiceKey"] = voice_key
                    if voice_id:
                        payload["voiceId"] = voice_id
                    if reply_text:
                        payload["replyText"] = reply_text
                    await local_participant.publish_data(
                        json.dumps(payload, ensure_ascii=False),
                        reliable=True,
                        topic="tanyue.control",
                    )
                except Exception as exc:  # noqa: BLE001
                    LOGGER.info("Could not publish assistant voice state: %s", exc)

        self.cls = _Assistant


def build_character_agent():
    if not env_bool("TANYUE_CHARACTER_ENABLED", True):
        return None
    try:
        from character.tanyue_character import CharacterAgent, CharacterAgentConfig

        return CharacterAgent(
            CharacterAgentConfig(
                base_url=os.environ.get("TANYUE_CHARACTER_BRIDGE_URL", "http://127.0.0.1:8893"),
                timeout=float(os.environ.get("TANYUE_CHARACTER_BRIDGE_TIMEOUT", "0.35")),
            )
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.info("Character bridge disabled: %s", exc)
        return None


def build_server():
    from livekit import agents
    from livekit.agents import AgentServer, AgentSession, JobExecutorType, inference
    from livekit.plugins import openai
    import httpx
    import openai as openai_sdk

    api_key = dashscope_api_key()
    motion_manifest = load_motion_manifest()
    cosyvoice = AliyunCosyVoiceTTS(config_from_env(api_key=api_key))
    if cosyvoice.config.clone_enabled:
        cosyvoice.ensure_cloned_voice()
    stt_provider = os.environ.get("TANYUE_STT_PROVIDER", "aliyun").lower()
    executor_name = os.environ.get("TANYUE_AGENT_EXECUTOR", "thread").lower()
    executor_type = JobExecutorType.PROCESS if executor_name == "process" else JobExecutorType.THREAD
    server = AgentServer(
        job_executor_type=executor_type,
        port=int(os.environ.get("TANYUE_AGENT_HTTP_PORT", "0")),
        load_threshold=float(os.environ.get("TANYUE_AGENT_LOAD_THRESHOLD", "inf")),
        num_idle_processes=int(os.environ.get("TANYUE_AGENT_IDLE_RUNNERS", "1")),
    )

    @server.rtc_session(agent_name=os.environ.get("TANYUE_LIVEKIT_AGENT_NAME", "tanyue"))
    async def tanyue_agent(ctx: agents.JobContext):
        assistant_factory = TanyueAssistant(motion_manifest).cls
        if stt_provider == "aliyun":
            stt_config = stt_config_from_env(api_key=api_key)
            stt_model = AliyunRealtimeSTT(stt_config)
        else:
            stt_config = None
            stt_model = inference.STT(
                model=os.environ.get("TANYUE_STT_MODEL", "deepgram/nova-3"),
                language=os.environ.get("TANYUE_STT_LANGUAGE", "zh"),
            )

        LOGGER.info(
            (
                "Tanyue job accepted: room=%s stt_provider=%s stt_model=%s "
                "mode=meme_play qwen_model=%s qwen_thinking=%s qwen_max_tokens=%s cosyvoice_model=%s voice=%s"
            ),
            getattr(ctx.room, "name", "unknown"),
            stt_provider,
            getattr(stt_config, "model", os.environ.get("TANYUE_STT_MODEL", "deepgram/nova-3")),
            os.environ.get("TANYUE_QWEN_MODEL", "qwen3.6-flash"),
            env_bool("TANYUE_QWEN_ENABLE_THINKING", False),
            os.environ.get("TANYUE_QWEN_MAX_COMPLETION_TOKENS", "48"),
            cosyvoice.config.model,
            cosyvoice.config.voice,
        )

        session = AgentSession(
            stt=stt_model,
            llm=openai.LLM(
                client=openai_sdk.AsyncClient(
                    api_key=api_key,
                    base_url=os.environ.get(
                        "TANYUE_QWEN_BASE_URL",
                        "https://dashscope.aliyuncs.com/compatible-mode/v1",
                    ),
                    max_retries=int(os.environ.get("TANYUE_QWEN_MAX_RETRIES", "1")),
                    http_client=httpx.AsyncClient(
                        trust_env=os.environ.get("TANYUE_QWEN_USE_ENV_PROXY", "0") in {"1", "true", "True"},
                        timeout=httpx.Timeout(connect=15.0, read=30.0, write=10.0, pool=5.0),
                    ),
                ),
                model=os.environ.get("TANYUE_QWEN_MODEL", "qwen3.6-flash"),
                temperature=float(os.environ.get("TANYUE_QWEN_TEMPERATURE", "0.6")),
                max_completion_tokens=int(os.environ.get("TANYUE_QWEN_MAX_COMPLETION_TOKENS", "48")),
                extra_body=qwen_extra_body(),
            ),
            min_endpointing_delay=float(os.environ.get("TANYUE_MIN_ENDPOINTING_DELAY", "1.1")),
            max_endpointing_delay=float(os.environ.get("TANYUE_MAX_ENDPOINTING_DELAY", "2.6")),
            allow_interruptions=env_bool("TANYUE_ALLOW_INTERRUPTION", False),
            min_interruption_duration=float(os.environ.get("TANYUE_MIN_INTERRUPTION_DURATION", "0.65")),
            min_interruption_words=int(os.environ.get("TANYUE_MIN_INTERRUPTION_WORDS", "2")),
            false_interruption_timeout=float(os.environ.get("TANYUE_FALSE_INTERRUPTION_TIMEOUT", "1.2")),
            resume_false_interruption=env_bool("TANYUE_RESUME_FALSE_INTERRUPTION", True),
            agent_false_interruption_timeout=float(
                os.environ.get("TANYUE_AGENT_FALSE_INTERRUPTION_TIMEOUT", "1.0")
            ),
        )

        await session.start(
            room=ctx.room,
            agent=assistant_factory(cosyvoice, ctx.room),
        )
        LOGGER.info("Tanyue session started: room=%s", getattr(ctx.room, "name", "unknown"))

    return agents, server


if __name__ == "__main__":
    agents, server = build_server()
    agents.cli.run_app(server)

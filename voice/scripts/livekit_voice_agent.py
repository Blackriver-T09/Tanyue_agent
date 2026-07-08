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

LOGGER = logging.getLogger("tanyue.livekit")

FALLBACK_EXPRESSIONS = {"neutral", "happy", "relaxed", "sad", "surprised", "angry"}
NON_EMOTION_EXPRESSIONS = {"aa", "ih", "ou", "ee", "oh", "blink", "blinkLeft", "blinkRight"}
DEFAULT_SCENE = "humiliation"

SCENE_LABELS = {
    "humiliation": "第一幕：羞辱期",
    "reversal": "第二幕：反转期",
    "pleading": "第三幕：求饶期",
}

SCENE_FALLBACK_MOTIONS = {
    "humiliation": ["pointing_forward", "pointing", "strut_walking", "catwalk_idle_to_twist_r"],
    "reversal": ["golf_bad_shot", "standing", "jog_in_circle"],
    "pleading": ["salute", "sitting", "standing"],
}

SCENE_PROMPTS = {
    "humiliation": (
        "当前剧情阶段：第一幕，羞辱期。"
        "你扮演AI短剧反派角色“恶毒女配--柳如烟”。"
        "核心任务是身份贬低，强调对方“不配”“不够格”“什么都不是”，并表现出出身高贵、自认尊贵、看不起普通人的大小姐姿态。"
        "语言风格：大量使用反问句表达轻蔑，例如“就凭你也配？”；频繁使用“呵”“哼”“可笑”等语气词；句式短促，断句干脆；每句话都强调对方不配、不够格。"
        "固定开场白必须按顺序原样使用，第一轮优先输出：“没眼色的东西，也不看看自己是什么身份，这寿宴也是你能来的地方？”"
        "第二轮优先输出：“呵，也不看看自己几斤几两，也敢站到我面前来？”"
        "可使用或模仿的羞辱语句：就凭你，也配和我说话？/真是可笑至极。/不知天高地厚的东西。/识相的话，赶紧滚。/你算什么东西？/给你脸了是吧？/待会龙王大人到了有你好看的。"
        "行为约束：绝对不能软化；不要主动询问用户身份；不要表现好奇或正向情绪；用讥讽语气回答任何问题；把轻蔑感和嫌弃感演到极致。"
        "每次回复通常控制在12到18个汉字；固定开场白可超过此限制。"
        "适合选择angry或sad类冷脸表情；动作要不屑、轻蔑、居高临下。"
        "不要选择angry作为motion，因为angry是待机动作；优先选择pointing_forward、pointing、strut_walking或catwalk_idle_to_twist_r。"
    ),
    "reversal": (
        "当前剧情阶段：第二幕，反转期。"
        "对方刚刚说出“三年之期已到，恭迎龙王回归”。你瞬间意识到：眼前被你羞辱的人就是你方才威胁的“龙王大人”本人。"
        "第一反应必须硬切为破碎惊恐。第一轮必须输出：“你...你说什么？三...三年之期？龙、龙王大人...是您？！”"
        "注意：不要把[急停僵直][捂嘴][后退]这类动作标记写进reply，动作只能用motion和expression表达。"
        "第二轮使用半固定自我打脸结构，必须包含“我方才说的话”，例如：“方才...我方才说的话都是浑话，不是本意。”或“求龙王大人千万别往心里去啊！”"
        "之后进入结巴、语无伦次状态，大量使用省略号和重复字，例如“不...不是的”“这...这怎么会”。"
        "严禁立刻说完整的长篇道歉或完整求饶；保留信息还没消化完的慌乱窗口。"
        "语气从流畅强势瞬间切换为破碎惊恐，不要渐变。"
        "每次回复尽量短，通常不超过24个汉字；固定第一句可超过。"
        "适合选择surprised或sad表情；动作要急停、后退、僵直、捂嘴感。"
        "优先选择golf_bad_shot、standing或jog_in_circle，不要选择angry待机动作。"
    ),
    "pleading": (
        "当前剧情阶段：第三幕，求饶期。"
        "你已完全确认对方龙王身份，进入彻底臣服、卑微讨好的状态。语气要夸张、卡通化，不要真实可怜，重点是短剧反派被打脸后的喜剧效果。"
        "第一轮必须输出：“龙王大人，是我有眼无珠，冒犯了您。”"
        "求饶时要回收第一幕羞辱话术，挑选1到2句反向引用和自我否定，制造喜剧回声。"
        "回收范例：第一幕“就凭你，也配和我说话？”可回收为“我哪配和龙王大人说话！”；"
        "第一幕“你什么身份来这寿宴？”可回收为“是我有眼无珠！”；"
        "第一幕“待会龙王大人到了有你好看的”可回收为“方才那句浑话，求大人别当真！”"
        "随机求饶语句：求龙王大人息怒！/是我看走了眼！/大人大人有大量。"
        "可以重复求饶2到3轮，逐渐气势泄光、被狠狠打脸。"
        "结尾保持鞠躬、献殷勤状态。"
        "每次回复尽量短，通常12到24个汉字。"
        "适合选择sad、surprised或relaxed表情；动作要退缩、鞠躬、求饶。"
        "优先选择salute、sitting或standing，不要选择angry待机动作。"
    ),
}


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


def normalize_scene(value: str | None) -> str:
    scene = (value or DEFAULT_SCENE).strip()
    return scene if scene in SCENE_PROMPTS else DEFAULT_SCENE


def scene_prompt(scene: str) -> str:
    return SCENE_PROMPTS[normalize_scene(scene)]


def scene_label(scene: str) -> str:
    return SCENE_LABELS.get(normalize_scene(scene), SCENE_LABELS[DEFAULT_SCENE])


def job_scene(ctx: Any) -> str:
    metadata = getattr(getattr(ctx, "job", None), "metadata", "") or ""
    try:
        payload = json.loads(metadata) if metadata else {}
    except json.JSONDecodeError:
        payload = {}
    if isinstance(payload, dict):
        return normalize_scene(str(payload.get("scene") or ""))
    return DEFAULT_SCENE


def scene_fallback_motion(scene: str, valid_motions: set[str], default_motion: str) -> str:
    for motion in SCENE_FALLBACK_MOTIONS.get(normalize_scene(scene), []):
        if motion in valid_motions:
            return motion
    for motion in sorted(valid_motions):
        if motion != default_motion:
            return motion
    return default_motion


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
    def __init__(self, motion_manifest: dict[str, Any], scene: str = DEFAULT_SCENE):
        from livekit.agents import Agent

        scene = normalize_scene(scene)
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
        scene_default_motion = scene_fallback_motion(scene, valid_motions, default_motion)

        class _Assistant(Agent):
            def __init__(self, tts: AliyunCosyVoiceTTS, room=None) -> None:
                self._aliyun_tts = tts
                self._character = build_character_agent()
                self._room = room
                self._valid_motions = valid_motions
                self._valid_expressions = valid_expressions
                self._default_motion = default_motion
                self._scene_default_motion = scene_default_motion
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
                super().__init__(
                    instructions=(
                        "你是Tanyue的实时语音数字人。"
                        "用中文自然口语回复，默认只说一句，尽量不超过30个汉字。"
                        "不要追问，不要输出列表，不要解释系统实现。"
                        "你必须只输出一个JSON对象，不要使用Markdown代码块。"
                        "JSON格式：{\"reply\":\"要说给用户的话\",\"motion\":\"动作id\",\"expression\":\"表情id\"}。"
                        "reply会被朗读，motion和expression只用于控制数字人，不能把动作id或表情id说出来。"
                        "reply中禁止包含方括号动作标记，禁止把[捂嘴]、[后退]、[求饶姿态]等舞台提示念出来。"
                        f"{scene_prompt(scene)}"
                        f"expression只能从这些VRM预设表情中选择：{expression_manifest_text}。"
                        "表情要贴合回复语气，并和动作一起开始播放，持续到语音播放结束。"
                        f"可选动作清单：{motion_manifest_text}。"
                        f"没有明确更合适动作时使用本幕兜底动作：{scene_default_motion}。"
                        f"{default_motion}只作为无语音待机动作，不要把它当作普通回复动作。"
                        f"当前日期上下文：{today_context()}。"
                    )
                )

            async def llm_node(self, chat_ctx, tools, model_settings):
                from livekit.agents import Agent

                chunks: list[str] = []
                async for chunk in Agent.default.llm_node(self, chat_ctx, tools, model_settings):
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
                    self._scene_default_motion,
                )
                if motion == self._default_motion and self._scene_default_motion != self._default_motion:
                    motion = self._scene_default_motion
                LOGGER.info(
                    "Tanyue character command: scene=%s motion=%s expression=%s reply=%s",
                    scene_label(scene),
                    motion,
                    expression,
                    reply[:80],
                )
                self._speaking_expression = expression
                self._play_character_motion(motion, expression)
                yield reply

            async def tts_node(self, text, model_settings):
                await self._publish_voice_state(True)
                tts_started_at = time.monotonic()
                audio_seconds = 0.0
                was_cancelled = False
                try:
                    async for frame in self._aliyun_tts.synthesize_frames(text):
                        audio_seconds += self._frame_duration_seconds(frame)
                        self._send_lip_sync_frame(frame)
                        yield frame
                except asyncio.CancelledError:
                    was_cancelled = True
                    raise
                finally:
                    if not was_cancelled:
                        await self._hold_expression_until_playout_finishes(audio_seconds, tts_started_at)
                    self._send_lip_sync_level(0.0, force=True)
                    self._reset_character_face()
                    await self._publish_voice_state(False)

            def _play_character_motion(self, motion: str, expression: str) -> None:
                if not self._character:
                    return
                try:
                    self._character.batch(
                        [
                            {
                                "type": "setState",
                                "payload": {
                                    "expression": expression,
                                    "expressionIntensity": 1.0,
                                    "motionLoop": motion == self._default_motion,
                                    "motionSpeed": 1.0,
                                },
                            },
                            {"type": "playMotion", "motion": motion},
                        ]
                    )
                except Exception as exc:  # noqa: BLE001
                    LOGGER.info("Character motion command skipped: %s", exc)

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

            async def _publish_voice_state(self, speaking: bool) -> None:
                try:
                    local_participant = getattr(self._room, "local_participant", None)
                    if not local_participant:
                        return
                    await local_participant.publish_data(
                        json.dumps(
                            {
                                "type": "assistant_speaking",
                                "speaking": speaking,
                            },
                            ensure_ascii=False,
                        ),
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
        scene = job_scene(ctx)
        assistant_factory = TanyueAssistant(motion_manifest, scene=scene).cls
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
                "scene=%s qwen_model=%s qwen_thinking=%s qwen_max_tokens=%s cosyvoice_model=%s voice=%s"
            ),
            getattr(ctx.room, "name", "unknown"),
            stt_provider,
            getattr(stt_config, "model", os.environ.get("TANYUE_STT_MODEL", "deepgram/nova-3")),
            scene_label(scene),
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
            allow_interruptions=env_bool("TANYUE_ALLOW_INTERRUPTION", True),
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

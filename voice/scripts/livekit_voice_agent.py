#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import importlib
import logging
from datetime import datetime
from pathlib import Path

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


class TanyueAssistant:
    def __init__(self):
        from livekit.agents import Agent

        class _Assistant(Agent):
            def __init__(self, tts: AliyunCosyVoiceTTS) -> None:
                self._aliyun_tts = tts
                super().__init__(
                    instructions=(
                        "你是Tanyue的实时语音数字人。"
                        "用中文自然口语回复，默认只说一句，尽量不超过30个汉字。"
                        "不要追问，不要输出列表，不要解释系统实现。"
                        f"当前日期上下文：{today_context()}。"
                    )
                )

            async def tts_node(self, text, model_settings):
                async for frame in self._aliyun_tts.synthesize_frames(text):
                    yield frame

        self.cls = _Assistant


def build_server():
    from livekit import agents
    from livekit.agents import AgentServer, AgentSession, JobExecutorType, inference
    from livekit.plugins import openai
    import httpx
    import openai as openai_sdk

    api_key = dashscope_api_key()
    assistant_factory = TanyueAssistant().cls
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
                "qwen_model=%s qwen_thinking=%s qwen_max_tokens=%s cosyvoice_model=%s voice=%s"
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
            agent=assistant_factory(cosyvoice),
        )
        LOGGER.info("Tanyue session started: room=%s", getattr(ctx.room, "name", "unknown"))

    return agents, server


if __name__ == "__main__":
    agents, server = build_server()
    agents.cli.run_app(server)

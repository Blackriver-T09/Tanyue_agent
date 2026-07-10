from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol


DEFAULT_API_VERSION = "2024-12-01-preview"
DEFAULT_DEPLOYMENT_NAME = "gpt-5"


class AzureClientFactory(Protocol):
    def __call__(self, **kwargs): ...


@dataclass(frozen=True)
class AzureInferenceConfig:
    azure_endpoint: str
    api_key: str
    api_version: str = DEFAULT_API_VERSION
    deployment_name: str = DEFAULT_DEPLOYMENT_NAME

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        deployment_name: str | None = None,
    ) -> "AzureInferenceConfig":
        values = env or os.environ
        endpoint = values.get("AZURE_API_BASE") or values.get("AZURE_OPENAI_ENDPOINT")
        api_key = values.get("AZURE_API_KEY") or values.get("AZURE_OPENAI_API_KEY")
        api_version = values.get("AZURE_API_VERSION", DEFAULT_API_VERSION)
        deployment = (
            deployment_name
            or values.get("AZURE_DEPLOYMENT_NAME")
            or values.get("AZURE_OPENAI_DEPLOYMENT")
            or DEFAULT_DEPLOYMENT_NAME
        )

        if not endpoint:
            raise ValueError("AZURE_API_BASE or AZURE_OPENAI_ENDPOINT is required")
        if not api_key:
            raise ValueError("AZURE_API_KEY or AZURE_OPENAI_API_KEY is required")

        return cls(
            azure_endpoint=_normalize_azure_endpoint(endpoint),
            api_key=api_key,
            api_version=api_version,
            deployment_name=deployment,
        )


def azure_inference(
    system_prompt: str,
    user_input: str,
    deployment_name: str | None = None,
    config: AzureInferenceConfig | None = None,
    client_factory: AzureClientFactory | None = None,
) -> str:
    config = config or AzureInferenceConfig.from_env(deployment_name=deployment_name)
    if deployment_name:
        config = AzureInferenceConfig(
            azure_endpoint=config.azure_endpoint,
            api_key=config.api_key,
            api_version=config.api_version,
            deployment_name=deployment_name,
        )

    if client_factory is None:
        from openai import AzureOpenAI

        factory: Callable[..., object] = AzureOpenAI
    else:
        factory = client_factory
    client = factory(
        api_key=config.api_key,
        api_version=config.api_version,
        azure_endpoint=config.azure_endpoint,
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input},
    ]
    response = client.chat.completions.create(
        model=config.deployment_name,
        messages=messages,
    )
    return response.choices[0].message.content or ""


def _normalize_azure_endpoint(endpoint: str) -> str:
    endpoint = endpoint.strip()
    markdown_match = re.fullmatch(r"\[([^\]]+)\]\([^)]+\)", endpoint)
    if markdown_match:
        endpoint = markdown_match.group(1)
    return endpoint.rstrip("/")

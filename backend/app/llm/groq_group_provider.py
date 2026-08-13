"""Experimental Groq adapter for the bounded whole-group advisory contract."""

import json

import httpx

from app.core.config import Settings
from app.llm.exceptions import LLMProviderConfigurationError
from app.llm.groq_provider import GroqLLMProvider
from app.llm.group_contracts import GroupAdvisoryRequest
from app.llm.group_execution import (
    DisabledGroupAdvisoryProvider,
    RawGroupProviderResponse,
    build_group_advisory_messages,
)


class GroqGroupAdvisoryProvider:
    """Map generic group messages onto the existing tested Groq JSON transport."""

    provider_id = "groq"
    enabled = True

    def __init__(self, transport: GroqLLMProvider) -> None:
        self._transport = transport
        self.provider_model = transport.model

    def request_bytes(self, request: GroupAdvisoryRequest) -> int:
        """Size the secret-free Groq JSON payload before transport."""
        messages = build_group_advisory_messages(request)
        payload = {
            "model": self.provider_model,
            "messages": [
                {"role": "system", "content": messages.system_prompt},
                {"role": "user", "content": messages.user_prompt},
            ],
            "stream": False,
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        return len(json.dumps(
            payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8"))

    async def execute(
        self, request: GroupAdvisoryRequest
    ) -> RawGroupProviderResponse:
        messages = build_group_advisory_messages(request)
        result = await self._transport.complete_json(
            system_prompt=messages.system_prompt,
            user_prompt=messages.user_prompt,
        )
        return RawGroupProviderResponse(
            provider_id=self.provider_id,
            provider_model=result.model,
            content=result.content,
            request_id=result.request_id,
            usage=result.usage,
        )


def create_group_advisory_provider(
    configuration: Settings, *, client: httpx.AsyncClient | None = None
):
    """Explicit group factory; pair provider settings never activate this path."""
    if configuration.group_llm_provider == "none":
        return DisabledGroupAdvisoryProvider()
    if not configuration.groq_api_key.get_secret_value().strip():
        raise LLMProviderConfigurationError(
            "Groq group benchmark is enabled but provider configuration is unavailable"
        )
    return GroqGroupAdvisoryProvider(GroqLLMProvider(
        api_key=configuration.groq_api_key,
        model=configuration.group_llm_model,
        timeout_seconds=configuration.llm_timeout_seconds,
        client=client,
    ))

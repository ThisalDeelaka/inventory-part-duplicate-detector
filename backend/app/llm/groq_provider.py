import json
import re
from typing import Any

import httpx
from pydantic import SecretStr

from app.llm.exceptions import (
    LLMProviderEmptyResponseError,
    LLMProviderHTTPError,
    LLMProviderMalformedJSONError,
    LLMProviderResponseStructureError,
    LLMProviderTimeoutError,
)
from app.llm.provider import LLMProviderResult, LLMUsageMetadata


GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"
_CODE_FENCE = re.compile(
    r"^```(?:json)?\s*\n?(.*?)\n?```$", re.IGNORECASE | re.DOTALL
)


def _strip_surrounding_code_fence(content: str) -> str:
    match = _CODE_FENCE.fullmatch(content.strip())
    return match.group(1).strip() if match else content.strip()


def _usage_from(payload: Any) -> LLMUsageMetadata | None:
    if not isinstance(payload, dict):
        return None
    allowed = {
        key: value
        for key, value in payload.items()
        if key in {"prompt_tokens", "completion_tokens", "total_tokens"}
        and isinstance(value, int)
        and value >= 0
    }
    return LLMUsageMetadata(**allowed) if allowed else None


class GroqLLMProvider:
    """Groq JSON transport only; scan integration and business prompts are deferred."""

    provider_name = "groq"

    def __init__(
        self,
        *,
        api_key: SecretStr,
        model: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._client = client

    async def complete_json(
        self, *, system_prompt: str, user_prompt: str
    ) -> LLMProviderResult:
        request = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "response_format": {"type": "json_object"},
            "temperature": 0,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }
        transport_error = None
        try:
            if self._client is None:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        GROQ_CHAT_COMPLETIONS_URL,
                        headers=headers,
                        json=request,
                        timeout=self.timeout_seconds,
                    )
            else:
                response = await self._client.post(
                    GROQ_CHAT_COMPLETIONS_URL,
                    headers=headers,
                    json=request,
                    timeout=self.timeout_seconds,
                )
        except httpx.TimeoutException:
            transport_error = LLMProviderTimeoutError(
                "LLM provider request timed out"
            )
        except httpx.RequestError:
            transport_error = LLMProviderHTTPError(
                "LLM provider transport failed"
            )

        if transport_error is not None:
            raise transport_error from None

        if not 200 <= response.status_code < 300:
            raise LLMProviderHTTPError(
                f"LLM provider returned HTTP status {response.status_code}"
            )
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise LLMProviderResponseStructureError(
                "LLM provider returned an invalid response envelope"
            ) from exc
        if not isinstance(payload, dict):
            raise LLMProviderResponseStructureError(
                "LLM provider response must be an object"
            )
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMProviderResponseStructureError(
                "LLM provider response is missing choices"
            )
        first_choice = choices[0]
        if not isinstance(first_choice, dict) or not isinstance(
            first_choice.get("message"), dict
        ):
            raise LLMProviderResponseStructureError(
                "LLM provider response is missing a message"
            )
        content = first_choice["message"].get("content")
        if content is None or (isinstance(content, str) and not content.strip()):
            raise LLMProviderEmptyResponseError(
                "LLM provider returned empty message content"
            )
        if not isinstance(content, str):
            raise LLMProviderResponseStructureError(
                "LLM provider message content must be text"
            )
        try:
            decoded = json.loads(_strip_surrounding_code_fence(content))
        except json.JSONDecodeError as exc:
            raise LLMProviderMalformedJSONError(
                "LLM provider message contained malformed JSON"
            ) from exc
        if not isinstance(decoded, dict):
            raise LLMProviderResponseStructureError(
                "LLM provider message JSON must be an object"
            )
        request_id = payload.get("id")
        if not isinstance(request_id, str):
            request_id = response.headers.get("x-request-id")
        if request_id is not None:
            request_id = request_id[:200]
        return LLMProviderResult(
            provider=self.provider_name,
            model=self.model,
            content=decoded,
            request_id=request_id,
            usage=_usage_from(payload.get("usage")),
        )

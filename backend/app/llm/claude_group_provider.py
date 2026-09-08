"""Claude Messages adapter for the provider-neutral whole-group advisory contract."""

import copy
import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from pydantic import SecretStr

from app.llm.exceptions import (
    LLMProviderEmptyResponseError,
    LLMProviderHTTPError,
    LLMProviderMalformedJSONError,
    LLMProviderNetworkError,
    LLMProviderResponseStructureError,
    LLMProviderTimeoutError,
)
from app.llm.group_contracts import GroupAdvisoryRequest
from app.llm.group_execution import (
    RawGroupProviderResponse,
    build_group_advisory_messages,
    group_advisory_structured_output_schema,
)
from app.llm.provider import LLMUsageMetadata


ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"

# Anthropic structured outputs do not accept these Pydantic-emitted bounds.
# They are removed only from the provider-facing copy; the authoritative local
# GroupAdvisoryResult parser retains and enforces every original constraint.
_UNSUPPORTED_SCHEMA_CONSTRAINTS = {
    "minimum": "minimum",
    "maximum": "maximum",
    "exclusiveMinimum": "exclusive minimum",
    "exclusiveMaximum": "exclusive maximum",
    "minLength": "minimum length",
    "maxLength": "maximum length",
    "minItems": "minimum items",
    "maxItems": "maximum items",
}


def _anthropic_compatible_schema_node(value: Any) -> Any:
    if isinstance(value, list):
        return [_anthropic_compatible_schema_node(item) for item in value]
    if not isinstance(value, dict):
        return value
    output = {}
    constraints = []
    for key, item in value.items():
        label = _UNSUPPORTED_SCHEMA_CONSTRAINTS.get(key)
        if label is not None:
            constraints.append(f"Authoritative local constraint: {label} {item}.")
        else:
            output[key] = _anthropic_compatible_schema_node(item)
    if constraints:
        existing = output.get("description")
        output["description"] = " ".join(
            ([existing] if isinstance(existing, str) and existing else []) + constraints
        )
    return output


def anthropic_group_structured_output_schema() -> dict[str, Any]:
    """Return a Claude-compatible copy derived from the authoritative schema."""
    authoritative = copy.deepcopy(group_advisory_structured_output_schema())
    return _anthropic_compatible_schema_node(authoritative)


def _safe_retry_after_seconds(value: str | None) -> float | None:
    if not value or len(value) > 128:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            seconds = (retry_at - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    return min(300.0, max(0.0, seconds))


def _non_negative_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _usage_from(value: Any) -> LLMUsageMetadata | None:
    if not isinstance(value, dict):
        return None
    input_tokens = _non_negative_int(value.get("input_tokens"))
    output_tokens = _non_negative_int(value.get("output_tokens"))
    cache_creation = _non_negative_int(value.get("cache_creation_input_tokens"))
    cache_read = _non_negative_int(value.get("cache_read_input_tokens"))
    values = [input_tokens, output_tokens, cache_creation, cache_read]
    if all(item is None for item in values):
        return None
    total = sum(item or 0 for item in values)
    return LLMUsageMetadata(
        prompt_tokens=input_tokens,
        completion_tokens=output_tokens,
        total_tokens=total,
        cache_creation_input_tokens=cache_creation,
        cache_read_input_tokens=cache_read,
    )


class ClaudeGroupAdvisoryProvider:
    """Map generic group messages onto Anthropic's structured Messages API."""

    provider_id = "claude"
    enabled = True

    def __init__(
        self,
        *,
        api_key: SecretStr,
        model: str,
        max_tokens: int,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self.provider_model = model
        self.max_tokens = max_tokens
        self.timeout_seconds = timeout_seconds
        self._client = client

    def _request_payload(self, request: GroupAdvisoryRequest) -> dict[str, Any]:
        messages = build_group_advisory_messages(request)
        return {
            "model": self.provider_model,
            "max_tokens": self.max_tokens,
            "system": messages.system_prompt,
            "messages": [{"role": "user", "content": messages.user_prompt}],
            "output_config": {
                "format": {
                    "type": "json_schema",
                    "schema": anthropic_group_structured_output_schema(),
                }
            },
        }

    def request_bytes(self, request: GroupAdvisoryRequest) -> int:
        """Measure only the secret-free serialized Messages body."""
        return len(json.dumps(
            self._request_payload(request),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"))

    async def execute(
        self, request: GroupAdvisoryRequest
    ) -> RawGroupProviderResponse:
        payload = self._request_payload(request)
        headers = {
            "x-api-key": self._api_key.get_secret_value(),
            "anthropic-version": ANTHROPIC_API_VERSION,
            "content-type": "application/json",
        }
        try:
            if self._client is None:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        ANTHROPIC_MESSAGES_URL,
                        headers=headers,
                        json=payload,
                        timeout=self.timeout_seconds,
                    )
            else:
                response = await self._client.post(
                    ANTHROPIC_MESSAGES_URL,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout_seconds,
                )
        except httpx.TimeoutException:
            raise LLMProviderTimeoutError("LLM provider request timed out") from None
        except httpx.RequestError:
            raise LLMProviderNetworkError("LLM provider transport failed") from None

        if not 200 <= response.status_code < 300:
            raise LLMProviderHTTPError(
                f"LLM provider returned HTTP status {response.status_code}",
                status_code=response.status_code,
                retry_after_seconds=_safe_retry_after_seconds(
                    response.headers.get("retry-after")
                ),
            )
        try:
            envelope = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise LLMProviderResponseStructureError(
                "LLM provider returned an invalid response envelope"
            ) from exc
        if not isinstance(envelope, dict):
            raise LLMProviderResponseStructureError(
                "LLM provider response must be an object"
            )
        if envelope.get("type") != "message" or envelope.get("role") != "assistant":
            raise LLMProviderResponseStructureError(
                "LLM provider returned an unexpected response envelope"
            )
        if envelope.get("stop_reason") != "end_turn":
            raise LLMProviderResponseStructureError(
                "LLM provider response did not complete normally"
            )
        blocks = envelope.get("content")
        if not isinstance(blocks, list) or not blocks:
            raise LLMProviderEmptyResponseError(
                "LLM provider returned no result content"
            )
        if len(blocks) != 1 or not isinstance(blocks[0], dict):
            raise LLMProviderResponseStructureError(
                "LLM provider returned ambiguous result content"
            )
        block = blocks[0]
        content = block.get("text")
        if block.get("type") != "text" or not isinstance(content, str):
            raise LLMProviderResponseStructureError(
                "LLM provider result content must be one text block"
            )
        if not content.strip():
            raise LLMProviderEmptyResponseError(
                "LLM provider returned empty result content"
            )
        try:
            decoded = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMProviderMalformedJSONError(
                "LLM provider result contained malformed JSON"
            ) from exc
        if not isinstance(decoded, dict):
            raise LLMProviderResponseStructureError(
                "LLM provider result JSON must be an object"
            )
        request_id = response.headers.get("request-id")
        if request_id is not None:
            request_id = request_id[:200]
        return RawGroupProviderResponse(
            provider_id=self.provider_id,
            provider_model=self.provider_model,
            content=decoded,
            request_id=request_id,
            usage=_usage_from(envelope.get("usage")),
        )

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class LLMUsageMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cache_creation_input_tokens: int | None = Field(default=None, ge=0)
    cache_read_input_tokens: int | None = Field(default=None, ge=0)


class LLMProviderResult(BaseModel):
    """Transport-only result; deterministic duplicate results remain authoritative."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=50)
    model: str = Field(min_length=1, max_length=200)
    content: dict[str, Any]
    request_id: str | None = Field(default=None, max_length=200)
    usage: LLMUsageMetadata | None = None


class LLMProvider(Protocol):
    """Provider-neutral async transport; business prompts are intentionally deferred."""

    async def complete_json(
        self, *, system_prompt: str, user_prompt: str
    ) -> LLMProviderResult:
        ...

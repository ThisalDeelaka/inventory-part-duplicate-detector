from app.llm.exceptions import LLMProviderDisabledError
from app.llm.provider import LLMProviderResult


class DisabledLLMProvider:
    """Network-free provider used while optional LLM support is disabled."""

    async def complete_json(
        self, *, system_prompt: str, user_prompt: str
    ) -> LLMProviderResult:
        del system_prompt, user_prompt
        raise LLMProviderDisabledError("LLM assistance is disabled")

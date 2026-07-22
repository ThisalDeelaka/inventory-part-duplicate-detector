import httpx

from app.core.config import Settings
from app.llm.disabled_provider import DisabledLLMProvider
from app.llm.exceptions import LLMProviderConfigurationError
from app.llm.groq_provider import GroqLLMProvider
from app.llm.provider import LLMProvider


def create_llm_provider(
    configuration: Settings, *, client: httpx.AsyncClient | None = None
) -> LLMProvider:
    """Build a provider on demand without changing deterministic application startup."""

    if not configuration.llm_demo_enabled:
        return DisabledLLMProvider()
    if configuration.llm_provider == "none":
        raise LLMProviderConfigurationError(
            "LLM assistance is enabled but no provider is configured"
        )
    if not configuration.groq_api_key.get_secret_value().strip():
        raise LLMProviderConfigurationError(
            "Groq is enabled but its API key is not configured"
        )
    return GroqLLMProvider(
        api_key=configuration.groq_api_key,
        model=configuration.groq_model,
        timeout_seconds=configuration.llm_timeout_seconds,
        client=client,
    )

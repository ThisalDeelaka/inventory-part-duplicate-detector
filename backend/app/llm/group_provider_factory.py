"""Explicit provider selection for benchmark-only whole-group advisory."""

import httpx

from app.core.config import Settings
from app.llm.claude_group_provider import ClaudeGroupAdvisoryProvider
from app.llm.exceptions import LLMProviderConfigurationError
from app.llm.groq_group_provider import create_group_advisory_provider as create_groq
from app.llm.group_execution import DisabledGroupAdvisoryProvider


def create_group_advisory_provider(
    configuration: Settings, *, client: httpx.AsyncClient | None = None
):
    """Select exactly one group provider without pair-provider fallback."""
    selected = configuration.group_llm_provider
    if selected == "none":
        return DisabledGroupAdvisoryProvider()
    if selected == "groq":
        return create_groq(configuration, client=client)
    if selected == "claude":
        if not configuration.anthropic_api_key.get_secret_value().strip():
            raise LLMProviderConfigurationError(
                "Claude group benchmark is enabled but provider configuration is unavailable"
            )
        if not configuration.claude_group_model:
            raise LLMProviderConfigurationError(
                "Claude group benchmark requires an explicit model selection"
            )
        return ClaudeGroupAdvisoryProvider(
            api_key=configuration.anthropic_api_key,
            model=configuration.claude_group_model,
            max_tokens=configuration.claude_group_max_tokens,
            timeout_seconds=configuration.llm_timeout_seconds,
            client=client,
        )
    raise LLMProviderConfigurationError("Unsupported group advisory provider")

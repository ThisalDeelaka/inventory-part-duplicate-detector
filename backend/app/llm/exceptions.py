class LLMProviderError(Exception):
    """Base exception for secret-safe LLM provider failures."""


class LLMProviderDisabledError(LLMProviderError):
    """Raised when an unavailable provider is invoked."""


class LLMProviderConfigurationError(LLMProviderError):
    """Raised when enabled provider configuration is invalid."""


class LLMProviderTimeoutError(LLMProviderError):
    """Raised when the provider request exceeds its timeout."""


class LLMProviderHTTPError(LLMProviderError):
    """Raised for provider HTTP or transport failures."""

    def __init__(
        self,
        message: str = "LLM provider request failed",
        *,
        status_code: int | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


class LLMProviderNetworkError(LLMProviderHTTPError):
    """Raised when the provider cannot be reached over the network."""


class LLMProviderEmptyResponseError(LLMProviderError):
    """Raised when the provider returns no usable message content."""


class LLMProviderMalformedJSONError(LLMProviderError):
    """Raised when provider message content is not valid JSON."""


class LLMProviderResponseStructureError(LLMProviderError):
    """Raised when the provider response does not match the transport contract."""

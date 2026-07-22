import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.llm.disabled_provider import DisabledLLMProvider
from app.llm.exceptions import (
    LLMProviderConfigurationError,
    LLMProviderDisabledError,
    LLMProviderEmptyResponseError,
    LLMProviderHTTPError,
    LLMProviderMalformedJSONError,
    LLMProviderResponseStructureError,
    LLMProviderTimeoutError,
)
from app.llm.factory import create_llm_provider
from app.llm.groq_provider import GROQ_CHAT_COMPLETIONS_URL, GroqLLMProvider


def _response(content, **extra):
    return {"id": "request-1", "choices": [{"message": {"content": content}}], **extra}


def _run_provider(handler, *, timeout=7.5, api_key="test-secret"):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            provider = GroqLLMProvider(
                api_key=SecretStr(api_key),
                model="test-model",
                timeout_seconds=timeout,
                client=client,
            )
            return await provider.complete_json(
                system_prompt="system instructions", user_prompt="bounded input"
            )

    return asyncio.run(run())


def test_disabled_factory_constructs_no_client_and_invocation_fails(monkeypatch):
    def unexpected_client(*args, **kwargs):
        raise AssertionError("network client must not be created")

    monkeypatch.setattr(httpx, "AsyncClient", unexpected_client)
    provider = create_llm_provider(
        Settings(llm_demo_enabled=False, llm_provider="groq", groq_api_key="")
    )

    assert isinstance(provider, DisabledLLMProvider)
    with pytest.raises(LLMProviderDisabledError):
        asyncio.run(provider.complete_json(system_prompt="x", user_prompt="y"))


def test_ordinary_application_startup_has_no_provider_instance():
    from app import main as application_main

    provider_types = (DisabledLLMProvider, GroqLLMProvider)
    assert not any(
        isinstance(value, provider_types) for value in vars(application_main).values()
    )


def test_enabled_without_provider_fails_clearly():
    with pytest.raises(LLMProviderConfigurationError, match="no provider"):
        create_llm_provider(Settings(llm_demo_enabled=True, llm_provider="none"))


def test_enabled_groq_without_key_fails_without_exposing_secrets():
    with pytest.raises(LLMProviderConfigurationError) as caught:
        create_llm_provider(
            Settings(llm_demo_enabled=True, llm_provider="groq", groq_api_key="")
        )
    assert "authorization" not in str(caught.value).lower()


def test_enabled_groq_factory_uses_validated_configuration():
    provider = create_llm_provider(
        Settings(
            llm_demo_enabled=True,
            llm_provider="groq",
            groq_api_key="test-secret",
            groq_model="chosen-model",
            llm_timeout_seconds=9,
        )
    )

    assert isinstance(provider, GroqLLMProvider)
    assert provider.model == "chosen-model"
    assert provider.timeout_seconds == 9
    assert "test-secret" not in repr(provider._api_key)


def test_groq_request_and_plain_json_response_contract():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        captured["timeout"] = request.extensions["timeout"]
        return httpx.Response(
            200,
            json=_response(
                '{"answer":"ok"}',
                usage={"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
            ),
            headers={"x-ignored-secret": "not-captured"},
        )

    result = _run_provider(handler)

    assert captured["url"] == GROQ_CHAT_COMPLETIONS_URL
    assert captured["payload"]["model"] == "test-model"
    assert captured["payload"]["messages"] == [
        {"role": "system", "content": "system instructions"},
        {"role": "user", "content": "bounded input"},
    ]
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["temperature"] == 0
    assert set(captured["timeout"].values()) == {7.5}
    assert result.content == {"answer": "ok"}
    assert result.provider == "groq"
    assert result.model == "test-model"
    assert result.request_id == "request-1"
    assert result.usage.total_tokens == 5


def test_groq_decodes_one_surrounding_json_code_fence():
    result = _run_provider(
        lambda request: httpx.Response(200, json=_response('```json\n{"answer": "ok"}\n```'))
    )
    assert result.content == {"answer": "ok"}


@pytest.mark.parametrize("content", ["", "   ", None])
def test_groq_rejects_blank_or_missing_content(content):
    with pytest.raises(LLMProviderEmptyResponseError):
        _run_provider(lambda request: httpx.Response(200, json=_response(content)))


def test_groq_rejects_malformed_message_json():
    with pytest.raises(LLMProviderMalformedJSONError):
        _run_provider(
            lambda request: httpx.Response(200, json=_response("{not-json"))
        )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"choices": []},
        {"choices": [{}]},
        {"choices": [{"message": {"content": []}}]},
        _response("[]"),
    ],
)
def test_groq_rejects_unexpected_response_structures(payload):
    with pytest.raises(LLMProviderResponseStructureError):
        _run_provider(lambda request: httpx.Response(200, json=payload))


def test_groq_maps_non_success_status_without_response_or_secret_text():
    with pytest.raises(LLMProviderHTTPError) as caught:
        _run_provider(
            lambda request: httpx.Response(
                401, text="test-secret authorization rejected"
            )
        )
    assert "401" in str(caught.value)
    assert "test-secret" not in str(caught.value)
    assert "authorization" not in str(caught.value).lower()


def test_groq_transport_failure_discards_secret_bearing_exception_chain():
    sensitive_key = "highly-sensitive-test-key"

    def handler(request):
        assert request.headers["Authorization"] == f"Bearer {sensitive_key}"
        raise httpx.ConnectError("connection failed", request=request)

    with pytest.raises(LLMProviderHTTPError) as caught:
        _run_provider(handler, api_key=sensitive_key)

    error = caught.value
    assert str(error) == "LLM provider transport failed"
    assert sensitive_key not in str(error)
    assert sensitive_key not in repr(error)
    assert error.__cause__ is None
    assert error.__context__ is None


def test_groq_maps_httpx_timeout_distinctly():
    sensitive_key = "highly-sensitive-test-key"

    def handler(request):
        assert request.headers["Authorization"] == f"Bearer {sensitive_key}"
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(LLMProviderTimeoutError) as caught:
        _run_provider(handler, api_key=sensitive_key)

    error = caught.value
    assert str(error) == "LLM provider request timed out"
    assert sensitive_key not in str(error)
    assert sensitive_key not in repr(error)
    assert error.__cause__ is None
    assert error.__context__ is None

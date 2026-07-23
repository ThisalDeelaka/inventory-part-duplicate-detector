from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core import config as config_module
from app.core.config import Settings


LLM_ENVIRONMENT_VARIABLES = (
    "LLM_DEMO_ENABLED",
    "LLM_PROVIDER",
    "GROQ_API_KEY",
    "GROQ_MODEL",
    "LLM_TIMEOUT_SECONDS",
    "LLM_CACHE_ENABLED",
    "LLM_CACHE_MAX_ENTRIES",
    "LLM_CACHE_TTL_SECONDS",
    "LLM_AUDIT_ENABLED",
    "LLM_AUDIT_MAX_ENTRIES",
    "LLM_AUTO_TRIAGE_ENABLED",
    "LLM_TRIAGE_CONCURRENCY",
    "LLM_TRIAGE_MAX_CANDIDATES_PER_SCAN",
)
LEGACY_ENVIRONMENT_VARIABLES = (
    "MODEL_VERSION",
    "DEFAULT_THRESHOLD",
    "ENVIRONMENT",
    "MAX_UPLOAD_BYTES",
    "MAX_CSV_RECORDS",
    "DATABASE_URL",
    "CORS_ORIGINS",
    "CORS_ORIGIN_REGEX",
)


@pytest.fixture(autouse=True)
def clear_llm_environment(monkeypatch):
    for name in LLM_ENVIRONMENT_VARIABLES + LEGACY_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(name, raising=False)


def test_llm_settings_defaults_are_disabled_and_secret_safe():
    configuration = Settings()

    assert configuration.llm_demo_enabled is False
    assert configuration.llm_provider == "none"
    assert configuration.groq_model == "llama-3.3-70b-versatile"
    assert configuration.llm_timeout_seconds == 20
    assert configuration.groq_api_key.get_secret_value() == ""
    assert configuration.llm_cache_enabled is True
    assert configuration.llm_cache_max_entries == 256
    assert configuration.llm_cache_ttl_seconds == 3600
    assert configuration.llm_audit_enabled is True
    assert configuration.llm_audit_max_entries == 1000
    assert configuration.llm_auto_triage_enabled is True
    assert configuration.llm_triage_concurrency == 1
    assert configuration.llm_triage_max_candidates_per_scan == 250


def test_legacy_settings_defaults_remain_compatible():
    configuration = Settings()
    expected_database_path = (
        Path(config_module.__file__).resolve().parents[3] / "inventory_detector.db"
    )

    assert configuration.service_name == "inventory-part-duplicate-detector"
    assert configuration.model_version == "hybrid-nlp-v1"
    assert configuration.default_threshold == 75
    assert configuration.environment == "development"
    assert configuration.max_upload_bytes == 52428800
    assert configuration.max_csv_records == 100000
    assert configuration.database_url == f"sqlite:///{expected_database_path}"
    assert configuration.cors_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    assert configuration.cors_origin_regex == (
        r"http://(localhost|127\.0\.0\.1):\d+"
    )


def test_legacy_settings_environment_overrides_remain_compatible(monkeypatch):
    overrides = {
        "MODEL_VERSION": "legacy-model-override",
        "DEFAULT_THRESHOLD": "81.5",
        "ENVIRONMENT": "review",
        "MAX_UPLOAD_BYTES": "4096",
        "MAX_CSV_RECORDS": "250",
        "DATABASE_URL": "sqlite:///review.db",
        "CORS_ORIGINS": "https://one.example,https://two.example",
        "CORS_ORIGIN_REGEX": r"https://.*\.example",
    }
    for name, value in overrides.items():
        monkeypatch.setenv(name, value)

    configuration = Settings()
    assert configuration.model_version == "legacy-model-override"
    assert configuration.default_threshold == 81.5
    assert configuration.environment == "review"
    assert configuration.max_upload_bytes == 4096
    assert configuration.max_csv_records == 250
    assert configuration.database_url == "sqlite:///review.db"
    assert configuration.cors_origins == [
        "https://one.example",
        "https://two.example",
    ]
    assert configuration.cors_origin_regex == r"https://.*\.example"

    for name in LEGACY_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    reset = Settings()
    expected_database_path = (
        Path(config_module.__file__).resolve().parents[3] / "inventory_detector.db"
    )
    assert reset.service_name == "inventory-part-duplicate-detector"
    assert reset.model_version == "hybrid-nlp-v1"
    assert reset.default_threshold == 75
    assert reset.environment == "development"
    assert reset.max_upload_bytes == 52428800
    assert reset.max_csv_records == 100000
    assert reset.database_url == f"sqlite:///{expected_database_path}"
    assert reset.cors_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    assert reset.cors_origin_regex == r"http://(localhost|127\.0\.0\.1):\d+"


def test_llm_settings_read_environment_for_each_new_instance(monkeypatch):
    monkeypatch.setenv("LLM_DEMO_ENABLED", "true")
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_MODEL", "test-model")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "7.5")
    monkeypatch.setenv("GROQ_API_KEY", "not-a-real-secret")

    overridden = Settings()
    assert overridden.llm_demo_enabled is True
    assert overridden.llm_provider == "groq"
    assert overridden.groq_model == "test-model"
    assert overridden.llm_timeout_seconds == 7.5
    assert "not-a-real-secret" not in repr(overridden)

    for name in LLM_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    assert Settings().llm_demo_enabled is False


def test_unsupported_provider_is_rejected():
    with pytest.raises(ValidationError):
        Settings(llm_provider="unsupported")


@pytest.mark.parametrize("timeout", [0, -1, 121])
def test_invalid_timeout_is_rejected(timeout):
    with pytest.raises(ValidationError):
        Settings(llm_timeout_seconds=timeout)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("llm_cache_max_entries", 0),
        ("llm_cache_max_entries", 4097),
        ("llm_cache_ttl_seconds", 0),
        ("llm_cache_ttl_seconds", 86401),
        ("llm_audit_max_entries", 0),
        ("llm_audit_max_entries", 10001),
    ],
)
def test_invalid_cache_and_audit_limits_are_rejected(field, value):
    with pytest.raises(ValidationError):
        Settings(**{field: value})


def test_cache_and_audit_environment_overrides_are_isolated(monkeypatch):
    monkeypatch.setenv("LLM_CACHE_ENABLED", "false")
    monkeypatch.setenv("LLM_CACHE_MAX_ENTRIES", "12")
    monkeypatch.setenv("LLM_CACHE_TTL_SECONDS", "45")
    monkeypatch.setenv("LLM_AUDIT_ENABLED", "false")
    monkeypatch.setenv("LLM_AUDIT_MAX_ENTRIES", "34")

    overridden = Settings()
    assert overridden.llm_cache_enabled is False
    assert overridden.llm_cache_max_entries == 12
    assert overridden.llm_cache_ttl_seconds == 45
    assert overridden.llm_audit_enabled is False
    assert overridden.llm_audit_max_entries == 34

    for name in LLM_ENVIRONMENT_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    reset = Settings()
    assert reset.llm_cache_enabled is True
    assert reset.llm_cache_max_entries == 256
    assert reset.llm_cache_ttl_seconds == 3600
    assert reset.llm_audit_enabled is True
    assert reset.llm_audit_max_entries == 1000

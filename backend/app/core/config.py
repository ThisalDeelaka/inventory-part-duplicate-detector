import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)

    service_name: str = "inventory-part-duplicate-detector"
    model_version: str = Field(
        default_factory=lambda: os.getenv("MODEL_VERSION", "hybrid-nlp-v1")
    )
    default_threshold: float = Field(
        default_factory=lambda: os.getenv("DEFAULT_THRESHOLD", "75")
    )
    environment: str = Field(
        default_factory=lambda: os.getenv("ENVIRONMENT", "development")
    )
    max_upload_bytes: int = Field(
        default_factory=lambda: os.getenv(
            "MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)
        )
    )
    max_csv_records: int = Field(
        default_factory=lambda: os.getenv("MAX_CSV_RECORDS", "100000")
    )
    database_url: str = Field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            f"sqlite:///{Path(__file__).resolve().parents[3] / 'inventory_detector.db'}",
        )
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
        ).split(",")
    )
    cors_origin_regex: str = Field(
        default_factory=lambda: os.getenv(
            "CORS_ORIGIN_REGEX", r"http://(localhost|127\.0\.0\.1):\d+"
        )
    )
    llm_demo_enabled: bool = Field(
        default_factory=lambda: os.getenv("LLM_DEMO_ENABLED", "false")
    )
    llm_provider: Literal["none", "groq"] = Field(
        default_factory=lambda: os.getenv("LLM_PROVIDER", "none")
    )
    groq_api_key: SecretStr = Field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    groq_model: str = Field(
        default_factory=lambda: os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        min_length=1,
        max_length=200,
    )
    llm_timeout_seconds: float = Field(
        default_factory=lambda: os.getenv("LLM_TIMEOUT_SECONDS", "20"), gt=0, le=120
    )
    llm_cache_enabled: bool = Field(
        default_factory=lambda: os.getenv("LLM_CACHE_ENABLED", "true")
    )
    llm_cache_max_entries: int = Field(
        default_factory=lambda: os.getenv("LLM_CACHE_MAX_ENTRIES", "256"),
        gt=0,
        le=4096,
    )
    llm_cache_ttl_seconds: float = Field(
        default_factory=lambda: os.getenv("LLM_CACHE_TTL_SECONDS", "3600"),
        gt=0,
        le=86400,
    )
    llm_audit_enabled: bool = Field(
        default_factory=lambda: os.getenv("LLM_AUDIT_ENABLED", "true")
    )
    llm_audit_max_entries: int = Field(
        default_factory=lambda: os.getenv("LLM_AUDIT_MAX_ENTRIES", "1000"),
        gt=0,
        le=10000,
    )
    llm_auto_triage_enabled: bool = Field(
        default_factory=lambda: os.getenv("LLM_AUTO_TRIAGE_ENABLED", "true")
    )
    llm_triage_concurrency: int = Field(
        default_factory=lambda: os.getenv("LLM_TRIAGE_CONCURRENCY", "1"),
        gt=0,
        le=8,
    )
    llm_triage_max_candidates_per_scan: int = Field(
        default_factory=lambda: os.getenv(
            "LLM_TRIAGE_MAX_CANDIDATES_PER_SCAN", "250"
        ),
        gt=0,
        le=1000,
    )
    llm_triage_min_interval_ms: int = Field(
        default_factory=lambda: os.getenv("LLM_TRIAGE_MIN_INTERVAL_MS", "1000"),
        ge=0,
        le=10000,
    )
    llm_triage_max_retries: int = Field(
        default_factory=lambda: os.getenv("LLM_TRIAGE_MAX_RETRIES", "2"),
        ge=0,
        le=5,
    )
    llm_triage_retry_batch_size: int = Field(
        default_factory=lambda: os.getenv("LLM_TRIAGE_RETRY_BATCH_SIZE", "20"),
        gt=0,
        le=100,
    )
    llm_triage_consecutive_failure_limit: int = Field(
        default_factory=lambda: os.getenv(
            "LLM_TRIAGE_CONSECUTIVE_FAILURE_LIMIT", "5"
        ),
        gt=0,
        le=20,
    )


settings = Settings()

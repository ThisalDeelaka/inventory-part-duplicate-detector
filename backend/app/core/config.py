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
    group_llm_provider: Literal["none", "groq", "claude"] = Field(
        default_factory=lambda: os.getenv("GROUP_LLM_PROVIDER", "none")
    )
    group_llm_model: str = Field(
        default_factory=lambda: os.getenv(
            "GROUP_LLM_MODEL",
            os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        ),
        min_length=1,
        max_length=200,
    )
    anthropic_api_key: SecretStr = Field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", "")
    )
    claude_group_model: str | None = Field(
        default_factory=lambda: os.getenv("CLAUDE_GROUP_MODEL") or None,
        min_length=1,
        max_length=200,
    )
    claude_group_max_tokens: int = Field(
        default_factory=lambda: os.getenv("CLAUDE_GROUP_MAX_TOKENS", "4096"),
        ge=256,
        le=16384,
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
    llm_semantic_enrichment_enabled: bool = Field(
        default_factory=lambda: os.getenv("LLM_SEMANTIC_ENRICHMENT_ENABLED", "true")
    )
    llm_semantic_enrichment_batch_size: int = Field(
        default_factory=lambda: os.getenv("LLM_SEMANTIC_ENRICHMENT_BATCH_SIZE", "12"),
        gt=0,
        le=20,
    )
    llm_semantic_enrichment_max_records_per_scan: int = Field(
        default_factory=lambda: os.getenv("LLM_SEMANTIC_ENRICHMENT_MAX_RECORDS_PER_SCAN", "200"),
        gt=0,
        le=500,
    )
    llm_semantic_enrichment_concurrency: int = Field(
        default_factory=lambda: os.getenv("LLM_SEMANTIC_ENRICHMENT_CONCURRENCY", "1"),
        gt=0,
        le=2,
    )
    llm_recall_rescue_enabled: bool = Field(
        default_factory=lambda: os.getenv("LLM_RECALL_RESCUE_ENABLED", "true")
    )
    llm_recall_rescue_top_k_per_row: int = Field(
        default_factory=lambda: os.getenv("LLM_RECALL_RESCUE_TOP_K_PER_ROW", "3"),
        gt=0,
        le=10,
    )
    llm_recall_rescue_max_candidates_per_scan: int = Field(
        default_factory=lambda: os.getenv("LLM_RECALL_RESCUE_MAX_CANDIDATES_PER_SCAN", "50"),
        gt=0,
        le=100,
    )
    llm_recall_rescue_pairwise_fallback_max: int = Field(
        default_factory=lambda: os.getenv("LLM_RECALL_RESCUE_PAIRWISE_FALLBACK_MAX", "10"),
        ge=0,
        le=25,
    )
    llm_recall_rescue_min_score: float = Field(
        default_factory=lambda: os.getenv("LLM_RECALL_RESCUE_MIN_SCORE", "62"),
        ge=50,
        lt=75,
    )
    hybrid_retrieval_enabled: bool = Field(
        default_factory=lambda: os.getenv("HYBRID_RETRIEVAL_ENABLED", "true")
    )
    hybrid_retrieval_lexical_top_k: int = Field(
        default_factory=lambda: os.getenv("HYBRID_RETRIEVAL_LEXICAL_TOP_K", "5"), gt=0, le=20
    )
    local_embedding_enabled: bool = Field(
        default_factory=lambda: os.getenv("LOCAL_EMBEDDING_ENABLED", "true")
    )
    local_embedding_model: str = Field(
        default_factory=lambda: os.getenv("LOCAL_EMBEDDING_MODEL", "sklearn-hashing-domain-v1"),
        min_length=1, max_length=200,
    )
    hybrid_retrieval_vector_top_k: int = Field(
        default_factory=lambda: os.getenv("HYBRID_RETRIEVAL_VECTOR_TOP_K", "5"), gt=0, le=20
    )
    hybrid_retrieval_vector_weight: float = Field(
        default_factory=lambda: os.getenv("HYBRID_RETRIEVAL_VECTOR_WEIGHT", "0.4"), ge=0, le=0.6
    )
    hybrid_retrieval_final_top_k: int = Field(
        default_factory=lambda: os.getenv("HYBRID_RETRIEVAL_FINAL_TOP_K", "10"), gt=0, le=30
    )
    hybrid_retrieval_min_score: float = Field(
        default_factory=lambda: os.getenv("HYBRID_RETRIEVAL_MIN_SCORE", "55"), ge=0, le=90
    )
    hybrid_retrieval_max_pairs_per_scan: int = Field(
        default_factory=lambda: os.getenv("HYBRID_RETRIEVAL_MAX_PAIRS_PER_SCAN", "500"), gt=0, le=5000
    )
    hybrid_retrieval_tier_a_max: int = Field(
        default_factory=lambda: os.getenv("HYBRID_RETRIEVAL_TIER_A_MAX", "250"), ge=0, le=5000
    )
    hybrid_retrieval_tier_b_max: int = Field(
        default_factory=lambda: os.getenv("HYBRID_RETRIEVAL_TIER_B_MAX", "200"), ge=0, le=5000
    )
    hybrid_retrieval_tier_c_max: int = Field(
        default_factory=lambda: os.getenv("HYBRID_RETRIEVAL_TIER_C_MAX", "50"), ge=0, le=5000
    )
    hybrid_retrieval_family_max: int = Field(
        default_factory=lambda: os.getenv("HYBRID_RETRIEVAL_FAMILY_MAX", "25"), gt=0, le=250
    )
    identity_neighborhood_max_members: int = Field(
        default_factory=lambda: os.getenv("IDENTITY_NEIGHBORHOOD_MAX_MEMBERS", "20"),
        ge=2,
        le=250,
    )
    group_first_shadow_comparison_enabled: bool = Field(
        default_factory=lambda: os.getenv(
            "GROUP_FIRST_SHADOW_COMPARISON_ENABLED", "false"
        )
    )
    identity_orchestration_mode: Literal[
        "legacy_primary", "group_first_primary"
    ] = Field(
        default_factory=lambda: os.getenv(
            "IDENTITY_ORCHESTRATION_MODE", "legacy_primary"
        )
    )


settings = Settings()

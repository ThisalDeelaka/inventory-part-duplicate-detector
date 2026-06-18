import os
from pathlib import Path


class Settings:
    service_name = "inventory-part-duplicate-detector"
    model_version = os.getenv("MODEL_VERSION", "hybrid-nlp-v1")
    default_threshold = float(os.getenv("DEFAULT_THRESHOLD", "75"))
    environment = os.getenv("ENVIRONMENT", "development")
    max_upload_bytes = int(os.getenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
    max_csv_records = int(os.getenv("MAX_CSV_RECORDS", "100000"))
    use_redesigned_engine = os.getenv("USE_REDESIGNED_ENGINE", "false").strip().lower() in {"1", "true", "yes", "on"}
    database_url = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{Path(__file__).resolve().parents[3] / 'inventory_detector.db'}",
    )
    cors_origins = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    cors_origin_regex = os.getenv(
        "CORS_ORIGIN_REGEX",
        r"http://(localhost|127\.0\.0\.1):\d+",
    )


settings = Settings()

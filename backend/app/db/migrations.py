from sqlalchemy import inspect, text


def ensure_sqlite_demo_columns(engine):
    """Small demo migration for existing SQLite databases.

    SQLAlchemy create_all creates fresh tables but does not add columns to an
    existing SQLite file. This keeps local/Docker demo databases compatible
    after schema additions without introducing Alembic for the demo.
    """
    if not engine.url.get_backend_name().startswith("sqlite"):
        return

    additions = {
        "duplicate_scan": [
            ("scan_mode", "VARCHAR(60) NOT NULL DEFAULT 'SAME_SITE_DUPLICATE'"),
        ],
        "duplicate_candidate": [
            ("business_status", "VARCHAR(80) NOT NULL DEFAULT 'POSSIBLE_DUPLICATE_REVIEW'"),
            ("rule_decision", "VARCHAR(50) NOT NULL DEFAULT 'ALLOW'"),
            ("rejection_reason", "VARCHAR(120) DEFAULT ''"),
            ("scan_mode", "VARCHAR(60) NOT NULL DEFAULT 'SAME_SITE_DUPLICATE'"),
            ("critical_mismatches", "TEXT DEFAULT '[]'"),
            ("variant_attributes_a", "TEXT DEFAULT '{}'"),
            ("variant_attributes_b", "TEXT DEFAULT '{}'"),
            ("generic_description_warning", "VARCHAR(10) DEFAULT 'false'"),
            ("application_context_a", "TEXT DEFAULT '[]'"),
            ("application_context_b", "TEXT DEFAULT '[]'"),
            ("application_context_warning", "VARCHAR(10) DEFAULT 'false'"),
            ("normalized_description_a", "TEXT DEFAULT ''"),
            ("normalized_description_b", "TEXT DEFAULT ''"),
            ("normalized_part_no_a", "TEXT DEFAULT ''"),
            ("normalized_part_no_b", "TEXT DEFAULT ''"),
        ],
    }

    inspector = inspect(engine)
    with engine.begin() as connection:
        for table, columns in additions.items():
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, ddl in columns:
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))

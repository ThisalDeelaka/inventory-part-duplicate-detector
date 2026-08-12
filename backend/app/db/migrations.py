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
            ("rejections_count", "INTEGER DEFAULT 0"),
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
        "candidate_discovery_metadata": [
            ("retrieval_sources_json", "TEXT NOT NULL DEFAULT '[]'"),
            ("retrieval_score", "FLOAT"),
            ("retrieval_priority", "FLOAT"),
            ("retrieval_tier", "VARCHAR(20)"),
            ("lexical_score", "FLOAT"),
            ("vector_score", "FLOAT"),
            ("description_specificity_score", "FLOAT"),
            ("generic_description_penalty", "FLOAT"),
            ("retrieval_conflict_signals_json", "TEXT NOT NULL DEFAULT '[]'"),
            ("reciprocal_sources_json", "TEXT NOT NULL DEFAULT '[]'"),
            ("uom_relationship", "VARCHAR(50)"),
            ("uom_evidence", "VARCHAR(80)"),
            ("uom_penalty", "FLOAT"),
            ("mapping_quality", "VARCHAR(40)"),
            ("retrieval_rank", "INTEGER"),
            ("embedding_model_version", "VARCHAR(200)"),
        ],
        "hybrid_retrieval_run": [
            ("exact_description_candidates", "INTEGER NOT NULL DEFAULT 0"),
            ("part_family_candidates", "INTEGER NOT NULL DEFAULT 0"),
            ("technical_identity_candidates", "INTEGER NOT NULL DEFAULT 0"),
            ("reciprocal_candidates", "INTEGER NOT NULL DEFAULT 0"),
            ("generic_penalized_candidates", "INTEGER NOT NULL DEFAULT 0"),
            ("conflict_penalized_candidates", "INTEGER NOT NULL DEFAULT 0"),
            ("uom_same_pairs_considered", "INTEGER"),
            ("uom_convertible_pairs_considered", "INTEGER"),
            ("uom_different_basis_pairs_considered", "INTEGER"),
            ("uom_missing_or_wildcard_pairs_considered", "INTEGER"),
            ("uom_malformed_or_unknown_pairs_considered", "INTEGER"),
            ("tier_a_candidates", "INTEGER NOT NULL DEFAULT 0"),
            ("tier_b_candidates", "INTEGER NOT NULL DEFAULT 0"),
            ("tier_c_candidates", "INTEGER NOT NULL DEFAULT 0"),
            ("hybrid_post_scoring_excluded_count", "INTEGER"),
            ("hybrid_post_scoring_exclusion_reasons_json", "TEXT"),
            ("hybrid_candidates_added_with_uom_difference", "INTEGER"),
            ("hybrid_candidates_added_with_uom_unknown", "INTEGER"),
            ("largest_description_family_candidates", "INTEGER NOT NULL DEFAULT 0"),
            ("candidate_family_concentration", "FLOAT NOT NULL DEFAULT 0"),
        ],
    }

    inspector = inspect(engine)
    with engine.begin() as connection:
        for table, columns in additions.items():
            existing = {column["name"] for column in inspector.get_columns(table)}
            for name, ddl in columns:
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def ensure_identity_group_snapshot_tables(engine):
    """Add the immutable G2 snapshot tables without backfilling historical scans."""
    from app.db.models import (
        IdentityFamilyDiagnosticMemberSnapshot,
        IdentityFamilyDiagnosticSnapshot,
        IdentityGroupEdgeSnapshot,
        IdentityGroupMemberSnapshot,
        IdentityGroupProjectionRun,
        IdentityGroupSnapshot,
        ScanRecordSnapshot,
    )

    tables = [
        IdentityGroupProjectionRun.__table__,
        ScanRecordSnapshot.__table__,
        IdentityGroupSnapshot.__table__,
        IdentityGroupMemberSnapshot.__table__,
        IdentityFamilyDiagnosticSnapshot.__table__,
        IdentityFamilyDiagnosticMemberSnapshot.__table__,
        IdentityGroupEdgeSnapshot.__table__,
    ]
    IdentityGroupProjectionRun.metadata.create_all(bind=engine, tables=tables, checkfirst=True)

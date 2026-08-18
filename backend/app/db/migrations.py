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
            ("source_row_index_a", "INTEGER"),
            ("source_row_index_b", "INTEGER"),
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
        "rule_exclusion_audit": [
            ("source_row_index_a", "INTEGER"),
            ("source_row_index_b", "INTEGER"),
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
    if engine.url.get_backend_name().startswith("sqlite"):
        additions = [
            ("source_row_index", "INTEGER"),
            ("source_record_fingerprint", "VARCHAR(64)"),
            ("type_code", "VARCHAR(128)"),
            ("prime_commodity", "VARCHAR(128)"),
            ("second_commodity", "VARCHAR(128)"),
            ("accounting_group", "VARCHAR(128)"),
            ("part_product_code", "VARCHAR(128)"),
            ("part_product_family", "VARCHAR(128)"),
            ("hazard_code", "VARCHAR(128)"),
            ("normalization_version", "VARCHAR(80)"),
        ]
        existing = {
            column["name"]
            for column in inspect(engine).get_columns("scan_record_snapshot")
        }
        with engine.begin() as connection:
            for name, ddl in additions:
                if name not in existing:
                    connection.execute(text(
                        f"ALTER TABLE scan_record_snapshot ADD COLUMN {name} {ddl}"
                    ))
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_scan_record_source_row "
                "ON scan_record_snapshot (scan_id, source_row_index)"
            ))


def ensure_group_review_tables(engine):
    """Add append-only G6A review tables without inventing historical reviews."""
    from app.db.models import (
        HumanIdentityConstraint,
        IdentityGroupReviewEvent,
        IdentityGroupReviewPartition,
        IdentityGroupReviewPartitionMember,
    )

    tables = [
        IdentityGroupReviewEvent.__table__,
        IdentityGroupReviewPartition.__table__,
        IdentityGroupReviewPartitionMember.__table__,
        HumanIdentityConstraint.__table__,
    ]
    IdentityGroupReviewEvent.metadata.create_all(bind=engine, tables=tables, checkfirst=True)
    if engine.url.get_backend_name().startswith("sqlite"):
        columns = {
            column["name"] for column in inspect(engine).get_columns(
                "identity_group_review_event"
            )
        }
        with engine.begin() as connection:
            if "initial_group_snapshot_id" not in columns:
                connection.execute(text(
                    "ALTER TABLE identity_group_review_event "
                    "ADD COLUMN initial_group_snapshot_id INTEGER"
                ))
                connection.execute(text(
                    "UPDATE identity_group_review_event "
                    "SET initial_group_snapshot_id = group_snapshot_id "
                    "WHERE supersedes_review_event_id IS NULL"
                ))
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_group_review_initial_group "
                "ON identity_group_review_event (initial_group_snapshot_id)"
            ))


def ensure_identity_discovery_tables(engine):
    """Add GF-2/GF-3/GF-4 tables without backfilling historical scans."""
    from app.db.models import (
        IdentityDiscoveryRun,
        IdentityEvidenceEdgeSnapshot,
        IdentityEvidenceRun,
        IdentityNeighborProposal,
        IdentityNeighborhoodMember,
        IdentityNeighborhoodSnapshot,
    )

    IdentityDiscoveryRun.metadata.create_all(
        bind=engine,
        tables=[
            IdentityDiscoveryRun.__table__,
            IdentityNeighborProposal.__table__,
            IdentityNeighborhoodSnapshot.__table__,
            IdentityNeighborhoodMember.__table__,
            IdentityEvidenceRun.__table__,
            IdentityEvidenceEdgeSnapshot.__table__,
        ],
        checkfirst=True,
    )
    if engine.url.get_backend_name().startswith("sqlite"):
        additions = [
            ("neighborhood_count", "INTEGER NOT NULL DEFAULT 0"),
            ("records_in_at_least_one_neighborhood", "INTEGER NOT NULL DEFAULT 0"),
            ("records_with_proposals_but_no_neighborhood", "INTEGER NOT NULL DEFAULT 0"),
            ("truncated_neighborhood_count", "INTEGER NOT NULL DEFAULT 0"),
            ("max_candidate_neighbor_count", "INTEGER NOT NULL DEFAULT 0"),
            ("max_included_member_count", "INTEGER NOT NULL DEFAULT 0"),
        ]
        existing = {
            column["name"]
            for column in inspect(engine).get_columns("identity_discovery_run")
        }
        with engine.begin() as connection:
            for name, ddl in additions:
                if name not in existing:
                    connection.execute(text(
                        f"ALTER TABLE identity_discovery_run ADD COLUMN {name} {ddl}"
                    ))


def ensure_identity_resolution_tables(engine):
    """Add immutable GF-5C resolver tables without backfilling old scans."""
    from app.db.models import (
        IdentityResolutionConflictMember,
        IdentityResolutionConflictSnapshot,
        IdentityResolutionConstraintInput,
        IdentityResolutionDeferredMember,
        IdentityResolutionDeferredSnapshot,
        IdentityResolutionGroupMember,
        IdentityResolutionGroupSnapshot,
        IdentityResolutionRun,
        IdentityResolutionTargetedEvidence,
        IdentityResolutionUnassignedRecord,
    )

    IdentityResolutionRun.metadata.create_all(bind=engine, tables=[
        IdentityResolutionRun.__table__,
        IdentityResolutionGroupSnapshot.__table__,
        IdentityResolutionGroupMember.__table__,
        IdentityResolutionConflictSnapshot.__table__,
        IdentityResolutionConflictMember.__table__,
        IdentityResolutionDeferredSnapshot.__table__,
        IdentityResolutionDeferredMember.__table__,
        IdentityResolutionTargetedEvidence.__table__,
        IdentityResolutionUnassignedRecord.__table__,
        IdentityResolutionConstraintInput.__table__,
    ], checkfirst=True)


def ensure_g2_v2_projection_tables(engine):
    """Create structurally isolated non-current GF-6B tables; never backfill v1."""
    from app.db.models import (
        G2V2ConflictMemberRow,
        G2V2ConflictSnapshotRow,
        G2V2DeferredMemberRow,
        G2V2DeferredSnapshotRow,
        G2V2GroupMemberRow,
        G2V2GroupSnapshotRow,
        G2V2InternalEvidenceRow,
        G2V2ProjectionRun,
        G2V2UnassignedRecordRow,
    )

    G2V2ProjectionRun.metadata.create_all(bind=engine, tables=[
        G2V2ProjectionRun.__table__,
        G2V2GroupSnapshotRow.__table__,
        G2V2GroupMemberRow.__table__,
        G2V2InternalEvidenceRow.__table__,
        G2V2ConflictSnapshotRow.__table__,
        G2V2ConflictMemberRow.__table__,
        G2V2DeferredSnapshotRow.__table__,
        G2V2DeferredMemberRow.__table__,
        G2V2UnassignedRecordRow.__table__,
    ], checkfirst=True)

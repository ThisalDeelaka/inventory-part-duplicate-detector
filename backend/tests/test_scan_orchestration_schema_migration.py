import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db.migrations import ensure_scan_orchestration_tables
from app.db.models import DuplicateScan, ScanOrchestrationRun
from app.orchestration.contracts import ScanOrchestrationMode
from app.orchestration.pair_path_deprecation import (
    build_post_gf9_orchestration_plan,
    post_gf9_orchestration_policy,
)
from app.services.scan_orchestration_service import start_scan_orchestration


OLD_RUN_TABLE_SQL = """
CREATE TABLE scan_orchestration_run (
    id INTEGER NOT NULL,
    scan_id INTEGER NOT NULL,
    mode VARCHAR(40) NOT NULL,
    policy_version VARCHAR(100) NOT NULL,
    policy_fingerprint VARCHAR(64) NOT NULL,
    plan_fingerprint VARCHAR(64) NOT NULL,
    primary_identity_pipeline VARCHAR(40) NOT NULL,
    visible_projection_contract VARCHAR(20) NOT NULL,
    compatibility_projection_required BOOLEAN NOT NULL,
    status VARCHAR(20) DEFAULT 'RUNNING' NOT NULL,
    started_at DATETIME NOT NULL,
    completed_at DATETIME,
    primary_identity_ready BOOLEAN,
    compatibility_projection_ready BOOLEAN,
    visible_product_ready BOOLEAN,
    shadow_diagnostics_ready BOOLEAN,
    safe_failure_category VARCHAR(80),
    PRIMARY KEY (id),
    CONSTRAINT uq_scan_orchestration_scan UNIQUE (scan_id),
    CONSTRAINT ck_scan_orchestration_mode
        CHECK (mode IN ('legacy_primary', 'group_first_primary')),
    CONSTRAINT ck_scan_orchestration_status
        CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
    CONSTRAINT ck_scan_orchestration_primary_pipeline
        CHECK (primary_identity_pipeline IN ('LEGACY_PAIR_G1', 'GROUP_FIRST_GF1_GF6')),
    CONSTRAINT ck_scan_orchestration_visible_v1
        CHECK (visible_projection_contract = 'G2_V1'),
    FOREIGN KEY(scan_id) REFERENCES duplicate_scan (id)
)
"""


def _sqlite_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys = ON")

    return engine


def _scan(name):
    return DuplicateScan(
        scan_name=name,
        source_type="CSV",
        selected_fields="[]",
        threshold=60,
        status="RUNNING",
        scan_mode="SAME_SITE_DUPLICATE",
        model_version="schema-migration-test",
    )


def _run_insert_sql(projection):
    return text("""
        INSERT INTO scan_orchestration_run (
            scan_id, mode, policy_version, policy_fingerprint, plan_fingerprint,
            primary_identity_pipeline, visible_projection_contract,
            compatibility_projection_required, status, started_at
        ) VALUES (
            :scan_id, 'group_first_primary', 'group-first-orchestration-policy-v2',
            :policy_fingerprint, :plan_fingerprint, 'GROUP_FIRST_GF1_GF6',
            :projection, 0, 'RUNNING', '2026-08-20 00:00:00'
        )
    """).bindparams(projection=projection)


def test_fresh_schema_accepts_v1_and_v2_but_rejects_unknown_projection_values():
    engine = _sqlite_engine()
    Base.metadata.create_all(engine)
    ddl = engine.connect().exec_driver_sql(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='scan_orchestration_run'"
    ).scalar_one()
    assert "visible_projection_contract IN ('G2_V1', 'G2_V2')" in ddl

    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        scans = [_scan(value) for value in ("v2", "v1", "G2_V3", "AUTO")]
        db.add_all(scans)
        db.commit()
        plan = build_post_gf9_orchestration_plan(post_gf9_orchestration_policy(
            ScanOrchestrationMode.GROUP_FIRST_PRIMARY
        ))
        persisted = start_scan_orchestration(db, scan_id=scans[0].id, plan=plan)
        row = db.get(ScanOrchestrationRun, persisted.orchestration_run_id)
        assert row.policy_version == "group-first-orchestration-policy-v2"
        assert row.visible_projection_contract == "G2_V2"
        assert row.compatibility_projection_required is False

        db.execute(_run_insert_sql("G2_V1"), {
            "scan_id": scans[1].id,
            "policy_fingerprint": "v1-policy".ljust(64, "0"),
            "plan_fingerprint": "v1-plan".ljust(64, "1"),
        })
        db.commit()
        assert db.query(ScanOrchestrationRun).filter_by(
            scan_id=scans[1].id
        ).one().visible_projection_contract == "G2_V1"

        for scan, value in zip(scans[2:], ("G2_V3", "AUTO")):
            with pytest.raises(IntegrityError):
                db.execute(_run_insert_sql(value), {
                    "scan_id": scan.id,
                    "policy_fingerprint": value.lower().ljust(64, "0"),
                    "plan_fingerprint": value.lower().ljust(64, "1"),
                })
                db.commit()
            db.rollback()
    finally:
        db.close()
        engine.dispose()


def test_migrated_schema_preserves_history_schema_objects_and_constraints():
    engine = _sqlite_engine()
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE duplicate_scan (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql(OLD_RUN_TABLE_SQL)
        connection.exec_driver_sql("""
            CREATE TABLE scan_orchestration_stage_result (
                id INTEGER PRIMARY KEY,
                orchestration_run_id INTEGER NOT NULL,
                stage_id VARCHAR(50) NOT NULL,
                execution_order INTEGER NOT NULL,
                FOREIGN KEY(orchestration_run_id) REFERENCES scan_orchestration_run(id)
            )
        """)
        connection.exec_driver_sql(
            "CREATE INDEX ix_scan_orchestration_scan_status "
            "ON scan_orchestration_run (scan_id, status)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX ix_scan_orchestration_mode_status "
            "ON scan_orchestration_run (mode, status)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX ix_scan_orchestration_run_policy "
            "ON scan_orchestration_run (policy_version)"
        )
        connection.exec_driver_sql("""
            CREATE TRIGGER tr_scan_orchestration_insert
            AFTER INSERT ON scan_orchestration_run BEGIN SELECT NEW.id; END
        """)
        connection.exec_driver_sql(
            "INSERT INTO duplicate_scan (id) VALUES (11), (12), (13), (14)"
        )
        connection.exec_driver_sql("""
            INSERT INTO scan_orchestration_run VALUES
            (21, 11, 'legacy_primary', 'group-first-orchestration-policy-v1',
             'legacy-policy', 'legacy-plan', 'LEGACY_PAIR_G1', 'G2_V1', 1,
             'COMPLETED', '2026-01-01 10:00:00', '2026-01-01 10:01:00',
             1, 1, 1, 0, 'OPTIONAL_DIAGNOSTIC_FAILED'),
            (22, 12, 'group_first_primary', 'group-first-orchestration-policy-v1',
             'group-policy', 'group-plan', 'GROUP_FIRST_GF1_GF6', 'G2_V1', 1,
             'FAILED', '2026-02-02 11:00:00', '2026-02-02 11:01:00',
             1, 0, 0, 1, 'COMPATIBILITY_OUTPUT_FAILED')
        """)
        connection.exec_driver_sql(
            "INSERT INTO scan_orchestration_stage_result VALUES "
            "(31, 21, 'DISCOVERY', 1), (32, 22, 'GROUP_RESOLUTION', 3)"
        )

    with engine.connect() as connection:
        historical_before = connection.exec_driver_sql(
            "SELECT * FROM scan_orchestration_run ORDER BY id"
        ).fetchall()
        stages_before = connection.exec_driver_sql(
            "SELECT * FROM scan_orchestration_stage_result ORDER BY id"
        ).fetchall()
        columns_before = connection.exec_driver_sql(
            "PRAGMA table_info(scan_orchestration_run)"
        ).fetchall()
        indexes_before = connection.exec_driver_sql(
            "PRAGMA index_list(scan_orchestration_run)"
        ).fetchall()
        foreign_keys_before = connection.exec_driver_sql(
            "PRAGMA foreign_key_list(scan_orchestration_run)"
        ).fetchall()

    ensure_scan_orchestration_tables(engine)
    ensure_scan_orchestration_tables(engine)

    with engine.connect() as connection:
        ddl = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type='table' "
            "AND name='scan_orchestration_run'"
        ).scalar_one()
        assert "visible_projection_contract IN ('G2_V1', 'G2_V2')" in ddl
        assert "ck_scan_orchestration_visible_v1" not in ddl
        assert "ck_scan_orchestration_mode" in ddl
        assert "ck_scan_orchestration_status" in ddl
        assert "ck_scan_orchestration_primary_pipeline" in ddl
        assert connection.exec_driver_sql(
            "SELECT * FROM scan_orchestration_run ORDER BY id"
        ).fetchall() == historical_before
        assert connection.exec_driver_sql(
            "SELECT * FROM scan_orchestration_stage_result ORDER BY id"
        ).fetchall() == stages_before
        assert connection.exec_driver_sql(
            "PRAGMA table_info(scan_orchestration_run)"
        ).fetchall() == columns_before
        assert connection.exec_driver_sql(
            "PRAGMA index_list(scan_orchestration_run)"
        ).fetchall() == indexes_before
        assert connection.exec_driver_sql(
            "PRAGMA foreign_key_list(scan_orchestration_run)"
        ).fetchall() == foreign_keys_before
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
        assert connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='trigger' "
            "AND name='tr_scan_orchestration_insert'"
        ).scalar_one() == "tr_scan_orchestration_insert"

        connection.execute(_run_insert_sql("G2_V2"), {
            "scan_id": 13,
            "policy_fingerprint": "v2-policy".ljust(64, "0"),
            "plan_fingerprint": "v2-plan".ljust(64, "1"),
        })
        connection.execute(_run_insert_sql("G2_V1"), {
            "scan_id": 14,
            "policy_fingerprint": "v1-policy".ljust(64, "0"),
            "plan_fingerprint": "v1-plan".ljust(64, "1"),
        })
        assert connection.exec_driver_sql(
            "SELECT scan_id, visible_projection_contract "
            "FROM scan_orchestration_run WHERE scan_id IN (13, 14) ORDER BY scan_id"
        ).fetchall() == [(13, "G2_V2"), (14, "G2_V1")]

        for column, value in (
            ("visible_projection_contract", "G2_V3"),
            ("visible_projection_contract", "AUTO"),
            ("mode", "AUTO"),
            ("primary_identity_pipeline", "AUTO"),
            ("status", "AUTO"),
        ):
            with pytest.raises(IntegrityError):
                connection.exec_driver_sql(
                    f"UPDATE scan_orchestration_run SET {column}=? WHERE id=21",
                    (value,),
                )
        with pytest.raises(IntegrityError):
            connection.exec_driver_sql("""
                INSERT INTO scan_orchestration_run (
                    scan_id, mode, policy_version, policy_fingerprint, plan_fingerprint,
                    primary_identity_pipeline, visible_projection_contract,
                    compatibility_projection_required, status, started_at
                ) SELECT scan_id, mode, policy_version, policy_fingerprint, plan_fingerprint,
                    primary_identity_pipeline, visible_projection_contract,
                    compatibility_projection_required, status, started_at
                FROM scan_orchestration_run WHERE id=21
            """)
    engine.dispose()

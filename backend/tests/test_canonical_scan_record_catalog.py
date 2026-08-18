from dataclasses import fields
from types import SimpleNamespace

import pandas as pd
import pytest
from sqlalchemy import create_engine, event, inspect, text

from app.core.constants import SOURCE_ROW_INDEX_FIELD
from app.core.config import Settings
from app.db.migrations import ensure_identity_group_snapshot_tables
from app.db.models import (
    DuplicateScan,
    IdentityGroupProjectionRun,
    IdentityGroupSnapshot,
    ScanRecordSnapshot,
)
from app.services.canonical_record_service import (
    CanonicalScanRecord,
    catalog_record_to_engine_input,
    create_or_get_scan_record_catalog,
    load_scan_record_catalog,
)
from app.services.identity_group_query_service import IdentityGroupQueryService
from app.services.scan_runner import ScanRunner
from app.services.validation_service import apply_column_mapping


def _scan(db, name="catalog"):
    row = DuplicateScan(
        scan_name=name,
        threshold=60,
        status="RUNNING",
        total_records=0,
        model_version="hybrid-nlp-v1",
        scan_mode="SAME_SITE_DUPLICATE",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _record(index, **overrides):
    value = {
        SOURCE_ROW_INDEX_FIELD: index,
        "PART_NO": f"P-{index}",
        "DESCRIPTION": "Precision hydraulic valve",
        "CONTRACT": "S1",
        "UNIT_MEAS": "PCS",
        "TYPE_CODE": "PURCHASED",
        "PRIME_COMMODITY": "VALVE",
        "SECOND_COMMODITY": "HYDRAULIC",
        "ACCOUNTING_GROUP": "SPARES",
        "PART_PRODUCT_CODE": "PV",
        "PART_PRODUCT_FAMILY": "CONTROL VALVES",
        "PRODUCT_CATEGORY_ID": "CAT-1",
        "HSN_SAC_CODE": "8481",
        "HAZARD_CODE": "SAFE",
    }
    value.update(overrides)
    return value


def _disabled_configuration():
    return SimpleNamespace(hybrid_retrieval_enabled=False)


def _scan_frame():
    return pd.DataFrame([
        {
            "PART_NO": "A",
            "DESCRIPTION": "MCB30A",
            "CONTRACT": "S1",
            "UNIT_MEAS": "PCS",
        },
        {
            "PART_NO": "B",
            "DESCRIPTION": "MCB 30 A",
            "CONTRACT": "S1",
            "UNIT_MEAS": "PCS",
        },
    ])


def test_one_valid_source_row_is_one_snapshot_and_identical_rows_remain_distinct(db):
    scan = _scan(db)
    identical = _record(0, PART_NO="SAME")
    rows = [identical, {**identical, SOURCE_ROW_INDEX_FIELD: 1}, _record(
        2,
        TYPE_CODE=None,
        PRIME_COMMODITY=None,
        SECOND_COMMODITY=None,
        ACCOUNTING_GROUP=None,
        PART_PRODUCT_CODE=None,
        PART_PRODUCT_FAMILY=None,
        PRODUCT_CATEGORY_ID=None,
        HSN_SAC_CODE=None,
        HAZARD_CODE=None,
    )]

    result = create_or_get_scan_record_catalog(db, scan_id=scan.id, records=rows)
    db.commit()

    assert result.created_count == len(rows)
    assert len(result.records) == len(rows)
    assert [row.source_row_index for row in result.records] == [0, 1, 2]
    assert len({row.record_id for row in result.records}) == len(rows)
    assert len({row.record_ref_key for row in result.records}) == len(rows)
    assert result.records[0].source_record_fingerprint == result.records[1].source_record_fingerprint
    assert result.records[2].type_code is None
    assert db.query(ScanRecordSnapshot).filter_by(scan_id=scan.id).count() == len(rows)
    assert not {
        "similarity_score", "confidence_level", "business_status", "group_status"
    } & {field.name for field in fields(CanonicalScanRecord)}


def test_scan_local_identity_differs_across_scans_and_catalog_order_is_stable(db):
    first_scan = _scan(db, "first")
    second_scan = _scan(db, "second")
    records = [_record(2), _record(0), _record(1)]
    first = create_or_get_scan_record_catalog(
        db, scan_id=first_scan.id, records=records
    )
    db.commit()
    second = create_or_get_scan_record_catalog(
        db, scan_id=second_scan.id, records=records
    )
    db.commit()

    assert [row.source_row_index for row in first.records] == [0, 1, 2]
    assert [row.source_row_index for row in load_scan_record_catalog(db, first_scan.id)] == [0, 1, 2]
    assert {
        row.record_ref_key for row in first.records
    }.isdisjoint({row.record_ref_key for row in second.records})


def test_existing_header_mapping_populates_canonical_values_without_raw_row_payload(db):
    source = pd.DataFrame([{
        "Part No": "IFS-1",
        "Part Description": "Mapped bearing",
        "Site": "SITE-A",
        "Inventory UOM": "EA",
        "Product Family": "BEARINGS",
        "Unused Source Column": "not persisted",
    }])
    mapped, metadata = apply_column_mapping(source)
    mapped[SOURCE_ROW_INDEX_FIELD] = range(len(mapped))
    scan = _scan(db)
    result = create_or_get_scan_record_catalog(
        db, scan_id=scan.id, records=mapped.to_dict(orient="records")
    )
    db.commit()

    record = result.records[0]
    assert metadata["resolved_column_mapping"]["PART_NO"] == "Part No"
    assert (record.part_no, record.description, record.contract, record.uom) == (
        "IFS-1", "Mapped bearing", "SITE-A", "EA"
    )
    assert record.part_product_family == "BEARINGS"
    assert not hasattr(db.query(ScanRecordSnapshot).one(), "unused_source_column")


def test_raw_canonical_values_are_preserved_separately_from_normalization(db):
    scan = _scan(db)
    record = create_or_get_scan_record_catalog(
        db,
        scan_id=scan.id,
        records=[_record(0, PART_NO="  Ab-12  ", DESCRIPTION="  Motor-Bearing  ")],
    ).records[0]
    db.commit()

    assert record.part_no == "  Ab-12  "
    assert record.description == "  Motor-Bearing  "
    assert record.normalized_part_no != record.part_no
    assert record.normalized_description != record.description


def test_historical_null_source_rows_are_not_silently_duplicated_or_reinterpreted(db):
    scan = _scan(db)
    db.add(ScanRecordSnapshot(
        scan_id=scan.id,
        record_ref_key="legacy-ref",
        part_no="LEGACY",
        description="Historical record",
        normalized_part_no="legacy",
        normalized_description="historical record",
    ))
    db.commit()

    with pytest.raises(ValueError, match="historical"):
        create_or_get_scan_record_catalog(
            db, scan_id=scan.id, records=[_record(0)]
        )
    assert db.query(ScanRecordSnapshot).filter_by(scan_id=scan.id).count() == 1


def test_catalog_is_idempotent_and_immutable(db):
    scan = _scan(db)
    records = [_record(0), _record(1)]
    first = create_or_get_scan_record_catalog(db, scan_id=scan.id, records=records)
    db.commit()
    second = create_or_get_scan_record_catalog(db, scan_id=scan.id, records=records)
    db.commit()

    assert first.created_count == 2
    assert second.idempotent and second.created_count == 0
    assert [row.record_id for row in first.records] == [row.record_id for row in second.records]
    assert db.query(ScanRecordSnapshot).filter_by(scan_id=scan.id).count() == 2

    persisted = db.query(ScanRecordSnapshot).filter_by(scan_id=scan.id).first()
    persisted.description = "attempted mutation"
    with pytest.raises(ValueError, match="immutable"):
        db.commit()
    db.rollback()
    assert db.query(ScanRecordSnapshot).filter_by(id=persisted.id).one().description == records[0]["DESCRIPTION"]


def test_catalog_batch_failure_rolls_back_without_partial_rows(db):
    scan = _scan(db)

    def fail_second(_mapper, _connection, target):
        if target.source_row_index == 1:
            raise RuntimeError("forced catalog failure")

    event.listen(ScanRecordSnapshot, "before_insert", fail_second)
    try:
        with pytest.raises(RuntimeError, match="forced catalog failure"):
            create_or_get_scan_record_catalog(
                db, scan_id=scan.id, records=[_record(0), _record(1), _record(2)]
            )
    finally:
        event.remove(ScanRecordSnapshot, "before_insert", fail_second)

    assert db.query(ScanRecordSnapshot).filter_by(scan_id=scan.id).count() == 0


def test_catalog_creation_uses_bounded_selects_not_per_record_queries(db):
    scan_id = _scan(db).id
    statements = []

    def count_select(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", count_select)
    try:
        create_or_get_scan_record_catalog(
            db, scan_id=scan_id, records=[_record(index) for index in range(50)]
        )
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", count_select)
    db.commit()

    assert len(statements) <= 1
    assert db.query(ScanRecordSnapshot).filter_by(scan_id=scan_id).count() == 50


def test_normal_scan_catalog_precedes_candidates_scoring_and_g2_and_g2_reuses_rows(
    db, monkeypatch
):
    from app.services import scan_runner as module

    calls = []
    original_catalog = module.create_or_get_scan_record_catalog
    original_candidates = module.generate_candidate_pairs
    original_score = module.score_candidate
    original_projection = module.project_and_persist_identity_groups

    def catalog(*args, **kwargs):
        calls.append("catalog")
        return original_catalog(*args, **kwargs)

    def candidates(frame, selected_fields):
        assert db.query(ScanRecordSnapshot).count() == len(frame)
        calls.append("candidates")
        return original_candidates(frame, selected_fields)

    def score(*args, **kwargs):
        assert "catalog" in calls and "candidates" in calls
        calls.append("score")
        return original_score(*args, **kwargs)

    def projection(*args, **kwargs):
        before = db.query(ScanRecordSnapshot).count()
        calls.append("g2")
        result = original_projection(*args, **kwargs)
        assert db.query(ScanRecordSnapshot).count() == before
        return result

    def provider_called(*_args, **_kwargs):
        raise AssertionError("GF-1 deterministic scan invoked an external provider")

    monkeypatch.setattr(module, "create_or_get_scan_record_catalog", catalog)
    monkeypatch.setattr(module, "generate_candidate_pairs", candidates)
    monkeypatch.setattr(module, "score_candidate", score)
    monkeypatch.setattr(module, "project_and_persist_identity_groups", projection)
    monkeypatch.setattr("app.llm.factory.create_llm_provider", provider_called)
    monkeypatch.setattr("app.llm.group_provider_factory.create_group_advisory_provider", provider_called)

    scan, _ = ScanRunner(db, _disabled_configuration()).run(
        _scan_frame(), "ordered GF-1", ["CONTRACT", "UNIT_MEAS"], 60
    )

    assert scan.status == "COMPLETED"
    assert calls.index("catalog") < calls.index("candidates") < calls.index("score") < calls.index("g2")
    assert db.query(ScanRecordSnapshot).filter_by(scan_id=scan.id).count() == len(_scan_frame())
    run = db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan.id).one()
    assert run.records_seen == len(_scan_frame())
    assert IdentityGroupQueryService(db).summary(scan.id)["snapshot_available"] is True


def test_catalog_failure_marks_scan_failed_and_discovery_never_starts(db, monkeypatch):
    from app.services import scan_runner as module

    def catalog_failure(*_args, **_kwargs):
        raise RuntimeError("catalog unavailable")

    def discovery_called(*_args, **_kwargs):
        raise AssertionError("candidate discovery ran after catalog failure")

    monkeypatch.setattr(module, "create_or_get_scan_record_catalog", catalog_failure)
    monkeypatch.setattr(module, "generate_candidate_pairs", discovery_called)

    with pytest.raises(RuntimeError, match="catalog unavailable"):
        ScanRunner(db, _disabled_configuration()).run(
            _scan_frame(), "failed GF-1", ["CONTRACT"], 60
        )

    scan = db.query(DuplicateScan).one()
    assert scan.status == "FAILED"
    assert db.query(ScanRecordSnapshot).count() == 0
    assert db.query(IdentityGroupProjectionRun).count() == 0


def test_hybrid_retrieval_starts_only_after_catalog_commit(db, monkeypatch):
    from app.services import scan_runner as module

    original_retrieve = module.HybridCandidateRetriever.retrieve
    observed = []

    def retrieve(retriever, frame, *args, **kwargs):
        assert db.query(ScanRecordSnapshot).count() == len(frame)
        observed.append("hybrid")
        return original_retrieve(retriever, frame, *args, **kwargs)

    monkeypatch.setattr(module.HybridCandidateRetriever, "retrieve", retrieve)
    configuration = Settings(
        llm_provider="none",
        llm_demo_enabled=False,
        hybrid_retrieval_enabled=True,
        hybrid_retrieval_min_score=40,
        hybrid_retrieval_lexical_top_k=2,
        hybrid_retrieval_vector_top_k=2,
        hybrid_retrieval_final_top_k=2,
        hybrid_retrieval_max_pairs_per_scan=10,
    )
    scan, _ = ScanRunner(db, configuration).run(
        _scan_frame(), "hybrid ordering", ["CONTRACT", "UNIT_MEAS"], 60
    )

    assert scan.status == "COMPLETED"
    assert observed == ["hybrid"]


def test_group_reads_export_and_unsure_review_do_not_mutate_catalog(client, db):
    scan, _ = ScanRunner(db, _disabled_configuration()).run(
        _scan_frame(), "immutable consumers", ["CONTRACT", "UNIT_MEAS"], 60
    )
    group = db.query(IdentityGroupSnapshot).filter_by(scan_id=scan.id).one()
    run = db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan.id).one()
    before = [
        tuple(getattr(row, column.name) for column in ScanRecordSnapshot.__table__.columns)
        for row in db.query(ScanRecordSnapshot).filter_by(scan_id=scan.id).order_by(ScanRecordSnapshot.id)
    ]

    assert client.get(f"/api/scans/{scan.id}/identity-groups/{group.id}").status_code == 200
    assert client.get(f"/api/scans/{scan.id}/identity-groups/export.csv").status_code == 200
    response = client.post(
        f"/api/scans/{scan.id}/identity-groups/{group.id}/reviews",
        json={
            "projection_run_id": run.id,
            "group_hypothesis_key": group.hypothesis_key,
            "decision_type": "UNSURE",
            "reviewer": "gf-1-test",
        },
    )
    assert response.status_code == 201

    after = [
        tuple(getattr(row, column.name) for column in ScanRecordSnapshot.__table__.columns)
        for row in db.query(ScanRecordSnapshot).filter_by(scan_id=scan.id).order_by(ScanRecordSnapshot.id)
    ]
    assert after == before


def test_sqlite_additive_migration_extends_historical_record_table(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'historical-gf1.db'}")
    DuplicateScan.__table__.create(engine)
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE scan_record_snapshot (
                id INTEGER PRIMARY KEY,
                scan_id INTEGER NOT NULL,
                record_ref_key VARCHAR(64) NOT NULL,
                contract VARCHAR(100),
                part_no VARCHAR(200) NOT NULL,
                description TEXT NOT NULL,
                normalized_part_no TEXT NOT NULL DEFAULT '',
                normalized_description TEXT NOT NULL DEFAULT '',
                uom VARCHAR(128),
                product_category_id VARCHAR(128),
                hsn_sac_code VARCHAR(128),
                created_at DATETIME NOT NULL
            )
        """))

    ensure_identity_group_snapshot_tables(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("scan_record_snapshot")}
    assert {
        "source_row_index", "source_record_fingerprint", "type_code",
        "prime_commodity", "second_commodity", "accounting_group",
        "part_product_code", "part_product_family", "hazard_code",
        "normalization_version",
    }.issubset(columns)
    indexes = {index["name"] for index in inspect(engine).get_indexes("scan_record_snapshot")}
    assert "uq_scan_record_source_row" in indexes


def test_g2_rejects_missing_catalog_instead_of_creating_records(db):
    from app.services.identity_group_projection import project_identity_groups
    from app.services.identity_group_snapshot_service import persist_identity_group_projection

    scan = _scan(db)
    records = [_record(0), _record(1)]
    candidates = [{
        "source_row_index_a": 0,
        "source_row_index_b": 1,
        "contract_a": "S1",
        "part_no_a": "P-0",
        "description_a": "Precision hydraulic valve",
        "contract_b": "S1",
        "part_no_b": "P-1",
        "description_b": "Precision hydraulic valve",
        "business_status": "LIKELY_DUPLICATE",
        "rule_decision": "ALLOW",
        "rejection_reason": "",
        "critical_mismatches": [],
        "similarity_score": 92.0,
    }]
    projection = project_identity_groups(
        scan_id=scan.id,
        records=records,
        candidates=candidates,
        selected_fields=["CONTRACT", "UNIT_MEAS"],
    )
    with pytest.raises(ValueError, match="missing from the canonical"):
        persist_identity_group_projection(
            db,
            scan=scan,
            records=records,
            candidates=candidates,
            projection=projection,
            selected_fields=["CONTRACT", "UNIT_MEAS"],
        )
    assert db.query(ScanRecordSnapshot).count() == 0
    assert db.query(IdentityGroupProjectionRun).count() == 0


def test_catalog_adapter_preserves_supported_engine_fields(db):
    scan = _scan(db)
    created = create_or_get_scan_record_catalog(
        db, scan_id=scan.id, records=[_record(0)]
    ).records[0]
    db.commit()
    adapted = catalog_record_to_engine_input(created)
    assert adapted[SOURCE_ROW_INDEX_FIELD] == 0
    assert adapted["PART_NO"] == created.part_no
    assert adapted["DESCRIPTION"] == created.description
    assert adapted["HAZARD_CODE"] == created.hazard_code

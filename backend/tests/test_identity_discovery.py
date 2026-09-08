import dataclasses
import json
import pandas as pd
import pytest
from sqlalchemy import event
from sqlalchemy import inspect

from app.core.config import Settings
from app.core.constants import SOURCE_ROW_INDEX_FIELD
from app.db.models import (
    DuplicateCandidate,
    DuplicateScan,
    IdentityDiscoveryRun,
    IdentityNeighborProposal,
    ScanRecordSnapshot,
)
from app.db.migrations import ensure_identity_discovery_tables
from app.discovery.contracts import DiscoveryChannel, NeighborProposal
from app.engine.candidate_generator import generate_candidate_pairs
from app.services.canonical_record_service import create_or_get_scan_record_catalog
from app.services.hybrid_retrieval import (
    CANONICAL_RECORD_REF_FIELD, HybridCandidateRetriever, MemoryEmbeddingVectorCache,
)
from app.services.identity_discovery_service import (
    discovery_fingerprint,
    load_discovery_run,
    load_neighbor_proposals,
    persist_discovery_proposals,
    start_discovery_run,
)
from app.services.identity_neighborhood_service import (
    build_and_persist_identity_neighborhoods,
)
from app.services.scan_runner import ScanRunner


def configuration(**values):
    defaults = dict(
        llm_provider="none",
        llm_demo_enabled=False,
        hybrid_retrieval_enabled=False,
        hybrid_retrieval_lexical_top_k=2,
        hybrid_retrieval_vector_top_k=2,
        hybrid_retrieval_final_top_k=4,
        hybrid_retrieval_max_pairs_per_scan=20,
    )
    defaults.update(values)
    return Settings(**defaults)


def frame(rows):
    result = pd.DataFrame([
        {
            "PART_NO": part_no,
            "DESCRIPTION": description,
            "CONTRACT": contract,
            "UNIT_MEAS": "EA",
        }
        for part_no, description, contract in rows
    ])
    result[SOURCE_ROW_INDEX_FIELD] = range(len(result))
    result[CANONICAL_RECORD_REF_FIELD] = [
        f"test-record-{index:04d}" for index in range(len(result))
    ]
    return result


def create_scan_and_catalog(db, rows):
    scan = DuplicateScan(
        scan_name="GF-2 fixture",
        selected_fields='["CONTRACT"]',
        threshold=99,
        model_version="test",
        scan_mode="SAME_SITE_DUPLICATE",
    )
    db.add(scan)
    db.commit()
    catalog = create_or_get_scan_record_catalog(
        db, scan_id=scan.id, records=rows.to_dict(orient="records")
    )
    db.commit()
    return scan, catalog


def complete(db, scan, catalog, rows, pairs, *, hybrid=None, cfg=None):
    cfg = cfg or configuration()
    run = start_discovery_run(
        db,
        scan_id=scan.id,
        catalog_records=catalog.records,
        configuration=cfg,
        scan_mode="SAME_SITE_DUPLICATE",
        selected_fields=["CONTRACT"],
    )
    db.commit()
    persisted = persist_discovery_proposals(
        db,
        discovery_run_id=run.discovery_run_id,
        scan_id=scan.id,
        catalog_records=catalog.records,
        standard_pairs=pairs,
        hybrid_result=hybrid,
        engine_records=rows.to_dict(orient="records"),
    )
    assert persisted.status.value == "RUNNING"
    build_and_persist_identity_neighborhoods(
        db,
        discovery_run_id=run.discovery_run_id,
        scan_id=scan.id,
        max_members=cfg.identity_neighborhood_max_members,
    )
    db.commit()
    return load_discovery_run(db, run.discovery_run_id), load_neighbor_proposals(
        db, run.discovery_run_id
    )


def test_neighbor_proposal_contract_is_neutral_and_immutable():
    names = {field.name for field in dataclasses.fields(NeighborProposal)}
    forbidden = {
        "business_status", "duplicate_status", "group_status", "human_review_decision",
        "llm_result", "identity_confidence", "duplicate_probability",
    }
    assert not names & forbidden
    assert dataclasses.is_dataclass(NeighborProposal)
    assert NeighborProposal.__dataclass_params__.frozen is True


def test_standard_adapter_has_canonical_identity_and_exact_coverage(db):
    rows = frame([
        ("A", "alpha motor", "S1"),
        ("B", "alpha motor", "S2"),
        ("C", "alpha motor", "S3"),
        ("D", "unrelated", "S4"),
        ("E", "isolated", "S5"),
    ])
    scan, catalog = create_scan_and_catalog(db, rows)
    records = rows.to_dict(orient="records")
    pairs = [
        {"record_a": records[1], "record_b": records[0], "matched_fields": [], "mismatched_fields": [], "warnings": []},
        {"record_a": records[2], "record_b": records[1], "matched_fields": [], "mismatched_fields": [], "warnings": []},
        {"record_a": records[0], "record_b": records[1], "matched_fields": [], "mismatched_fields": [], "warnings": []},
    ]
    run, proposals = complete(db, scan, catalog, rows, pairs)

    assert run.records_total == 5
    assert run.records_with_any_proposal == 3
    assert run.records_without_proposal == 2
    assert run.proposal_count == 2
    assert len(proposals) == 2
    assert all(item.record_id_1 < item.record_id_2 for item in proposals)
    assert all(item.source_channels == (DiscoveryChannel.STANDARD_BLOCKING,) for item in proposals)


def test_same_record_and_missing_or_cross_scan_endpoints_fail_safely(db):
    rows = frame([("A", "one", "S1"), ("B", "two", "S1")])
    scan, catalog = create_scan_and_catalog(db, rows)
    records = rows.to_dict(orient="records")
    self_pair = [{
        "record_a": records[0], "record_b": records[0],
        "matched_fields": [], "mismatched_fields": [], "warnings": [],
    }]
    run = start_discovery_run(
        db, scan_id=scan.id, catalog_records=catalog.records,
        configuration=configuration(), scan_mode="SAME_SITE_DUPLICATE",
        selected_fields=["CONTRACT"],
    )
    db.commit()
    with pytest.raises(ValueError, match="cannot be proposed to itself"):
        persist_discovery_proposals(
            db, discovery_run_id=run.discovery_run_id, scan_id=scan.id,
            catalog_records=catalog.records, standard_pairs=self_pair,
            hybrid_result=None, engine_records=records,
        )
    db.rollback()

    other_rows = frame([("C", "other", "S2")])
    other_scan, other_catalog = create_scan_and_catalog(db, other_rows)
    assert other_scan.id != scan.id
    with pytest.raises(ValueError, match="cross-scan"):
        persist_discovery_proposals(
            db, discovery_run_id=run.discovery_run_id, scan_id=scan.id,
            catalog_records=catalog.records + other_catalog.records,
            standard_pairs=[], hybrid_result=None, engine_records=records,
        )


def test_standard_generation_pair_identities_equal_standard_proposals(db):
    rows = frame([
        ("A", "milk soap", "S1"),
        ("B", "milk-soap", "S1"),
        ("C", "bearing", "S2"),
    ])
    scan, catalog = create_scan_and_catalog(db, rows)
    pairs = generate_candidate_pairs(rows, ["CONTRACT"])
    _, proposals = complete(db, scan, catalog, rows, pairs)
    by_source = {item.source_row_index: item.record_id for item in catalog.records}
    expected = {
        tuple(sorted((by_source[pair["record_a"][SOURCE_ROW_INDEX_FIELD]], by_source[pair["record_b"][SOURCE_ROW_INDEX_FIELD]])))
        for pair in pairs
    }
    assert {(item.record_id_1, item.record_id_2) for item in proposals} == expected


def test_hybrid_equivalence_and_cross_channel_provenance_are_persisted_once(db):
    rows = frame([
        ("A", "MILK SOAP", "S1"),
        ("B", "Milk-Soap", "S1"),
        ("C", "motor bearing 6205", "S2"),
    ])
    cfg = configuration(hybrid_retrieval_enabled=True, local_embedding_enabled=False)
    scan, catalog = create_scan_and_catalog(db, rows)
    hybrid = HybridCandidateRetriever(cfg, cache=MemoryEmbeddingVectorCache()).retrieve(
        rows, "SAME_SITE_DUPLICATE"
    )
    standard = generate_candidate_pairs(rows, ["CONTRACT"])
    _, proposals = complete(db, scan, catalog, rows, standard, hybrid=hybrid, cfg=cfg)
    by_source = {item.source_row_index: item.record_id for item in catalog.records}
    hybrid_pairs = {
        tuple(sorted((by_source[item.left_record_id], by_source[item.right_record_id])))
        for item in hybrid.candidates
    }
    proposal_pairs = {(item.record_id_1, item.record_id_2) for item in proposals}
    assert hybrid_pairs <= proposal_pairs
    shared = next(
        item for item in proposals
        if DiscoveryChannel.STANDARD_BLOCKING in item.source_channels
        and DiscoveryChannel.EXACT_DESCRIPTION in item.source_channels
    )
    assert len([item for item in proposals if item.proposal_id == shared.proposal_id]) == 1
    provenance = {item.channel: item for item in shared.channel_provenance}
    assert provenance[DiscoveryChannel.EXACT_DESCRIPTION].rank is not None
    assert provenance[DiscoveryChannel.EXACT_DESCRIPTION].score is not None
    assert shared.discovery_context_json == json.dumps(
        json.loads(shared.discovery_context_json), sort_keys=True, separators=(",", ":")
    )


def test_hybrid_cap_and_generic_context_are_explicit_without_false_precision(db):
    rows = frame([
        ("A", "BRACKET", "S1"),
        ("B", "BRACKET", "S1"),
        ("C", "BRACKET", "S1"),
        ("D", "BRACKET", "S1"),
    ])
    cfg = configuration(
        hybrid_retrieval_enabled=True,
        local_embedding_enabled=False,
        hybrid_retrieval_final_top_k=1,
        hybrid_retrieval_max_pairs_per_scan=1,
        hybrid_retrieval_tier_a_max=1,
        hybrid_retrieval_tier_b_max=1,
        hybrid_retrieval_tier_c_max=1,
    )
    scan, catalog = create_scan_and_catalog(db, rows)
    hybrid = HybridCandidateRetriever(cfg, cache=MemoryEmbeddingVectorCache()).retrieve(
        rows, "SAME_SITE_DUPLICATE"
    )
    assert hybrid.metrics.hybrid_candidates_skipped_by_cap > 0
    run, proposals = complete(db, scan, catalog, rows, [], hybrid=hybrid, cfg=cfg)
    assert run.degraded is True
    assert run.warning_codes == ("HYBRID_CAP_REACHED",)
    assert run.truncated_record_count is None
    assert run.deferred_family_count is None
    assert len(proposals) == 1
    context = json.loads(proposals[0].discovery_context_json)
    assert context["generic_description_penalty"] > 0


def test_fingerprint_and_serialization_are_deterministic(db):
    rows = frame([("A", "one", "S1"), ("B", "two", "S1")])
    scan, catalog = create_scan_and_catalog(db, rows)
    cfg = configuration()
    first = discovery_fingerprint(catalog.records, cfg, "SAME_SITE_DUPLICATE", ["UNIT_MEAS", "CONTRACT"])
    second = discovery_fingerprint(tuple(reversed(catalog.records)), cfg, "SAME_SITE_DUPLICATE", ["CONTRACT", "UNIT_MEAS"])
    assert first == second


def test_primary_run_start_and_completion_are_idempotent(db):
    rows = frame([("A", "one", "S1"), ("B", "two", "S1")])
    scan, catalog = create_scan_and_catalog(db, rows)
    cfg = configuration()
    first = start_discovery_run(
        db, scan_id=scan.id, catalog_records=catalog.records, configuration=cfg,
        scan_mode="SAME_SITE_DUPLICATE", selected_fields=["CONTRACT"],
    )
    db.commit()
    second = start_discovery_run(
        db, scan_id=scan.id, catalog_records=tuple(reversed(catalog.records)),
        configuration=cfg, scan_mode="SAME_SITE_DUPLICATE", selected_fields=["CONTRACT"],
    )
    assert first.discovery_run_id == second.discovery_run_id
    completed, proposals = complete(
        db, scan, catalog, rows, generate_candidate_pairs(rows, ["CONTRACT"]), cfg=cfg
    )
    repeated = persist_discovery_proposals(
        db, discovery_run_id=completed.discovery_run_id, scan_id=scan.id,
        catalog_records=catalog.records, standard_pairs=[], hybrid_result=None,
        engine_records=rows.to_dict(orient="records"),
    )
    assert repeated.status.value == "COMPLETED"
    assert db.query(IdentityNeighborProposal).count() == len(proposals)


def test_additive_migration_creates_discovery_tables_without_backfill(db):
    engine = db.get_bind()
    IdentityNeighborProposal.__table__.drop(engine)
    IdentityDiscoveryRun.__table__.drop(engine)
    assert "identity_discovery_run" not in inspect(engine).get_table_names()
    ensure_identity_discovery_tables(engine)
    tables = set(inspect(engine).get_table_names())
    assert {"identity_discovery_run", "identity_neighbor_proposal"} <= tables
    assert db.query(IdentityDiscoveryRun).count() == 0


def test_normal_scan_lifecycle_no_neighbor_success_and_legacy_output_unchanged(db):
    data = frame([("A", "alpha", "S1"), ("B", "beta", "S2")]).drop(columns=[SOURCE_ROW_INDEX_FIELD])
    scan, pair_count = ScanRunner(db, configuration()).run(
        data, "no neighbors", ["CONTRACT"], 99
    )
    run = db.query(IdentityDiscoveryRun).filter_by(scan_id=scan.id).one()
    assert scan.status == "COMPLETED"
    assert run.status == "COMPLETED"
    assert run.records_total == 2
    assert run.records_without_proposal == 2
    assert run.proposal_count == 0
    assert pair_count == 0
    assert db.query(DuplicateCandidate).filter_by(scan_id=scan.id).count() == 0


def test_persistence_failure_marks_run_and_scan_failed_and_keeps_catalog(db, monkeypatch):
    from app.repositories.discovery_repository import DiscoveryRepository

    def fail(*_args, **_kwargs):
        raise RuntimeError("forced GF-2 proposal failure")

    monkeypatch.setattr(DiscoveryRepository, "add_proposals", fail)
    data = frame([("A", "same", "S1"), ("B", "same", "S1")]).drop(columns=[SOURCE_ROW_INDEX_FIELD])
    with pytest.raises(RuntimeError, match="forced GF-2 proposal failure"):
        ScanRunner(db, configuration()).run(data, "failed discovery", ["CONTRACT"], 60)

    scan = db.query(DuplicateScan).one()
    run = db.query(IdentityDiscoveryRun).one()
    assert scan.status == "FAILED"
    assert run.status == "FAILED"
    assert run.safe_error_category == "RUNTIMEERROR"
    assert db.query(IdentityNeighborProposal).count() == 0
    assert db.query(ScanRecordSnapshot).count() == 2
    assert db.query(DuplicateCandidate).count() == 0


def test_proposal_persistence_uses_bulk_catalog_resolution_without_endpoint_selects(db):
    rows = frame([(str(index), f"part {index}", "S1") for index in range(8)])
    scan, catalog = create_scan_and_catalog(db, rows)
    pairs = generate_candidate_pairs(rows, ["CONTRACT"])
    run = start_discovery_run(
        db, scan_id=scan.id, catalog_records=catalog.records,
        configuration=configuration(), scan_mode="SAME_SITE_DUPLICATE",
        selected_fields=["CONTRACT"],
    )
    db.commit()
    selects = []

    def count_select(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(db.bind, "before_cursor_execute", count_select)
    try:
        persist_discovery_proposals(
            db, discovery_run_id=run.discovery_run_id, scan_id=scan.id,
            catalog_records=catalog.records, standard_pairs=pairs,
            hybrid_result=None, engine_records=rows.to_dict(orient="records"),
        )
        db.commit()
    finally:
        event.remove(db.bind, "before_cursor_execute", count_select)
    assert len(selects) <= 2
    assert not any("scan_record_snapshot" in statement.lower() for statement in selects)


def test_deterministic_scan_never_invokes_provider_factories(db, monkeypatch):
    def called(*_args, **_kwargs):
        raise AssertionError("GF-2 invoked an external provider")

    monkeypatch.setattr("app.llm.factory.create_llm_provider", called)
    monkeypatch.setattr("app.llm.group_provider_factory.create_group_advisory_provider", called)
    data = frame([("A", "same", "S1"), ("B", "same", "S1")]).drop(columns=[SOURCE_ROW_INDEX_FIELD])
    scan, _ = ScanRunner(db, configuration()).run(data, "provider isolation", ["CONTRACT"], 60)
    run = db.query(IdentityDiscoveryRun).filter_by(scan_id=scan.id).one()
    assert run.provider_request_count == 0

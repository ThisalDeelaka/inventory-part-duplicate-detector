"""RF1-RF26: recovery, failure-mode, and transactional-integrity validation."""

from __future__ import annotations

import inspect
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.benchmarks import production_graduation
from app.benchmarks.contracts import ScaleBenchmarkStatus
from app.benchmarks.group_first_scale import run_scale_benchmark
from app.db.models import (
    DuplicateScan,
    G2V2GroupMemberRow,
    G2V2ProjectionRun,
    IdentityDiscoveryRun,
    IdentityEvidenceEdgeSnapshot,
    IdentityEvidenceRun,
    IdentityNeighborProposal,
    IdentityNeighborhoodMember,
    IdentityNeighborhoodSnapshot,
    IdentityResolutionGroupMember,
    IdentityResolutionRun,
    ScanOrchestrationRun,
    ScanRecordSnapshot,
)
from app.db.database import Base
from app.identity_read.key_codec import serialize_versioned_identity_group_key
from app.services import scan_runner as scan_runner_module
from app.services.hybrid_retrieval import SqlAlchemyEmbeddingVectorCache
from app.services.identity_read_service import (
    IdentityReadAuthorityInconsistent,
    IdentityReadNotReady,
    IdentityReadService,
)
from app.services.scan_runner import ScanRunner


REPO_ROOT = Path(__file__).resolve().parents[2]
RECOVERY_MATRIX = REPO_ROOT / "docs" / "GF12_RECOVERY_FAILURE_MATRIX.md"
RECOVERY_VALIDATION = REPO_ROOT / "docs" / "GF12_RECOVERY_FAILURE_VALIDATION.md"


def _configuration():
    return SimpleNamespace(
        hybrid_retrieval_enabled=False,
        identity_orchestration_mode="group_first_primary",
        group_first_shadow_comparison_enabled=False,
        llm_provider="none",
        group_llm_provider="none",
    )


def _records():
    return pd.DataFrame(
        [
            {
                "PART_NO": "SKF-6205-A",
                "DESCRIPTION": "SKF BEARING 6205 25MM",
                "CONTRACT": "SITE-1",
                "UNIT_MEAS": "PCS",
            },
            {
                "PART_NO": "SKF6205A",
                "DESCRIPTION": "SKF BEARING 6205 25 MM",
                "CONTRACT": "SITE-1",
                "UNIT_MEAS": "PCS",
            },
            {
                "PART_NO": "UNIQUE-9",
                "DESCRIPTION": "UNIQUE CERAMIC INSULATOR 9KV",
                "CONTRACT": "SITE-1",
                "UNIT_MEAS": "PCS",
            },
        ]
    )


def _run(db, name="GF-12B2"):
    return ScanRunner(db, _configuration()).run(
        _records(), name, ["CONTRACT", "UNIT_MEAS"], 60
    )[0]


def _failed_scan(db):
    return db.query(DuplicateScan).order_by(DuplicateScan.id.desc()).first()


def _fail_at(db, monkeypatch, target, message):
    def fail(*_args, **_kwargs):
        raise RuntimeError(message)

    monkeypatch.setattr(target, fail)
    with pytest.raises(RuntimeError):
        _run(db, message)
    scan = _failed_scan(db)
    assert scan.status == "FAILED"
    orchestration = db.query(ScanOrchestrationRun).filter_by(scan_id=scan.id).one()
    assert orchestration.status == "FAILED"
    assert orchestration.visible_product_ready is False
    with pytest.raises(IdentityReadNotReady):
        IdentityReadService(db).load_identity_read_snapshot(scan.id)
    return scan


def _product_signature(db, scan_id):
    records = {
        row.id: row.source_row_index
        for row in db.query(ScanRecordSnapshot).filter_by(scan_id=scan_id)
    }
    proposals = tuple(
        sorted(
            (
                records[row.record_id_1],
                records[row.record_id_2],
                row.proposal_key,
                row.source_channels_json,
            )
            for row in db.query(IdentityNeighborProposal).filter_by(scan_id=scan_id)
        )
    )
    neighborhoods = []
    for row in db.query(IdentityNeighborhoodSnapshot).filter_by(scan_id=scan_id):
        members = tuple(
            records[item.record_id]
            for item in db.query(IdentityNeighborhoodMember)
            .filter_by(neighborhood_id=row.id)
            .order_by(IdentityNeighborhoodMember.member_order)
        )
        neighborhoods.append((records[row.anchor_record_id], members, row.neighborhood_fingerprint))
    resolution = db.query(IdentityResolutionRun).filter_by(scan_id=scan_id).one()
    projection = db.query(G2V2ProjectionRun).filter_by(scan_id=scan_id).one()
    snapshot = IdentityReadService(db).load_identity_read_snapshot(scan_id)
    return (
        proposals,
        tuple(sorted(neighborhoods)),
        resolution.resolution_fingerprint,
        projection.manifest_fingerprint,
        snapshot.summary.group_count,
        sum(group.member_count for group in snapshot.groups),
        len(snapshot.conflicts),
        len(snapshot.deferred_work_units),
        len(snapshot.unassigned_records),
    )


def test_rf1_scan_transaction_state_map_matches_implementation():
    source = inspect.getsource(ScanRunner.run)
    assert source.index("create_or_get_scan_record_catalog") < source.index(
        "start_discovery_run"
    )
    assert source.index("persist_discovery_proposals") < source.index(
        "build_and_persist_identity_neighborhoods"
    ) < source.index("self.db.commit()", source.index("persist_discovery_proposals"))
    assert "complete_scan_orchestration" in source
    assert source.rindex('self.scans.update_status(scan, "FAILED"') > source.index(
        "except Exception as exc"
    )


def test_rf2_failed_scan_never_reports_false_success(db, monkeypatch):
    scan = _fail_at(
        db,
        monkeypatch,
        "app.services.scan_runner.acquire_identity_evidence",
        "RF2 controlled evidence failure",
    )
    assert scan.status != "COMPLETED"


def test_rf3_pre_persistence_failure_leaves_no_final_result(db):
    with pytest.raises(ValueError, match="Missing required columns"):
        ScanRunner(db, _configuration()).run(
            pd.DataFrame([{"DESCRIPTION": "missing part number"}]),
            "RF3",
            [],
            60,
        )
    assert db.query(DuplicateScan).count() == 0
    assert db.query(G2V2ProjectionRun).count() == 0


def test_rf4_discovery_failure_leaves_catalog_but_no_final_result(db, monkeypatch):
    scan = _fail_at(
        db,
        monkeypatch,
        "app.services.scan_runner.generate_candidate_pairs",
        "RF4 discovery computation failure",
    )
    assert db.query(ScanRecordSnapshot).filter_by(scan_id=scan.id).count() == len(_records())
    discovery = db.query(IdentityDiscoveryRun).filter_by(scan_id=scan.id).one()
    assert discovery.status == "FAILED"
    assert db.query(IdentityNeighborProposal).filter_by(scan_id=scan.id).count() == 0
    assert db.query(G2V2ProjectionRun).filter_by(scan_id=scan.id).count() == 0


def test_rf5_gf2_persistence_failure_is_controlled(db, monkeypatch):
    scan = _fail_at(
        db,
        monkeypatch,
        "app.services.scan_runner.persist_discovery_proposals",
        "RF5 GF2 persistence failure",
    )
    assert db.query(IdentityNeighborProposal).filter_by(scan_id=scan.id).count() == 0
    assert db.query(IdentityNeighborhoodSnapshot).filter_by(scan_id=scan.id).count() == 0


def test_rf6_post_gf2_pre_gf3_has_no_distinct_commit_boundary():
    source = inspect.getsource(ScanRunner.run)
    gf2 = source.index("persist_discovery_proposals")
    gf3 = source.index("build_and_persist_identity_neighborhoods")
    commit = source.index("self.db.commit()", gf2)
    assert gf2 < gf3 < commit
    assert "NOT_APPLICABLE" in RECOVERY_MATRIX.read_text(encoding="utf-8")


def test_rf7_gf3_persistence_failure_rolls_back_gf2_and_gf3(db, monkeypatch):
    scan = _fail_at(
        db,
        monkeypatch,
        "app.services.scan_runner.build_and_persist_identity_neighborhoods",
        "RF7 GF3 persistence failure",
    )
    assert db.query(IdentityNeighborProposal).filter_by(scan_id=scan.id).count() == 0
    assert db.query(IdentityNeighborhoodSnapshot).filter_by(scan_id=scan.id).count() == 0


def test_rf8_gf4_persistence_failure_rolls_back_edges(db, monkeypatch):
    scan = _fail_at(
        db,
        monkeypatch,
        "app.services.scan_runner.acquire_identity_evidence",
        "RF8 GF4 persistence failure",
    )
    evidence = db.query(IdentityEvidenceRun).filter_by(scan_id=scan.id).one()
    assert evidence.status == "FAILED"
    assert db.query(IdentityEvidenceEdgeSnapshot).filter_by(scan_id=scan.id).count() == 0


def test_rf9_gf5_pre_persistence_failure_preserves_completed_gf4(db, monkeypatch):
    scan = _fail_at(
        db,
        monkeypatch,
        "app.services.scan_runner.resolve_and_persist_identity_groups",
        "RF9 GF5 pre-persistence validation failure",
    )
    assert db.query(IdentityEvidenceRun).filter_by(scan_id=scan.id).one().status == "COMPLETED"
    assert db.query(IdentityResolutionRun).filter_by(scan_id=scan.id).count() == 0


def test_rf10_gf5_persistence_failure_rolls_back_children(db):
    def fail(*_args):
        raise RuntimeError("RF10 GF5 child persistence failure")

    event.listen(IdentityResolutionGroupMember, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="required group resolution failed"):
            _run(db, "RF10")
    finally:
        event.remove(IdentityResolutionGroupMember, "before_insert", fail)
    scan = _failed_scan(db)
    run = db.query(IdentityResolutionRun).filter_by(scan_id=scan.id).one()
    assert scan.status == run.status == "FAILED"
    assert db.query(IdentityResolutionGroupMember).filter_by(
        resolution_run_id=run.id
    ).count() == 0


def test_rf11_gf5_reload_failure_rolls_back_completed_payload(db, monkeypatch):
    monkeypatch.setattr(
        "app.services.identity_resolution_service.load_persisted_resolution_result",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            ValueError("RF11 reconstruction failure")
        ),
    )
    with pytest.raises(RuntimeError, match="required group resolution failed"):
        _run(db, "RF11")
    scan = _failed_scan(db)
    run = db.query(IdentityResolutionRun).filter_by(scan_id=scan.id).one()
    assert scan.status == run.status == "FAILED"
    assert run.resolution_fingerprint is None
    assert db.query(IdentityResolutionGroupMember).filter_by(
        resolution_run_id=run.id
    ).count() == 0


def test_rf12_gf6_failure_preserves_gf5_but_publishes_nothing(db):
    def fail(*_args):
        raise RuntimeError("RF12 GF6 child persistence failure")

    event.listen(G2V2GroupMemberRow, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="required G2-v2 projection failed"):
            _run(db, "RF12")
    finally:
        event.remove(G2V2GroupMemberRow, "before_insert", fail)
    scan = _failed_scan(db)
    assert db.query(IdentityResolutionRun).filter_by(scan_id=scan.id).one().status == "COMPLETED"
    assert db.query(G2V2ProjectionRun).filter_by(scan_id=scan.id).one().status == "FAILED"
    with pytest.raises(IdentityReadNotReady):
        IdentityReadService(db).load_identity_read_snapshot(scan.id)


def test_rf13_cache_save_failure_preserves_caller_transaction(db):
    cache = SqlAlchemyEmbeddingVectorCache(db)
    original = np.ones(384, dtype=np.float32)
    replacement = np.zeros(384, dtype=np.float32)
    cache.save({"existing": original}, "rf13-model")
    db.commit()

    def fail_insert(_connection, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith("INSERT"):
            raise RuntimeError("RF13 cache insert failure")

    event.listen(db.bind, "before_cursor_execute", fail_insert)
    try:
        with pytest.raises(RuntimeError, match="RF13"):
            cache.save(
                {"existing": replacement, "new": replacement}, "rf13-model"
            )
    finally:
        event.remove(db.bind, "before_cursor_execute", fail_insert)
    db.rollback()
    assert np.array_equal(cache.load(["existing"], "rf13-model")["existing"], original)
    assert cache.load(["new"], "rf13-model") == {}


def test_rf14_cancellation_is_explicitly_unsupported_not_false_success():
    source = inspect.getsource(ScanRunner.run).casefold()
    assert "cancel" not in source and "cancellation" not in source
    text = RECOVERY_VALIDATION.read_text(encoding="utf-8")
    assert "CANCELLATION GRANULARITY GAP" in text
    assert "UNSUPPORTED / NOT IMPLEMENTED" in text


def test_rf15_existing_timeout_seam_is_typed_and_never_completed():
    result = production_graduation.timeout_result(
        {"status": "RUNNING", "active_sub_stage": "GF2_PROPOSAL_PERSISTENCE"},
        {"run": {"status": "TIMED_OUT"}},
        bound=0.01,
        wall=0.02,
    )
    assert result["status"] == "TIMED_OUT"
    assert result["status"] != "COMPLETED"
    assert result["scale_result"]["run"]["status"] == "TIMED_OUT"


def test_rf16_bounded_timeout_worker_is_joined_after_termination():
    source = inspect.getsource(production_graduation.execute_bounded_graduation)
    assert "process.terminate()" in source
    assert "process.join(30)" in source
    assert source.index("process.terminate()") < source.index("process.join(30)")


def test_rf17_catalog_failure_rolls_back_partial_catalog(db, monkeypatch):
    original = scan_runner_module.create_or_get_scan_record_catalog

    def fail_after_materialization(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("RF17 catalog failure after flush")

    monkeypatch.setattr(scan_runner_module, "create_or_get_scan_record_catalog", fail_after_materialization)
    with pytest.raises(RuntimeError, match="RF17 catalog failure after flush"):
        _run(db, "RF17")
    scan = _failed_scan(db)
    assert scan.status == "FAILED"
    assert db.query(ScanRecordSnapshot).filter_by(scan_id=scan.id).count() == 0


def test_rf18_fresh_rerun_equals_clean_control_after_failure(db, monkeypatch):
    original = scan_runner_module.persist_discovery_proposals
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("RF18 one-time GF2 failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(scan_runner_module, "persist_discovery_proposals", fail_once)
    with pytest.raises(RuntimeError, match="RF18"):
        _run(db, "RF18 failed attempt")
    recovered = _run(db, "RF18 recovered attempt")
    recovered_signature = _product_signature(db, recovered.id)

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    control_db = sessionmaker(bind=engine)()
    try:
        # Persisted GF6 fingerprints intentionally include database-owned record
        # ids. Reproduce only the pre-GF2 ordinal setup in the independent control
        # so the fault-free successful runs have the same scan/record identity.
        original_generator = scan_runner_module.generate_candidate_pairs
        monkeypatch.setattr(
            scan_runner_module,
            "generate_candidate_pairs",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                RuntimeError("RF18 control ordinal setup")
            ),
        )
        with pytest.raises(RuntimeError, match="control ordinal setup"):
            _run(control_db, "RF18 control ordinal setup")
        monkeypatch.setattr(
            scan_runner_module, "generate_candidate_pairs", original_generator
        )
        control_scan = _run(control_db, "RF18 clean control")
        assert recovered.id == control_scan.id == 2
        control_signature = _product_signature(control_db, control_scan.id)
    finally:
        control_db.close()
        engine.dispose()
    assert recovered_signature == control_signature


def test_rf18_bounded_500_record_production_integration(tmp_path):
    result = run_scale_benchmark(
        records=500,
        seed=1101,
        scenario="canonical-mixed",
        db_path=tmp_path / "gf12b2-500.sqlite",
        hybrid_enabled=False,
    )
    assert result.run.status == ScaleBenchmarkStatus.COMPLETED
    assert result.safety_metrics.passed
    assert result.safety_metrics.provider_calls == 0
    assert dict(result.database_metrics.row_counts)["gf6_projection_runs"] == 1


def test_rf19_durable_stage_resume_is_not_implemented_or_claimed():
    source = inspect.getsource(ScanRunner)
    assert "def resume" not in source
    text = RECOVERY_VALIDATION.read_text(encoding="utf-8")
    assert "Resume status: `NOT_IMPLEMENTED`" in text
    assert "reconstruction helpers are" in text
    assert "not resume checkpoints" in text


def test_rf20_corrupt_persisted_projection_fails_closed(db):
    scan = _run(db, "RF20 corruption fixture")
    member = db.query(G2V2GroupMemberRow).filter_by(scan_id=scan.id).first()
    assert member is not None
    # Deliberately bypass ORM immutability only in this disposable test database
    # to model storage-level corruption that the read boundary must reject.
    db.execute(text("DELETE FROM g2_v2_group_member WHERE id = :id"), {"id": member.id})
    db.commit()
    with pytest.raises(IdentityReadAuthorityInconsistent, match="SELECTED_PROJECTION_INVALID"):
        IdentityReadService(db).load_identity_read_snapshot(scan.id)


def test_rf21_a_fails_b_succeeds_with_distinct_ownership(db, monkeypatch):
    original = scan_runner_module.acquire_identity_evidence
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("RF21 scan A failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(scan_runner_module, "acquire_identity_evidence", fail_once)
    with pytest.raises(RuntimeError, match="RF21"):
        _run(db, "RF21 scan A")
    scan_a = _failed_scan(db)
    scan_b = _run(db, "RF21 scan B")
    assert scan_a.id != scan_b.id
    assert scan_a.status == "FAILED" and scan_b.status == "COMPLETED"
    assert db.query(G2V2ProjectionRun).filter_by(scan_id=scan_a.id).count() == 0
    assert db.query(G2V2ProjectionRun).filter_by(scan_id=scan_b.id).one().status == "COMPLETED"
    snapshot = IdentityReadService(db).load_identity_read_snapshot(scan_b.id)
    assert snapshot.scan_id == scan_b.id
    assert all(row.versioned_group_key.scan_id == scan_b.id for row in snapshot.groups)


def test_rf22_failed_scan_read_and_review_boundary_is_safe(client, db, monkeypatch):
    failed = _fail_at(
        db,
        monkeypatch,
        "app.services.scan_runner.acquire_identity_evidence",
        "RF22 failed read fixture",
    )
    monkeypatch.undo()
    successful = _run(db, "RF22 key source")
    group = IdentityReadService(db).load_identity_read_snapshot(successful.id).groups[0]
    key = serialize_versioned_identity_group_key(group.versioned_group_key)
    read = client.get(f"/api/scans/{failed.id}/identity-read/summary")
    review = client.post(
        f"/api/scans/{failed.id}/identity-read/groups/{key}/reviews",
        json={"decision_type": "CONFIRM_ALL_AS_ONE", "reviewer": "rf22"},
    )
    assert read.status_code == review.status_code == 409


def test_rf23_failed_scan_authoritative_exports_are_safe(client, db, monkeypatch):
    failed = _fail_at(
        db,
        monkeypatch,
        "app.services.scan_runner.acquire_identity_evidence",
        "RF23 failed export fixture",
    )
    paths = (
        "system-groups/export.csv",
        "reviewed-identities/export.csv",
        "conflicts/export.csv",
        "deferred/export.csv",
    )
    responses = [
        client.get(f"/api/scans/{failed.id}/identity-read/{path}") for path in paths
    ]
    assert [response.status_code for response in responses] == [409, 409, 409, 409]
    assert all("export_contract_version" not in response.text for response in responses)


def test_rf24_group_first_recovery_validation_makes_zero_provider_calls(db, monkeypatch):
    def provider_called(*_args, **_kwargs):
        raise AssertionError("RF24 provider boundary invoked")

    monkeypatch.setattr("app.llm.factory.create_llm_provider", provider_called)
    monkeypatch.setattr(
        "app.llm.groq_group_provider.create_group_advisory_provider", provider_called
    )
    scan = _run(db, "RF24 provider isolation")
    assert db.query(IdentityDiscoveryRun).filter_by(scan_id=scan.id).one().provider_request_count == 0
    assert db.query(IdentityResolutionRun).filter_by(scan_id=scan.id).one().provider_request_count == 0


def test_rf25_no_schema_migration_dependency_or_frontend_change():
    changed = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    forbidden = (
        "backend/app/db/models.py",
        "backend/app/db/migrations.py",
        "backend/requirements",
        "frontend/",
        "docker",
    )
    assert not [path for path in changed if path.casefold().startswith(forbidden)]


def test_rf26_no_production_decision_semantic_change():
    changed = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    production = [path for path in changed if path.startswith("backend/app/")]
    assert production in ([], ["backend/app/api/routes_scans.py"])
    if production:
        diff = subprocess.run(
            ["git", "diff", "--unified=0", "HEAD", "--", production[0]],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert '"message": "Scan failed safely"' in diff
        for forbidden in ("generate_candidate_pairs", "threshold", "score_candidate"):
            assert forbidden not in diff

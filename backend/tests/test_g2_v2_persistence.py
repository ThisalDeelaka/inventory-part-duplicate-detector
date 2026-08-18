import dataclasses

import pytest
from sqlalchemy import event

from app.db.migrations import ensure_g2_v2_projection_tables
from app.db.models import (
    G2V2ConflictSnapshotRow,
    G2V2DeferredSnapshotRow,
    G2V2GroupMemberRow,
    G2V2GroupSnapshotRow,
    G2V2InternalEvidenceRow,
    G2V2ProjectionRun,
    G2V2UnassignedRecordRow,
    IdentityGroupProjectionRun,
    IdentityGroupSnapshot,
    IdentityResolutionRun,
)
from app.repositories.g2_v2_projection_repository import G2V2ProjectionRepository
from app.services.g2_v2_projection_service import (
    _persist_manifest,
    build_and_persist_g2_v2_projection,
    load_persisted_g2_v2_manifest,
)
from app.g2_v2.contracts import G2V2EvidenceOrigin
from app.resolution.contracts import (
    IdentityGroupHypothesisStatus,
    IdentityValidationMode,
)
from app.services.group_llm_eligibility import GroupAdvisoryContractService
from app.services.identity_group_export_service import identity_groups_to_csv
from app.services.identity_group_query_service import IdentityGroupQueryService
from app.services.identity_group_review_service import IdentityGroupReviewService
from app.services.scan_runner import ScanRunner
from test_identity_resolution_persistence import resolve_fixture
from test_identity_evidence import row
from test_scan_identity_group_projection import (
    SELECTED_FIELDS,
    accepted_group_records,
    configuration,
)


def _resolved_pair(db):
    scan, _discovery, _evidence, resolved = resolve_fixture(db, [
        row("SKF-6205-A", "SKF BEARING 6205 25MM"),
        row("SKF6205A", "SKF BEARING 6205 25 MM"),
    ], [(0, 1)])
    assert resolved.status == "COMPLETED"
    return scan, resolved


def test_pure_manifest_persists_reloads_exactly_and_is_idempotent(db):
    scan, resolved = _resolved_pair(db)
    first = build_and_persist_g2_v2_projection(
        db, scan_id=scan.id, resolution_run_id=resolved.resolution_run_id
    )
    assert first.status == "COMPLETED"
    assert first.manifest == load_persisted_g2_v2_manifest(db, first.projection_run_id)
    assert first.manifest.accepted_group_count == 1
    assert first.manifest.groups[0].validation_coverage.evaluated_internal_pair_count == 1
    assert first.manifest.groups[0].validation_coverage.possible_internal_pair_count == 1
    assert first.manifest.groups[0].validation_coverage.missing_nonrequired_pair_count == 0
    before = tuple(db.query(model).count() for model in (
        G2V2ProjectionRun, G2V2GroupSnapshotRow, G2V2GroupMemberRow,
        G2V2InternalEvidenceRow,
    ))
    second = build_and_persist_g2_v2_projection(
        db, scan_id=scan.id, resolution_run_id=resolved.resolution_run_id
    )
    after = tuple(db.query(model).count() for model in (
        G2V2ProjectionRun, G2V2GroupSnapshotRow, G2V2GroupMemberRow,
        G2V2InternalEvidenceRow,
    ))
    assert second.idempotent is True
    assert second.projection_run_id == first.projection_run_id
    assert second.manifest_fingerprint == first.manifest_fingerprint
    assert after == before


def test_conflict_deferred_and_unassigned_stay_distinct(db):
    conflict_scan, _d, _e, conflict = resolve_fixture(db, [
        row("A", "MOTOR 10A"), row("B", "MOTOR 20A")
    ], [(0, 1)])
    conflict_v2 = build_and_persist_g2_v2_projection(
        db, scan_id=conflict_scan.id, resolution_run_id=conflict.resolution_run_id
    ).manifest
    assert conflict_v2.conflicts and not conflict_v2.groups
    assert db.query(G2V2ConflictSnapshotRow).filter_by(scan_id=conflict_scan.id).count() > 0

    from app.resolution.contracts import ResolverConfiguration
    deferred_scan, _d, _e, deferred = resolve_fixture(db, [
        row("A", "FILTER A"), row("B", "FILTER A"), row("C", "FILTER A")
    ], [(0, 1), (1, 2)], ResolverConfiguration(2, 40, 2, "g2-v2-deferred-test"))
    deferred_v2 = build_and_persist_g2_v2_projection(
        db, scan_id=deferred_scan.id, resolution_run_id=deferred.resolution_run_id
    ).manifest
    assert deferred_v2.deferred_work_units
    assert deferred_v2.unassigned_record_count == 3
    assert db.query(G2V2DeferredSnapshotRow).filter_by(scan_id=deferred_scan.id).count() > 0
    assert db.query(G2V2UnassignedRecordRow).filter_by(
        projection_run_id=db.query(G2V2ProjectionRun).filter_by(scan_id=deferred_scan.id).one().id
    ).count() == 3


def test_proposal_and_targeted_evidence_origins_persist_without_upstream_writes(db):
    scan, _discovery, evidence, resolved = resolve_fixture(db, [
        row("A", "SKF BEARING 6205"),
        row("B", "SKF BEARING 6205"),
        row("C", "SKF BEARING 6205"),
    ], [(0, 1), (1, 2)])
    before_gf4 = len(evidence.edges)
    persisted = build_and_persist_g2_v2_projection(
        db, scan_id=scan.id, resolution_run_id=resolved.resolution_run_id
    )
    assert persisted.status == "COMPLETED", persisted
    origins = {
        item.evidence_origin
        for group in persisted.manifest.groups
        for item in group.internal_evidence
    }
    assert origins == {
        G2V2EvidenceOrigin.PROPOSAL_EVIDENCE,
        G2V2EvidenceOrigin.TARGETED_RESOLUTION_EVIDENCE,
    }
    from app.db.models import IdentityEvidenceEdgeSnapshot, IdentityNeighborProposal
    assert db.query(IdentityEvidenceEdgeSnapshot).filter_by(
        evidence_run_id=evidence.run.evidence_run_id
    ).count() == before_gf4
    assert db.query(IdentityNeighborProposal).filter_by(
        discovery_run_id=evidence.run.discovery_run_id
    ).count() == before_gf4


def test_progressive_review_persistence_preserves_sparse_coverage(db):
    from test_g2_v2_adapter import build, hypothesis, proposal, record, resolution
    from app.engine.identity_edge import IdentityEdgeClass

    records = (record(1, "A"), record(2, "B"), record(3, "C"))
    edges = (
        proposal(1, 2, IdentityEdgeClass.STRONG_SUPPORT),
        proposal(2, 3, IdentityEdgeClass.REVIEW_SUPPORT),
    )
    source = hypothesis(
        records, edges,
        status=IdentityGroupHypothesisStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW,
        mode=IdentityValidationMode.PROGRESSIVE_TARGETED,
    )
    manifest = build(records, resolution(records, (source,)), edges)
    repository = G2V2ProjectionRepository(db)
    run = repository.add_run(
        scan_id=manifest.scan_id,
        source_resolution_run_id=manifest.source_resolution_run_id,
        source_discovery_run_id=manifest.source_discovery_run_id,
        source_evidence_run_id=manifest.source_evidence_run_id,
        snapshot_contract_version=manifest.snapshot_contract_version,
        adapter_algorithm_version=manifest.adapter_algorithm_version,
        adapter_configuration_fingerprint=manifest.adapter_configuration_fingerprint,
        source_manifest_fingerprint=manifest.source_resolution_fingerprint,
        manifest_fingerprint=manifest.manifest_fingerprint,
        status="RUNNING",
    )
    _persist_manifest(repository, run, manifest)
    for name in (
        "canonical_record_count", "accepted_group_count", "likely_group_count",
        "review_group_count", "conflict_count", "deferred_count",
        "unassigned_record_count",
    ):
        setattr(run, name, getattr(manifest, name))
    run.status = "COMPLETED"
    db.commit()
    loaded = load_persisted_g2_v2_manifest(db, run.id)
    coverage = loaded.groups[0].validation_coverage
    assert loaded == manifest
    assert loaded.groups[0].validation_mode == IdentityValidationMode.PROGRESSIVE_TARGETED
    assert coverage.evaluated_internal_pair_count == 2
    assert coverage.possible_internal_pair_count == 3
    assert coverage.missing_nonrequired_pair_count == 1
    assert len(loaded.groups[0].internal_evidence) == 2


def test_partial_child_failure_rolls_back_and_marks_only_v2_failed(db):
    scan, resolved = _resolved_pair(db)

    def fail(*_args):
        raise RuntimeError("forced G2-v2 child failure")

    event.listen(G2V2GroupMemberRow, "before_insert", fail)
    try:
        persisted = build_and_persist_g2_v2_projection(
            db, scan_id=scan.id, resolution_run_id=resolved.resolution_run_id
        )
    finally:
        event.remove(G2V2GroupMemberRow, "before_insert", fail)
    assert persisted.status == "FAILED"
    run = db.get(G2V2ProjectionRun, persisted.projection_run_id)
    assert run.status == "FAILED" and run.safe_failure_category == "RUNTIMEERROR"
    assert all(not rows for rows in G2V2ProjectionRepository(db).result_rows(run.id))
    assert db.get(IdentityResolutionRun, resolved.resolution_run_id).status == "COMPLETED"


def test_persisting_v2_does_not_contaminate_any_current_v1_reader(db, monkeypatch):
    monkeypatch.setattr(
        "app.services.scan_runner.build_and_persist_g2_v2_projection",
        lambda *_args, **_kwargs: None,
    )
    scan, _ = ScanRunner(db, configuration()).run(
        accepted_group_records(), "GF-6B reader isolation", SELECTED_FIELDS, 60
    )
    v1 = db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan.id).one()
    group = db.query(IdentityGroupSnapshot).filter_by(projection_run_id=v1.id).one()
    query = IdentityGroupQueryService(db)
    before_summary = query.summary(scan.id)
    before_groups = query.list_groups(scan.id)
    before_export = identity_groups_to_csv(db, scan.id)
    before_review_members = IdentityGroupReviewService(db).group_members(
        scan.id, v1.id, group.id, group.hypothesis_key
    )
    before_advisory_run = GroupAdvisoryContractService(db).load(
        scan.id, v1.id, group.id
    )[0].id
    resolution = db.query(IdentityResolutionRun).filter_by(scan_id=scan.id).one()
    persisted = build_and_persist_g2_v2_projection(
        db, scan_id=scan.id, resolution_run_id=resolution.id
    )
    v2 = db.get(G2V2ProjectionRun, persisted.projection_run_id)
    after_summary = query.summary(scan.id)
    after_groups = query.list_groups(scan.id)
    after_export = identity_groups_to_csv(db, scan.id)
    assert v2.status == "COMPLETED"
    assert before_summary == after_summary
    assert before_groups == after_groups
    assert before_export == after_export
    assert after_summary["snapshot_available"] is True
    assert after_summary["selected_projection"]["projection_run_id"] == v1.id
    assert query.resolve_run(scan.id).id == v1.id
    assert after_groups["items"][0]["group_snapshot_id"] == group.id
    assert f",{v1.id}," in after_export
    assert IdentityGroupReviewService(db).group_members(
        scan.id, v1.id, group.id, group.hypothesis_key
    ) == before_review_members
    assert len(before_review_members) == group.group_size
    assert GroupAdvisoryContractService(db).load(
        scan.id, v1.id, group.id
    )[0].id == before_advisory_run == v1.id


def test_normal_v2_failure_is_isolated_from_visible_v1(db):
    def fail(*_args):
        raise RuntimeError("forced non-current G2-v2 failure")

    event.listen(G2V2GroupMemberRow, "before_insert", fail)
    try:
        scan, _ = ScanRunner(db, configuration()).run(
            accepted_group_records(), "GF-6B failure isolation", SELECTED_FIELDS, 60
        )
    finally:
        event.remove(G2V2GroupMemberRow, "before_insert", fail)
    assert scan.status == "COMPLETED"
    assert db.query(G2V2ProjectionRun).filter_by(scan_id=scan.id).one().status == "FAILED"
    assert db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan.id).one().status == "COMPLETED"
    assert IdentityGroupQueryService(db).summary(scan.id)["snapshot_available"] is True


def test_additive_tables_terminal_immutability_and_bounded_reload_queries(db):
    ensure_g2_v2_projection_tables(db.get_bind())
    ensure_g2_v2_projection_tables(db.get_bind())
    scan, resolved = _resolved_pair(db)
    persisted = build_and_persist_g2_v2_projection(
        db, scan_id=scan.id, resolution_run_id=resolved.resolution_run_id
    )
    run = db.get(G2V2ProjectionRun, persisted.projection_run_id)
    run.status = "FAILED"
    with pytest.raises(ValueError, match="terminal G2-v2"):
        db.flush()
    db.rollback()
    db.expire_all()
    statements = []
    listener = lambda *_args: statements.append(1)
    event.listen(db.get_bind(), "before_cursor_execute", listener)
    try:
        loaded = load_persisted_g2_v2_manifest(db, persisted.projection_run_id)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", listener)
    assert dataclasses.is_dataclass(loaded)
    assert len(statements) == 9
    assert loaded.accepted_group_count == 1
    assert sum(group.member_count for group in loaded.groups) == 2
    assert sum(len(group.internal_evidence) for group in loaded.groups) == 1

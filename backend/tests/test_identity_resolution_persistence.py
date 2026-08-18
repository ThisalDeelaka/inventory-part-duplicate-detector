import dataclasses

import pytest
from sqlalchemy import event

from app.db.migrations import ensure_identity_resolution_tables
from app.db.models import (
    IdentityEvidenceEdgeSnapshot,
    IdentityResolutionGroupMember,
    IdentityResolutionRun,
    IdentityResolutionTargetedEvidence,
    IdentityGroupProjectionRun,
    IdentityGroupSnapshot,
)
from app.repositories.resolution_repository import ResolutionRepository
from app.resolution.contracts import ResolverConfiguration
from app.services.identity_resolution_service import (
    load_persisted_resolution_result,
    resolve_and_persist_identity_groups,
)
from app.services.scan_runner import ScanRunner
from app.services.identity_group_review_service import (
    GroupReviewDecision,
    IdentityGroupReviewService,
)
from test_identity_evidence import acquire, row
from test_scan_identity_group_projection import SELECTED_FIELDS, accepted_group_records, configuration


def resolve_fixture(db, records, proposal_pairs, configuration=None):
    scan, _catalog, discovery, evidence = acquire(db, records, proposal_pairs)
    persisted = resolve_and_persist_identity_groups(
        db,
        scan_id=scan.id,
        discovery_run_id=discovery.discovery_run_id,
        evidence_run_id=evidence.run.evidence_run_id,
        **({"configuration": configuration} if configuration else {}),
    )
    return scan, discovery, evidence, persisted


def test_successful_resolution_is_durable_equivalent_and_idempotent(db):
    scan, discovery, evidence, persisted = resolve_fixture(db, [
        row("SKF-6205-A", "SKF BEARING 6205 25MM"),
        row("SKF6205A", "SKF BEARING 6205 25 MM"),
    ], [(0, 1)])

    assert persisted.status == "COMPLETED"
    assert persisted.result == load_persisted_resolution_result(
        db, persisted.resolution_run_id
    )
    assert persisted.result.metrics.accepted_group_count == 1
    before = db.query(IdentityResolutionRun).count()
    retried = resolve_and_persist_identity_groups(
        db, scan_id=scan.id, discovery_run_id=discovery.discovery_run_id,
        evidence_run_id=evidence.run.evidence_run_id,
    )
    assert retried.idempotent is True
    assert retried.resolution_run_id == persisted.resolution_run_id
    assert db.query(IdentityResolutionRun).count() == before


def test_conflict_and_deferred_outcomes_are_persisted(db):
    _scan, _discovery, _evidence, conflict = resolve_fixture(db, [
        row("A", "MOTOR 10A"), row("B", "MOTOR 20A")
    ], [(0, 1)])
    assert conflict.status == "COMPLETED"
    assert conflict.result.conflicts

    capped = ResolverConfiguration(2, 40, 2, "test-member-cap-v1")
    _scan, _discovery, _evidence, deferred = resolve_fixture(db, [
        row("A", "FILTER A"), row("B", "FILTER A"), row("C", "FILTER A")
    ], [(0, 1), (1, 2)], capped)
    assert deferred.status == "COMPLETED"
    assert deferred.result.deferred_work_units


def test_targeted_evidence_is_separate_from_gf4_proposal_evidence(db):
    _scan, _discovery, evidence, persisted = resolve_fixture(db, [
        row("A", "SKF BEARING 6205"),
        row("B", "SKF BEARING 6205"),
        row("C", "SKF BEARING 6205"),
    ], [(0, 1), (1, 2)])
    assert persisted.status == "COMPLETED"
    assert persisted.result.targeted_evidence_requests
    assert db.query(IdentityResolutionTargetedEvidence).filter_by(
        resolution_run_id=persisted.resolution_run_id
    ).count() == len(persisted.result.targeted_evidence_requests)
    assert db.query(IdentityEvidenceEdgeSnapshot).filter_by(
        evidence_run_id=evidence.run.evidence_run_id
    ).count() == 2

    _scan, _discovery, _evidence, multiple = resolve_fixture(db, [
        row("D", "SKF BEARING 6205"), row("E", "SKF BEARING 6205"),
        row("F", "SKF BEARING 6205"), row("G", "SKF BEARING 6205"),
    ], [(0, 1), (1, 2), (2, 3)])
    assert multiple.status == "COMPLETED"
    assert len(multiple.result.targeted_evidence_results) > 1


def test_child_persistence_failure_rolls_back_and_marks_run_failed(db):
    def fail(*_args):
        raise RuntimeError("forced resolution child persistence failure")

    event.listen(IdentityResolutionGroupMember, "before_insert", fail)
    try:
        _scan, _discovery, _evidence, persisted = resolve_fixture(db, [
            row("A", "SKF BEARING 6205"), row("B", "SKF BEARING 6205")
        ], [(0, 1)])
    finally:
        event.remove(IdentityResolutionGroupMember, "before_insert", fail)
    assert persisted.status == "FAILED"
    run = db.get(IdentityResolutionRun, persisted.resolution_run_id)
    assert run.status == "FAILED"
    assert run.safe_failure_category == "RUNTIMEERROR"
    assert ResolutionRepository(db).result_rows(run.id)[0] == []


def test_resolution_tables_are_additive_and_terminal_rows_are_immutable(db):
    bind = db.get_bind()
    ensure_identity_resolution_tables(bind)
    ensure_identity_resolution_tables(bind)
    _scan, _discovery, _evidence, persisted = resolve_fixture(db, [
        row("A", "SKF BEARING 6205"), row("B", "SKF BEARING 6205")
    ], [(0, 1)])
    run = db.get(IdentityResolutionRun, persisted.resolution_run_id)
    run.status = "FAILED"
    with pytest.raises(ValueError, match="terminal identity resolution"):
        db.flush()
    db.rollback()
    assert dataclasses.is_dataclass(persisted.result)


def test_normal_scan_runs_gf5c_before_unchanged_visible_projection(db, monkeypatch):
    def provider_called(*_args, **_kwargs):
        raise AssertionError("GF-5C invoked an external provider")

    monkeypatch.setattr("app.llm.factory.create_llm_provider", provider_called)
    monkeypatch.setattr(
        "app.llm.groq_group_provider.create_group_advisory_provider", provider_called
    )
    scan, _ = ScanRunner(db, configuration()).run(
        accepted_group_records(), "GF-5C normal integration", SELECTED_FIELDS, 60
    )
    run = db.query(IdentityResolutionRun).filter_by(scan_id=scan.id).one()
    assert scan.status == "COMPLETED"
    assert run.status == "COMPLETED"
    assert run.provider_request_count == 0
    assert db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan.id).count() == 1


def test_gf5c_child_failure_does_not_fail_normal_visible_scan(db):
    def fail(*_args):
        raise RuntimeError("forced non-visible GF-5C failure")

    event.listen(IdentityResolutionGroupMember, "before_insert", fail)
    try:
        scan, _ = ScanRunner(db, configuration()).run(
            accepted_group_records(), "GF-5C isolated failure", SELECTED_FIELDS, 60
        )
    finally:
        event.remove(IdentityResolutionGroupMember, "before_insert", fail)
    run = db.query(IdentityResolutionRun).filter_by(scan_id=scan.id).one()
    assert scan.status == "COMPLETED"
    assert run.status == "FAILED"
    assert db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan.id).count() == 1


def test_completed_result_reload_uses_a_fixed_query_count(db):
    _scan, _discovery, _evidence, persisted = resolve_fixture(db, [
        row("A", "SKF BEARING 6205"), row("B", "SKF BEARING 6205")
    ], [(0, 1)])
    statements = []
    listener = lambda *_args: statements.append(1)
    event.listen(db.get_bind(), "before_cursor_execute", listener)
    try:
        assert load_persisted_resolution_result(db, persisted.resolution_run_id)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", listener)
    assert len(statements) <= 9


def test_new_effective_g6_constraints_create_new_resolution_without_reprojection(db):
    scan, _ = ScanRunner(db, configuration()).run(
        accepted_group_records(), "GF-5C constraint input", SELECTED_FIELDS, 60
    )
    first = db.query(IdentityResolutionRun).filter_by(scan_id=scan.id).one()
    projection = db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan.id).one()
    group = db.query(IdentityGroupSnapshot).filter_by(scan_id=scan.id).one()
    members = IdentityGroupReviewService(db).group_members(
        scan.id, projection.id, group.id, group.hypothesis_key
    )
    IdentityGroupReviewService(db).create_review(
        scan_id=scan.id, projection_run_id=projection.id,
        group_snapshot_id=group.id, group_hypothesis_key=group.hypothesis_key,
        decision_type=GroupReviewDecision.KEEP_ALL_SEPARATE,
        reviewer="gf5c-test", submitted_members=members,
    )
    second = resolve_and_persist_identity_groups(
        db, scan_id=scan.id, discovery_run_id=first.discovery_run_id,
        evidence_run_id=first.evidence_run_id,
    )
    assert second.status == "COMPLETED"
    assert second.resolution_run_id != first.id
    assert db.get(IdentityResolutionRun, second.resolution_run_id).effective_constraint_count > 0
    assert db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan.id).count() == 1

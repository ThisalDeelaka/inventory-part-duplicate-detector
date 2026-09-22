import dataclasses

import pytest
from sqlalchemy import create_engine, event, inspect, text
from unittest.mock import patch

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
from app.resolution.contracts import (
    ResolverConfiguration,
    TARGETED_EVIDENCE_CONTRACT_V1,
    TARGETED_EVIDENCE_CONTRACT_V2,
    TARGETED_EVIDENCE_CONTRACT_VERSION,
)
from app.resolution.pair_explanation import (
    PAIR_EXPLANATION_CONTRACT_VERSION,
    PairExplanationAvailability,
    project_proposal_pair_explanation,
    project_targeted_pair_explanation,
)
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
    targeted_rows = db.query(IdentityResolutionTargetedEvidence).filter_by(
        resolution_run_id=persisted.resolution_run_id,
        evaluation_completed=True,
    ).all()
    assert targeted_rows
    assert all(
        item.evidence_contract_version == TARGETED_EVIDENCE_CONTRACT_VERSION
        and item.deterministic_score is not None
        and item.explanation_evidence_json is not None
        and item.pair_explanation_contract_version
        == PAIR_EXPLANATION_CONTRACT_VERSION
        and item.pair_explanation_fingerprint is not None
        for item in targeted_rows
    )
    loaded = load_persisted_resolution_result(db, persisted.resolution_run_id)
    assert tuple(
        (
            item.evidence_contract_version,
            item.deterministic_score,
            item.explanation_evidence_json,
            item.pair_explanation_contract_version,
            item.pair_explanation_fingerprint,
        )
        for item in loaded.targeted_evidence_results
    ) == tuple(
        (
            item.evidence_contract_version,
            item.deterministic_score,
            item.explanation_evidence_json,
            item.pair_explanation_contract_version,
            item.pair_explanation_fingerprint,
        )
        for item in persisted.result.targeted_evidence_results
    )
    assert all(
        project_targeted_pair_explanation(item).availability
        == PairExplanationAvailability.COMPLETE
        for item in loaded.targeted_evidence_results
    )
    assert db.query(IdentityEvidenceEdgeSnapshot).filter_by(
        evidence_run_id=evidence.run.evidence_run_id
    ).count() == 2
    proposal_row = db.query(IdentityEvidenceEdgeSnapshot).filter_by(
        evidence_run_id=evidence.run.evidence_run_id
    ).first()
    proposal_explanation = project_proposal_pair_explanation(
        proposal_row,
        record_reference_1="proposal-left",
        record_reference_2="proposal-right",
    )
    assert proposal_explanation.availability == PairExplanationAvailability.COMPLETE
    assert proposal_explanation.component_scores

    _scan, _discovery, _evidence, multiple = resolve_fixture(db, [
        row("D", "SKF BEARING 6205"), row("E", "SKF BEARING 6205"),
        row("F", "SKF BEARING 6205"), row("G", "SKF BEARING 6205"),
    ], [(0, 1), (1, 2), (2, 3)])
    assert multiple.status == "COMPLETED"
    assert len(multiple.result.targeted_evidence_results) > 1


def test_targeted_score_reload_uses_persisted_value_without_recomputation(db):
    _scan, _discovery, _evidence, persisted = resolve_fixture(db, [
        row("A", "SKF BEARING 6205"),
        row("B", "SKF BEARING 6205"),
        row("C", "SKF BEARING 6205"),
    ], [(0, 1), (1, 2)])
    expected = tuple(
        item.deterministic_score for item in persisted.result.targeted_evidence_results
    )
    assert expected and all(item is not None for item in expected)
    with patch(
        "app.engine.identity_evidence_evaluator.evaluate_canonical_identity_relationship",
        side_effect=AssertionError("reload must not invoke canonical evaluator"),
    ):
        loaded = load_persisted_resolution_result(db, persisted.resolution_run_id)
        explanations = tuple(
            project_targeted_pair_explanation(item)
            for item in loaded.targeted_evidence_results
        )
    assert tuple(
        item.deterministic_score for item in loaded.targeted_evidence_results
    ) == expected
    assert all(
        item.availability == PairExplanationAvailability.COMPLETE
        for item in explanations
    )


def test_legacy_targeted_row_loads_without_claiming_score(db):
    _scan, _discovery, _evidence, persisted = resolve_fixture(db, [
        row("A", "SKF BEARING 6205"),
        row("B", "SKF BEARING 6205"),
        row("C", "SKF BEARING 6205"),
    ], [(0, 1), (1, 2)])
    rows = db.query(IdentityResolutionTargetedEvidence).filter_by(
        resolution_run_id=persisted.resolution_run_id,
        evaluation_completed=True,
    ).all()
    assert rows
    db.execute(text(
        "UPDATE identity_resolution_targeted_evidence "
        "SET evidence_contract_version = NULL, deterministic_score = NULL, "
        "explanation_evidence_json = NULL, "
        "pair_explanation_contract_version = NULL, "
        "pair_explanation_fingerprint = NULL "
        "WHERE resolution_run_id = :run_id AND evaluation_completed = 1"
    ), {"run_id": persisted.resolution_run_id})
    db.commit()
    loaded = load_persisted_resolution_result(db, persisted.resolution_run_id)
    assert all(
        item.evidence_contract_version == TARGETED_EVIDENCE_CONTRACT_V1
        and item.deterministic_score is None
        for item in loaded.targeted_evidence_results
    )
    assert all(
        project_targeted_pair_explanation(item).availability
        == PairExplanationAvailability.PARTIAL_LEGACY
        for item in loaded.targeted_evidence_results
    )


def test_v2_targeted_row_keeps_score_but_reports_partial_legacy_explanation(db):
    _scan, _discovery, _evidence, persisted = resolve_fixture(db, [
        row("A", "SKF BEARING 6205"),
        row("B", "SKF BEARING 6205"),
        row("C", "SKF BEARING 6205"),
    ], [(0, 1), (1, 2)])
    db.execute(text(
        "UPDATE identity_resolution_targeted_evidence "
        "SET evidence_contract_version = :version, "
        "explanation_evidence_json = NULL, "
        "pair_explanation_contract_version = NULL, "
        "pair_explanation_fingerprint = NULL "
        "WHERE resolution_run_id = :run_id AND evaluation_completed = 1"
    ), {
        "version": TARGETED_EVIDENCE_CONTRACT_V2,
        "run_id": persisted.resolution_run_id,
    })
    db.commit()

    loaded = load_persisted_resolution_result(db, persisted.resolution_run_id)

    assert all(
        item.deterministic_score is not None
        and project_targeted_pair_explanation(item).availability
        == PairExplanationAvailability.PARTIAL_LEGACY
        for item in loaded.targeted_evidence_results
    )


def test_legacy_sqlite_targeted_table_gets_nullable_score_columns():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE identity_resolution_targeted_evidence "
            "(id INTEGER PRIMARY KEY)"
        ))
        connection.execute(text(
            "INSERT INTO identity_resolution_targeted_evidence (id) VALUES (1)"
        ))
    ensure_identity_resolution_tables(engine)
    columns = {
        item["name"]: item for item in inspect(engine).get_columns(
            "identity_resolution_targeted_evidence"
        )
    }
    assert columns["evidence_contract_version"]["nullable"] is True
    assert columns["deterministic_score"]["nullable"] is True
    assert columns["explanation_evidence_json"]["nullable"] is True
    assert columns["pair_explanation_contract_version"]["nullable"] is True
    assert columns["pair_explanation_fingerprint"]["nullable"] is True
    with engine.connect() as connection:
        assert connection.execute(text(
            "SELECT evidence_contract_version, deterministic_score, "
            "explanation_evidence_json, pair_explanation_contract_version, "
            "pair_explanation_fingerprint "
            "FROM identity_resolution_targeted_evidence WHERE id = 1"
        )).one() == (None, None, None, None, None)


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

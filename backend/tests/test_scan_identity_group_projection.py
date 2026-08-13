from types import SimpleNamespace

import pandas as pd
import pytest
from sqlalchemy import event

from app.db.models import (
    DuplicateCandidate,
    DuplicateScan,
    IdentityGroupEdgeSnapshot,
    IdentityGroupMemberSnapshot,
    IdentityGroupProjectionRun,
    IdentityGroupSnapshot,
    ScanRecordSnapshot,
)
from app.services.identity_group_query_service import IdentityGroupQueryService
from app.services.scan_runner import ScanRunner


SELECTED_FIELDS = ["CONTRACT", "UNIT_MEAS"]


def configuration():
    return SimpleNamespace(hybrid_retrieval_enabled=False)


def accepted_group_records():
    return pd.DataFrame([
        {
            "PART_NO": "A", "DESCRIPTION": "MCB30A",
            "CONTRACT": "S1", "UNIT_MEAS": "PCS",
        },
        {
            "PART_NO": "B", "DESCRIPTION": "MCB 30 A",
            "CONTRACT": "S1", "UNIT_MEAS": "PCS",
        },
    ])


def test_normal_scan_persists_one_initial_projection_and_exposes_g3_and_pairs(
    client, db, monkeypatch
):
    from app.services import scan_runner as scan_runner_module

    invocations = 0
    authoritative_service = scan_runner_module.project_and_persist_identity_groups

    def counted_projection(*args, **kwargs):
        nonlocal invocations
        invocations += 1
        return authoritative_service(*args, **kwargs)

    def provider_called(*_args, **_kwargs):
        raise AssertionError("normal deterministic scan invoked an LLM provider")

    monkeypatch.setattr(scan_runner_module, "project_and_persist_identity_groups", counted_projection)
    monkeypatch.setattr("app.llm.factory.create_llm_provider", provider_called)
    monkeypatch.setattr("app.llm.groq_group_provider.create_group_advisory_provider", provider_called)

    scan, _ = ScanRunner(db, configuration()).run(
        accepted_group_records(), "initial projection", SELECTED_FIELDS, 60
    )

    assert scan.status == "COMPLETED"
    assert invocations == 1
    assert db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan.id).count() == 1
    assert db.query(IdentityGroupSnapshot).filter_by(scan_id=scan.id).count() > 0
    summary = client.get(f"/api/scans/{scan.id}/identity-groups/summary")
    assert summary.status_code == 200
    assert summary.json()["snapshot_available"] is True
    assert summary.json()["accepted_groups"] > 0
    pairs = client.get(f"/api/scans/{scan.id}/candidates")
    assert pairs.status_code == 200
    assert len(pairs.json()) == db.query(DuplicateCandidate).filter_by(scan_id=scan.id).count()


def test_normal_scan_persists_valid_zero_group_projection(db):
    records = pd.DataFrame([{
        "PART_NO": "ONLY", "DESCRIPTION": "Unique hydraulic actuator",
        "CONTRACT": "S1", "UNIT_MEAS": "PCS",
    }])
    scan, _ = ScanRunner(db, configuration()).run(
        records, "zero groups", SELECTED_FIELDS, 90
    )

    run = db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan.id).one()
    assert run.accepted_groups == 0
    assert db.query(IdentityGroupSnapshot).filter_by(scan_id=scan.id).count() == 0
    summary = IdentityGroupQueryService(db).summary(scan.id)
    assert summary["snapshot_available"] is True
    assert summary["accepted_groups"] == 0


def test_retrying_initial_projection_reuses_the_complete_snapshot_graph(db):
    records = accepted_group_records()
    runner = ScanRunner(db, configuration())
    scan, _ = runner.run(records, "idempotent projection", SELECTED_FIELDS, 60)
    before = tuple(db.query(model).count() for model in (
        IdentityGroupProjectionRun,
        ScanRecordSnapshot,
        IdentityGroupSnapshot,
        IdentityGroupMemberSnapshot,
        IdentityGroupEdgeSnapshot,
    ))

    retried = runner.persist_initial_identity_group_projection(scan, records, SELECTED_FIELDS)
    after = tuple(db.query(model).count() for model in (
        IdentityGroupProjectionRun,
        ScanRecordSnapshot,
        IdentityGroupSnapshot,
        IdentityGroupMemberSnapshot,
        IdentityGroupEdgeSnapshot,
    ))

    assert retried.idempotent is True
    assert before == after
    assert before[0] == 1


def test_projection_persistence_failure_is_atomic_and_marks_scan_failed(db):
    def fail_member_insert(*_args):
        raise RuntimeError("forced initial projection persistence failure")

    event.listen(IdentityGroupMemberSnapshot, "before_insert", fail_member_insert)
    try:
        with pytest.raises(
            RuntimeError, match="forced initial projection persistence failure"
        ):
            ScanRunner(db, configuration()).run(
                accepted_group_records(), "failed projection", SELECTED_FIELDS, 60
            )
    finally:
        event.remove(IdentityGroupMemberSnapshot, "before_insert", fail_member_insert)

    scan = db.query(DuplicateScan).one()
    assert scan.status == "FAILED"
    assert db.query(IdentityGroupProjectionRun).count() == 0
    assert db.query(ScanRecordSnapshot).count() == 0
    assert db.query(IdentityGroupSnapshot).count() == 0
    assert db.query(IdentityGroupMemberSnapshot).count() == 0
    assert db.query(IdentityGroupEdgeSnapshot).count() == 0
    assert IdentityGroupQueryService(db).summary(scan.id)["snapshot_available"] is False


def test_review_of_automatic_initial_projection_does_not_reproject(
    client, db, monkeypatch
):
    scan, _ = ScanRunner(db, configuration()).run(
        accepted_group_records(), "review immutable projection", SELECTED_FIELDS, 60
    )
    run = db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan.id).one()
    group = db.query(IdentityGroupSnapshot).filter_by(scan_id=scan.id).one()
    before = (
        db.query(IdentityGroupProjectionRun).count(),
        db.query(IdentityGroupSnapshot).count(),
        db.query(IdentityGroupMemberSnapshot).count(),
        db.query(IdentityGroupEdgeSnapshot).count(),
    )

    def unexpected_reprojection(*_args, **_kwargs):
        raise AssertionError("review creation automatically reprojected")

    monkeypatch.setattr(
        "app.services.identity_group_snapshot_service.project_and_persist_identity_groups",
        unexpected_reprojection,
    )
    response = client.post(
        f"/api/scans/{scan.id}/identity-groups/{group.id}/reviews",
        json={
            "projection_run_id": run.id,
            "group_hypothesis_key": group.hypothesis_key,
            "decision_type": "CONFIRM_ALL_AS_ONE",
            "reviewer": "stage-1a-test",
        },
    )

    assert response.status_code == 201
    assert before == (
        db.query(IdentityGroupProjectionRun).count(),
        db.query(IdentityGroupSnapshot).count(),
        db.query(IdentityGroupMemberSnapshot).count(),
        db.query(IdentityGroupEdgeSnapshot).count(),
    )

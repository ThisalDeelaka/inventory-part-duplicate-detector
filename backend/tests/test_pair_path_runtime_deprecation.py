import csv
import io

from app.db.models import (
    DuplicateCandidate,
    G2V2ProjectionRun,
    IdentityEvidenceEdgeSnapshot,
    IdentityGroupProjectionRun,
    IdentityNeighborProposal,
    IdentityResolutionRun,
    RuleExclusionAudit,
    ScanRecordSnapshot,
    ScanOrchestrationRun,
    ScanOrchestrationStageResultRow,
    ShadowComparisonRun,
)
from app.identity_read.key_codec import serialize_versioned_identity_group_key
from app.orchestration.pair_path_deprecation import PairDiagnosticsAvailability
from app.services.group_llm_eligibility import GroupAdvisoryContractService
from app.services.identity_group_review_service import (
    GroupReviewDecision,
    VersionedIdentityGroupReviewService,
)
from app.services.identity_read_service import IdentityReadService
from app.services.scan_orchestration_service import pair_diagnostics_state_for_scan
from app.services.scan_runner import ScanRunner
from test_group_first_scan_orchestration import configuration
from test_group_first_backend_inversion import review_records
from test_scan_identity_group_projection import SELECTED_FIELDS, accepted_group_records


def _run(db, mode="group_first_primary", *, shadow=False, name="GF-10B"):
    return ScanRunner(db, configuration(mode, shadow)).run(
        accepted_group_records(), name, SELECTED_FIELDS, 60
    )[0]


def _csv_rows(response):
    assert response.status_code == 200, response.text
    return list(csv.DictReader(io.StringIO(response.text)))


def _legacy_artifact_counts(db, scan_id):
    return {
        "pairs": db.query(DuplicateCandidate).filter_by(scan_id=scan_id).count(),
        "rejections": db.query(RuleExclusionAudit).filter_by(scan_id=scan_id).count(),
        "v1": db.query(IdentityGroupProjectionRun).filter_by(scan_id=scan_id).count(),
        "shadow": db.query(ShadowComparisonRun).filter_by(scan_id=scan_id).count(),
    }


def test_group_first_failing_spies_prove_deprecated_runtime_is_not_invoked(
    db, monkeypatch
):
    runner = ScanRunner(db, configuration("group_first_primary", shadow=True))

    def forbidden(*_args, **_kwargs):
        raise AssertionError("deprecated compatibility runtime was invoked")

    monkeypatch.setattr(runner.candidates, "save", forbidden)
    monkeypatch.setattr(runner.rejections, "save", forbidden)
    monkeypatch.setattr(runner, "persist_initial_identity_group_projection", forbidden)
    monkeypatch.setattr(
        "app.services.scan_runner.build_and_persist_shadow_comparison", forbidden
    )
    scan = runner.run(accepted_group_records(), "spies", SELECTED_FIELDS, 60)[0]

    assert scan.status == "COMPLETED"
    assert _legacy_artifact_counts(db, scan.id) == {
        "pairs": 0, "rejections": 0, "v1": 0, "shadow": 0,
    }
    assert db.query(IdentityNeighborProposal).filter_by(scan_id=scan.id).count() > 0
    assert db.query(IdentityEvidenceEdgeSnapshot).filter_by(scan_id=scan.id).count() > 0
    assert db.query(IdentityResolutionRun).filter_by(scan_id=scan.id).one().status == "COMPLETED"
    assert db.query(G2V2ProjectionRun).filter_by(scan_id=scan.id).one().status == "COMPLETED"
    run = db.query(ScanOrchestrationRun).filter_by(scan_id=scan.id).one()
    assert (
        run.policy_version,
        run.visible_projection_contract,
        run.compatibility_projection_required,
        run.primary_identity_ready,
        run.visible_product_ready,
    ) == (
        "group-first-orchestration-policy-v2", "G2_V2", False, True, True,
    )
    not_applicable = db.query(ScanOrchestrationStageResultRow).filter_by(
        orchestration_run_id=run.id, status="NOT_APPLICABLE"
    ).all()
    assert {row.stage_id for row in not_applicable} == {
        "LEGACY_PAIR_COMPATIBILITY", "G1_COMPATIBILITY_PROJECTION",
        "G2_V1_COMPATIBILITY_PROJECTION", "SHADOW_COMPARISON",
    }


def test_group_first_product_review_advisory_and_exports_need_no_v1(db, client):
    scan = ScanRunner(db, configuration("group_first_primary")).run(
        review_records(), "GF-10B product", ["CONTRACT", "UNIT_MEAS"], 60
    )[0]
    snapshot = IdentityReadService(db).load_identity_read_snapshot(scan.id)
    assert snapshot.projection_contract.value == "G2_V2"
    assert snapshot.groups
    group = snapshot.groups[0]
    key = serialize_versioned_identity_group_key(group.versioned_group_key)
    durable_core_before = tuple(db.query(model).filter_by(scan_id=scan.id).count()
                                for model in (
                                    ScanRecordSnapshot,
                                    IdentityNeighborProposal,
                                    IdentityEvidenceEdgeSnapshot,
                                    IdentityResolutionRun,
                                    G2V2ProjectionRun,
                                ))

    summary = client.get(f"/api/scans/{scan.id}/identity-read/summary")
    listing = client.get(f"/api/scans/{scan.id}/identity-read/groups")
    detail = client.get(f"/api/scans/{scan.id}/identity-read/groups/{key}")
    outcomes = client.get(f"/api/scans/{scan.id}/identity-read/outcomes")
    assert [item.status_code for item in (summary, listing, detail, outcomes)] == [
        200, 200, 200, 200,
    ]
    assert summary.json()["projection"]["projection_contract"] == "G2_V2"

    eligibility, request = GroupAdvisoryContractService(db).build_request_for_versioned_group(
        scan.id, key
    )
    assert eligibility.eligible is True
    assert request is not None
    eligibility_api = client.get(
        f"/api/scans/{scan.id}/identity-read/groups/{key}/advisory/eligibility"
    )
    assert eligibility_api.status_code == 200
    assert eligibility_api.json()["projection_contract"] == "G2_V2"

    refs = tuple(member.stable_record_reference for member in group.members)
    reviews = VersionedIdentityGroupReviewService(db)
    first = reviews.create_review(
        scan_id=scan.id,
        key=group.versioned_group_key,
        decision_type=GroupReviewDecision.CONFIRM_ALL_AS_ONE,
        reviewer="gf10b",
        submitted_members=refs,
    )
    history = reviews.review_history(scan.id, group.versioned_group_key)
    assert len(history) == 1
    assert history[0]["derived_constraint_counts"]["must_link_count"] > 0

    system_rows = _csv_rows(client.get(
        f"/api/scans/{scan.id}/identity-read/system-groups/export.csv"
    ))
    reviewed_rows = _csv_rows(client.get(
        f"/api/scans/{scan.id}/identity-read/reviewed-identities/export.csv"
    ))
    assert system_rows and reviewed_rows
    assert {row["projection_contract"] for row in system_rows + reviewed_rows} == {
        "G2_V2"
    }
    assert client.get(
        f"/api/scans/{scan.id}/identity-read/conflicts/export.csv"
    ).status_code == 200
    assert client.get(
        f"/api/scans/{scan.id}/identity-read/deferred/export.csv"
    ).status_code == 200

    second = reviews.create_review(
        scan_id=scan.id,
        key=group.versioned_group_key,
        decision_type=GroupReviewDecision.KEEP_ALL_SEPARATE,
        reviewer="gf10b-second",
        submitted_members=refs,
        supersedes_review_event_id=first.review_event_id,
    )
    assert second.review_event_id != first.review_event_id
    assert len(reviews.review_history(scan.id, group.versioned_group_key)) == 2

    state = pair_diagnostics_state_for_scan(db, scan.id)
    assert state.availability == PairDiagnosticsAvailability.NOT_GENERATED_NOT_APPLICABLE
    assert state.candidate_pair_count is None
    diagnostics = client.get(f"/api/scans/{scan.id}/candidates")
    diagnostic_export = client.get(f"/api/scans/{scan.id}/export")
    assert diagnostics.status_code == diagnostic_export.status_code == 409
    assert diagnostics.json()["detail"]["availability"] == (
        "NOT_GENERATED_NOT_APPLICABLE"
    )

    numeric = client.get(f"/api/scans/{scan.id}/identity-groups")
    assert numeric.status_code in {200, 404, 409}
    if numeric.status_code == 200:
        assert numeric.json()["items"] == []
    assert _legacy_artifact_counts(db, scan.id) == {
        "pairs": 0, "rejections": 0, "v1": 0, "shadow": 0,
    }
    assert tuple(db.query(model).filter_by(scan_id=scan.id).count()
                 for model in (
                     ScanRecordSnapshot,
                     IdentityNeighborProposal,
                     IdentityEvidenceEdgeSnapshot,
                     IdentityResolutionRun,
                     G2V2ProjectionRun,
                 )) == durable_core_before


def test_policy_v2_legacy_primary_retains_pair_v1_diagnostics_and_shadow(db, client):
    scan = _run(db, "legacy_primary", shadow=True, name="legacy-policy-v2")
    run = db.query(ScanOrchestrationRun).filter_by(scan_id=scan.id).one()
    artifacts = _legacy_artifact_counts(db, scan.id)
    assert run.policy_version == "group-first-orchestration-policy-v2"
    assert run.visible_projection_contract == "G2_V1"
    assert run.compatibility_projection_required is True
    assert artifacts["pairs"] > 0
    assert artifacts["v1"] == 1
    assert artifacts["shadow"] == 1
    assert IdentityReadService(db).load_identity_read_snapshot(
        scan.id
    ).projection_contract.value == "G2_V1"
    state = pair_diagnostics_state_for_scan(db, scan.id)
    assert state.availability == PairDiagnosticsAvailability.GENERATED_AVAILABLE
    assert state.candidate_pair_count == artifacts["pairs"]
    assert client.get(f"/api/scans/{scan.id}/candidates").status_code == 200
    assert client.get(f"/api/scans/{scan.id}/export").status_code == 200
    assert client.get(f"/api/scans/{scan.id}/identity-groups").status_code == 200


def test_controlled_group_first_write_reduction_retains_independent_evidence(db):
    legacy = _run(db, "legacy_primary", shadow=True, name="legacy")
    group = _run(db, "group_first_primary", shadow=True, name="group")
    legacy_artifacts = _legacy_artifact_counts(db, legacy.id)
    group_artifacts = _legacy_artifact_counts(db, group.id)
    assert legacy_artifacts["pairs"] > group_artifacts["pairs"] == 0
    assert legacy_artifacts["v1"] > group_artifacts["v1"] == 0
    assert legacy_artifacts["shadow"] > group_artifacts["shadow"] == 0
    assert db.query(IdentityNeighborProposal).filter_by(scan_id=group.id).count() > 0
    assert db.query(IdentityEvidenceEdgeSnapshot).filter_by(scan_id=group.id).count() > 0
    assert db.query(G2V2ProjectionRun).filter_by(scan_id=group.id).count() == 1

"""OR1-OR24: observability, runbook, and operational-readiness validation."""

from __future__ import annotations

import inspect
import json
import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from app.api import routes_scans
from app.core.config import Settings
from app.db.models import (
    G2V2ProjectionRun,
    IdentityDiscoveryRun,
    IdentityEvidenceRun,
    IdentityResolutionRun,
    ScanOrchestrationRun,
    ScanOrchestrationStageResultRow,
)
from app.llm.runtime import get_llm_settings
from app.orchestration.pair_path_deprecation import (
    build_post_gf9_orchestration_plan,
    post_gf9_orchestration_policy,
)
from app.repositories.scan_repository import ScanRepository
from app.services import scan_runner as scan_runner_module
from app.services.scan_orchestration_service import start_scan_orchestration
from app.services.scan_runner import ScanRunner


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = REPO_ROOT / "docs" / "GF12_OPERATOR_RUNBOOK.md"
CHECKLIST = REPO_ROOT / "docs" / "GF12_OPERATIONAL_READINESS_CHECKLIST.md"
SENTINEL = "SYNTHETIC_OPERATIONAL_SECRET_MUST_NOT_APPEAR"


def _configuration():
    return SimpleNamespace(
        hybrid_retrieval_enabled=False,
        identity_orchestration_mode="group_first_primary",
        group_first_shadow_comparison_enabled=False,
        llm_provider="none",
        group_llm_provider="none",
    )


def _records():
    return pd.DataFrame([
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
    ])


def _run(db, name="GF-12B3"):
    return ScanRunner(db, _configuration()).run(
        _records(), name, ["CONTRACT", "UNIT_MEAS"], 60
    )[0]


def _running(db):
    scan = ScanRepository(db).create(
        "GF-12B3 running", ["CONTRACT", "UNIT_MEAS"], 60
    )
    plan = build_post_gf9_orchestration_plan(
        post_gf9_orchestration_policy("group_first_primary")
    )
    start_scan_orchestration(db, scan_id=scan.id, plan=plan)
    return scan


def _failed(db, monkeypatch, message="GF-12B3 controlled failure"):
    def fail(*_args, **_kwargs):
        raise RuntimeError(message)

    monkeypatch.setattr(scan_runner_module, "generate_candidate_pairs", fail)
    with pytest.raises(RuntimeError, match=message):
        _run(db, "GF-12B3 failed")
    scan = ScanRepository(db).list()[0]
    assert scan.status == "FAILED"
    return scan


def test_or1_scan_correlation_id_and_projection_ownership_are_available(client, db):
    scan = _run(db, "OR1 correlation")
    detail = client.get(f"/api/scans/{scan.id}").json()
    summary = client.get(f"/api/scans/{scan.id}/identity-read/summary").json()
    projection = db.query(G2V2ProjectionRun).filter_by(scan_id=scan.id).one()
    assert detail["id"] == detail["scan_id"] == scan.id
    assert summary["projection"]["source_projection_run_id"] == projection.id
    assert projection.scan_id == scan.id
    assert summary["projection"]["source_orchestration_run_id"] is not None


def test_or2_running_status_is_persisted_and_not_read_ready(client, db):
    scan = _running(db)
    detail = client.get(f"/api/scans/{scan.id}")
    run = db.query(ScanOrchestrationRun).filter_by(scan_id=scan.id).one()
    assert detail.status_code == 200
    assert detail.json()["status"] == run.status == "RUNNING"
    assert detail.json()["completed_at"] is None
    assert run.visible_product_ready is not True
    assert client.get(f"/api/scans/{scan.id}/identity-read/summary").status_code == 409


def test_or3_failed_status_is_terminal_non_success(client, db, monkeypatch):
    scan = _failed(db, monkeypatch, "OR3 failure")
    run = db.query(ScanOrchestrationRun).filter_by(scan_id=scan.id).one()
    assert client.get(f"/api/scans/{scan.id}").json()["status"] == "FAILED"
    assert scan.completed_at is not None
    assert run.status == "FAILED" and run.visible_product_ready is False


def test_or4_completed_status_is_distinct_and_timestamped(client, db):
    scan = _run(db, "OR4 completed")
    body = client.get(f"/api/scans/{scan.id}").json()
    assert body["status"] == "COMPLETED"
    assert body["started_at"] and body["completed_at"]
    assert client.get(f"/api/scans/{scan.id}/identity-read/summary").status_code == 200


def test_or5_visible_product_ready_is_only_true_at_authoritative_boundary(db):
    running = _running(db)
    assert db.query(ScanOrchestrationRun).filter_by(
        scan_id=running.id
    ).one().visible_product_ready is not True
    completed = _run(db, "OR5 completed")
    run = db.query(ScanOrchestrationRun).filter_by(scan_id=completed.id).one()
    assert run.status == "COMPLETED" and run.visible_product_ready is True


def test_or6_failed_scan_cannot_appear_authoritative(client, db, monkeypatch):
    scan = _failed(db, monkeypatch, "OR6 failure")
    response = client.get(f"/api/scans/{scan.id}/identity-read/summary")
    assert response.status_code == 409
    assert "read_ready" not in response.text


def test_or7_stage_telemetry_is_ordered_immutable_terminal_audit(db):
    scan = _run(db, "OR7 stages")
    run = db.query(ScanOrchestrationRun).filter_by(scan_id=scan.id).one()
    rows = db.query(ScanOrchestrationStageResultRow).filter_by(
        orchestration_run_id=run.id
    ).order_by(ScanOrchestrationStageResultRow.execution_order).all()
    assert [row.execution_order for row in rows] == list(range(9))
    assert all(row.completed_at >= row.started_at for row in rows)
    assert [row.completed_at for row in rows] == sorted(row.completed_at for row in rows)
    assert [row.status for row in rows[:5]] == ["SUCCEEDED"] * 5
    assert [row.status for row in rows[5:]] == ["NOT_APPLICABLE"] * 4


def test_or8_successful_summary_reconciles_gf2_through_gf6(client, db):
    scan = _run(db, "OR8 reconciliation")
    discovery = db.query(IdentityDiscoveryRun).filter_by(scan_id=scan.id).one()
    evidence = db.query(IdentityEvidenceRun).filter_by(scan_id=scan.id).one()
    resolution = db.query(IdentityResolutionRun).filter_by(scan_id=scan.id).one()
    projection = db.query(G2V2ProjectionRun).filter_by(scan_id=scan.id).one()
    summary = client.get(f"/api/scans/{scan.id}/identity-read/summary").json()
    assert discovery.status == evidence.status == resolution.status == projection.status == "COMPLETED"
    assert discovery.proposal_count > 0 and discovery.neighborhood_count > 0
    assert evidence.edge_count_persisted == discovery.proposal_count
    assert summary["group_count"] == resolution.accepted_group_count == projection.accepted_group_count
    assert summary["conflict_count"] == resolution.conflict_count == projection.conflict_count
    assert summary["deferred_count"] == resolution.deferred_work_unit_count == projection.deferred_count
    assert summary["unassigned_count"] == resolution.unassigned_record_count == projection.unassigned_record_count


def test_or9_failed_summary_is_status_qualified_and_not_misleading(client, db, monkeypatch):
    scan = _failed(db, monkeypatch, "OR9 failure")
    detail = client.get(f"/api/scans/{scan.id}").json()
    diagnostics = client.get("/api/diagnostics/summary").json()
    assert detail["status"] == diagnostics["last_scan"]["status"] == "FAILED"
    assert client.get(f"/api/scans/{scan.id}/identity-read/summary").status_code == 409
    assert db.query(G2V2ProjectionRun).filter_by(scan_id=scan.id).count() == 0


def test_or10_provider_none_mode_is_safely_observable(client):
    configuration = Settings(
        llm_demo_enabled=False,
        llm_provider="none",
        group_llm_provider="none",
        groq_api_key=SENTINEL,
        anthropic_api_key=SENTINEL,
    )
    client.app.dependency_overrides[get_llm_settings] = lambda: configuration
    response = client.get("/api/llm/status")
    assert response.status_code == 200
    assert response.json()["enabled"] is False
    assert response.json()["provider"] == configuration.llm_provider == "none"
    assert configuration.group_llm_provider == "none"
    assert SENTINEL not in response.text


def test_or11_deterministic_operational_run_has_zero_provider_calls(db, monkeypatch):
    def provider_called(*_args, **_kwargs):
        raise AssertionError("OR11 provider invoked")

    monkeypatch.setattr("app.llm.factory.create_llm_provider", provider_called)
    monkeypatch.setattr(
        "app.llm.groq_group_provider.create_group_advisory_provider", provider_called
    )
    scan = _run(db, "OR11 zero providers")
    assert db.query(IdentityDiscoveryRun).filter_by(scan_id=scan.id).one().provider_request_count == 0
    assert db.query(IdentityResolutionRun).filter_by(scan_id=scan.id).one().provider_request_count == 0


def test_or12_performance_waiver_is_represented_truthfully():
    text = RUNBOOK.read_text(encoding="utf-8")
    for required in (
        "GF11-PERF-100K-COLD-FULL = OPEN",
        "100k cold-full `<=300 s` target = **NOT MET**",
        "GF-11 performance waiver = **ACTIVE**",
        "requires the canonical 100k cold-full benchmark to be rerun",
    ):
        assert required in text


def test_or13_human_validation_dependency_is_represented_truthfully():
    text = RUNBOOK.read_text(encoding="utf-8")
    for required in (
        "GF-12A2 human-review tooling = **VERIFIED**",
        "Authorized human-validation dataset = **REQUIRED**",
        "Human pilot = **NOT EXECUTED**",
        "Final human-quality signoff = **NOT AVAILABLE**",
    ):
        assert required in text


def test_or14_retry_restart_resume_wording_is_accurate():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "**Retry**: submit a new scan" in text
    assert "**Restart**: restore a healthy backend/database connection" in text
    assert "**Resume**: continue the same scan" in text
    assert "Current safe recovery is a new scan" not in text or "NOT_IMPLEMENTED" in text


def test_or15_resume_is_explicitly_not_implemented():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "Resume is **NOT_IMPLEMENTED**" in text
    assert "not a production resume entry point" in text


def test_or16_cancellation_wording_does_not_claim_support():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "Production scan cancellation is **NOT_IMPLEMENTED**" in text
    assert "cancellation-granularity" in text


def test_or17_timeout_wording_does_not_claim_support():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "Production scan-level\ntimeout is **NOT_IMPLEMENTED**" in text
    assert "benchmark-only timeout" in text


def test_or18_failed_review_and_exports_remain_unavailable(client, db, monkeypatch):
    scan = _failed(db, monkeypatch, "OR18 failure")
    paths = (
        "identity-read/system-groups/export.csv",
        "identity-read/reviewed-identities/export.csv",
        "identity-read/conflicts/export.csv",
        "identity-read/deferred/export.csv",
    )
    assert [client.get(f"/api/scans/{scan.id}/{path}").status_code for path in paths] == [409] * 4
    runbook = RUNBOOK.read_text(encoding="utf-8")
    assert "Never create a review or Reviewed Identity Export" in runbook


def test_or19_synthetic_secret_is_absent_from_operator_outputs(client, monkeypatch):
    responses = []
    cases = (
        (
            RuntimeError,
            500,
            {"category": "scan_failure", "message": "Scan failed safely"},
        ),
        (
            ValueError,
            422,
            {
                "category": "validation_failure",
                "message": "Scan input or configuration was rejected safely",
            },
        ),
    )
    for exception_type, expected_status, expected_detail in cases:
        def fail(*_args, **_kwargs):
            raise exception_type(SENTINEL)

        monkeypatch.setattr(routes_scans, "run_scan", fail)
        response = client.post(
            "/api/scans/upload",
            files={
                "file": (
                    "safe.csv",
                    b"PART_NO,DESCRIPTION\nA,SYNTHETIC FIXTURE\n",
                    "text/csv",
                )
            },
            data={"selected_fields": "[]", "scan_name": "OR19 safe failure"},
        )
        assert response.status_code == expected_status
        assert response.json()["detail"] == expected_detail
        responses.append(response)
    outputs = [
        *(response.text for response in responses),
        client.get("/health").text,
        client.get("/ready").text,
        client.get("/api/diagnostics/summary").text,
    ]
    assert all(SENTINEL not in output for output in outputs)


def test_or20_truth_and_human_labels_are_absent_from_operator_telemetry(client):
    payload = "\n".join((
        client.get("/health").text,
        client.get("/ready").text,
        client.get("/api/diagnostics/summary").text,
        client.get("/api/scans").text,
    )).casefold()
    for forbidden in (
        "benchmark_truth",
        "expected_label",
        "truth_group_id",
        "same_item_groups",
        "human_review_label",
        "authorization",
        "api_key",
    ):
        assert forbidden not in payload


def test_or21_runbook_uses_only_real_supported_interfaces():
    source = inspect.getsource(routes_scans)
    main = (REPO_ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
    text = RUNBOOK.read_text(encoding="utf-8")
    for route in (
        "/api/scans/upload",
        "/api/scans/validate-only",
        "/api/scans/{scan_id}",
    ):
        assert route in text
    assert '@router.post("/upload")' in source
    assert '@router.post("/validate-only")' in source
    assert '@router.get("/{scan_id}")' in source
    assert '@app.get("/health")' in main and '@app.get("/ready")' in main
    assert "uvicorn app.main:app" in text and "npm.cmd run dev" in text
    assert "background group-first job" in text and "does not enqueue" in text


def test_or22_checklist_status_values_fail_closed():
    text = CHECKLIST.read_text(encoding="utf-8")
    allowed = {
        "VERIFIED",
        "OPEN",
        "NOT_IMPLEMENTED",
        "NOT_APPLICABLE",
        "REQUIRES_EXTERNAL_DECISION",
    }
    statuses = re.findall(r"\| `([A-Z_]+)` \|", text)
    assert statuses and set(statuses) <= allowed
    assert {"OPEN", "NOT_IMPLEMENTED", "REQUIRES_EXTERNAL_DECISION"} <= set(statuses)
    for category in (
        "Build/test",
        "Database/storage",
        "Provider mode",
        "Observability",
        "Failure/recovery",
        "Review/export",
        "Privacy/security",
        "Human quality",
        "Performance",
        "Retention/policy",
        "Deployment",
        "Final signoff",
    ):
        assert f"| {category} |" in text


def test_or23_no_schema_migration_or_docker_change():
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
        "docker",
    )
    assert not [path for path in changed if path.casefold().startswith(forbidden)]


def test_or24_only_bounded_xlsx_export_changes_in_production():
    changed = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    production = [path for path in changed if path.startswith("backend/app/")]
    allowed = {
        "backend/app/api/routes_scans.py",
        "backend/app/engine/identity_discriminator.py",
        "backend/app/engine/identity_evidence_evaluator.py",
        "backend/app/engine/lexical_trust.py",
        "backend/app/engine/functional_location_facet.py",
        "backend/app/engine/identity_signature_derivation.py",
        "backend/app/engine/signed_identity_evidence.py",
        "backend/app/orchestration/contracts.py",
        "backend/app/api/routes_identity_groups.py",
        "backend/app/identity_read/explanations.py",
        "backend/app/schemas/identity_groups.py",
        "backend/app/services/identity_read_export_service.py",
        "backend/app/services/identity_read_xlsx_export_service.py",
        "backend/app/services/scan_runner.py",
        "backend/app/services/scan_service.py",
        "backend/app/services/hybrid_retrieval.py",
    }
    assert set(production) <= allowed
    if not production:
        return
    diff = subprocess.run(
        ["git", "diff", "--unified=0", "HEAD", "--", *production],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert (
        "authority_selected_system_groups_to_xlsx" in diff
        or "evaluate_identity_discriminators" in diff
        or "system_explanation" in diff
        or "cross_site_identity_discovery" in diff
        or "assess_lexical_trust" in diff
    )
    assert "generate_candidate_pairs" not in diff
    if "assess_lexical_trust" not in diff:
        assert "score_candidate" not in diff

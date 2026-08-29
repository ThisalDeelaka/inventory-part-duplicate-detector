"""DEMO1-DEMO24: showable group-first product acceptance on synthetic data."""

from __future__ import annotations

import json
import csv
import io
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.database import Base, get_db
from app.db.models import (
    G2V2ProjectionRun,
    IdentityDiscoveryRun,
    IdentityEvidenceRun,
    IdentityResolutionRun,
    ScanOrchestrationRun,
)
from app.llm.runtime import get_llm_settings
from app.main import app
from app.benchmarks.contracts import stable_fingerprint
from app.repositories.scan_repository import ScanRepository
from app.services.scan_runner import ScanRunner


REPO_ROOT = Path(__file__).resolve().parents[2]
DEMO_DATA = REPO_ROOT / "data" / "llm_assisted_mvp_demo.csv"
DEMO_GUIDE = REPO_ROOT / "docs" / "LLM_MVP_DEMO_GUIDE.md"
DEMO_CONTRACT = REPO_ROOT / "docs" / "GF12_SHOWABLE_PRODUCT_DEMO_CONTRACT.md"
DEMO_RUNBOOK = REPO_ROOT / "docs" / "GF12_DEMO_RUNBOOK.md"
PRESENTER_SCRIPT = REPO_ROOT / "docs" / "GF12_DEMO_PRESENTER_SCRIPT.md"
ACCEPTANCE = REPO_ROOT / "docs" / "GF12_SHOWABLE_PRODUCT_ACCEPTANCE.md"
SENTINEL = "SYNTHETIC_DEMO_SECRET_MUST_NOT_APPEAR"


def _configuration() -> Settings:
    return Settings(
        identity_orchestration_mode="group_first_primary",
        group_first_shadow_comparison_enabled=False,
        llm_demo_enabled=False,
        llm_provider="none",
        group_llm_provider="none",
        groq_api_key=SENTINEL,
        anthropic_api_key=SENTINEL,
    )


def _upload(client: TestClient, name: str):
    response = client.post(
        "/api/scans/upload",
        files={"file": ("synthetic-demo.csv", DEMO_DATA.read_bytes(), "text/csv")},
        data={
            "scan_name": name,
            "threshold": "75",
            "selected_fields": json.dumps(["CONTRACT", "UNIT_MEAS"]),
            "column_mapping": "{}",
            "sensitive_mode": "true",
            "scan_mode": "SAME_SITE_DUPLICATE",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _semantic_product_fingerprint(summary, details):
    """Cross-scan demo identity excluding scan-local keys, IDs, and timestamps."""
    return stable_fingerprint({
        "summary": {
            key: summary[key]
            for key in (
                "canonical_record_count", "group_count", "likely_group_count",
                "review_group_count", "conflict_count", "deferred_count",
                "unassigned_count",
            )
        },
        "groups": sorted(
            (
                item["group_status"],
                item["validation_mode"],
                tuple(sorted(
                    (
                        member["source_row_index"], member["part_no"],
                        member["normalized_part_no"], member["normalized_description"],
                    )
                    for member in item["members"]
                )),
            )
            for item in details
        ),
    })


def _semantic_export_identity(response):
    rows = csv.DictReader(io.StringIO(response.text))
    return tuple(sorted(
        (
            row["group_status"], row["validation_mode"], row["member_count"],
            row["source_row_reference"], row["part_no"], row["description"],
        )
        for row in rows
    ))


@pytest.fixture(scope="module")
def demo():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    configuration = _configuration()
    app.dependency_overrides[get_db] = lambda: session
    app.dependency_overrides[get_llm_settings] = lambda: configuration
    try:
        with TestClient(app) as client:
            uploads = [_upload(client, "GF-12C1 synthetic product demo") for _ in range(3)]
            scan_ids = [item["scan_id"] for item in uploads]
            summaries = [client.get(f"/api/scans/{scan_id}/identity-read/summary").json() for scan_id in scan_ids]
            groups = [client.get(f"/api/scans/{scan_id}/identity-read/groups?limit=100").json() for scan_id in scan_ids]
            outcomes = [client.get(f"/api/scans/{scan_id}/identity-read/outcomes").json() for scan_id in scan_ids]
            details = [
                [
                    client.get(
                        f"/api/scans/{scan_id}/identity-read/groups/{item['versioned_group_key']}"
                    ).json()
                    for item in result["items"]
                ]
                for scan_id, result in zip(scan_ids, groups, strict=True)
            ]
            system_exports = [
                client.get(f"/api/scans/{scan_id}/identity-read/system-groups/export.csv")
                for scan_id in scan_ids
            ]
            semantic_fingerprints = [
                _semantic_product_fingerprint(summary, detail)
                for summary, detail in zip(summaries, details, strict=True)
            ]
            semantic_export_identities = [
                _semantic_export_identity(response) for response in system_exports
            ]
            first_scan = scan_ids[0]
            before_review = client.get(
                f"/api/scans/{first_scan}/identity-read/reviewed-identities/export.csv"
            )
            review_group = next(item for item in details[0] if len(item["members"]) == 3)
            review_target = (
                f"/api/scans/{first_scan}/identity-read/groups/"
                f"{review_group['versioned_group_key']}/reviews"
            )
            created_review = client.post(review_target, json={
                "decision_type": "CONFIRM_ALL_AS_ONE",
                "reviewer": "GF12C1_DEMO_PRESENTER",
                "comment": "Synthetic demo action; not human-quality evidence.",
                "supersedes_review_event_id": None,
                "selected_record_ref_keys": [],
                "partitions": [],
            })
            review_history = client.get(review_target)
            updated_review = client.post(review_target, json={
                "decision_type": "UNSURE",
                "reviewer": "GF12C1_DEMO_PRESENTER",
                "comment": "Synthetic correction demonstrating append-only versioning.",
                "supersedes_review_event_id": created_review.json()["review_event_id"],
                "selected_record_ref_keys": [],
                "partitions": [],
            })
            updated_history = client.get(review_target)
            after_unsure = client.get(
                f"/api/scans/{first_scan}/identity-read/reviewed-identities/export.csv"
            )
            restored_review = client.post(review_target, json={
                "decision_type": "CONFIRM_ALL_AS_ONE",
                "reviewer": "GF12C1_DEMO_PRESENTER",
                "comment": "Synthetic final demo review; not quality evidence.",
                "supersedes_review_event_id": updated_review.json()["review_event_id"],
                "selected_record_ref_keys": [],
                "partitions": [],
            })
            reviewed_export = client.get(
                f"/api/scans/{first_scan}/identity-read/reviewed-identities/export.csv"
            )

            with patch(
                "app.services.scan_runner.generate_candidate_pairs",
                side_effect=RuntimeError("controlled synthetic demo failure"),
            ):
                with pytest.raises(RuntimeError, match="controlled synthetic demo failure"):
                    ScanRunner(session, configuration).run(
                        # Production runner sees a tiny safe synthetic shape.
                        __import__("pandas").DataFrame([
                            {"PART_NO": "FAIL-A", "DESCRIPTION": "Synthetic failure A"},
                            {"PART_NO": "FAIL-B", "DESCRIPTION": "Synthetic failure B"},
                        ]),
                        "GF-12C1 controlled failure",
                        [],
                        75,
                    )
            failed_scan = next(
                item for item in ScanRepository(session).list()
                if item.scan_name == "GF-12C1 controlled failure"
            )
            failed_detail = client.get(f"/api/scans/{failed_scan.id}")
            failed_result = client.get(
                f"/api/scans/{failed_scan.id}/identity-read/summary"
            )
            failed_export = client.get(
                f"/api/scans/{failed_scan.id}/identity-read/system-groups/export.csv"
            )

            yield {
                "session": session,
                "configuration": configuration,
                "client": client,
                "uploads": uploads,
                "scan_ids": scan_ids,
                "summaries": summaries,
                "groups": groups,
                "outcomes": outcomes,
                "details": details,
                "system_exports": system_exports,
                "semantic_fingerprints": semantic_fingerprints,
                "semantic_export_identities": semantic_export_identities,
                "before_review": before_review,
                "created_review": created_review,
                "review_history": review_history,
                "updated_review": updated_review,
                "updated_history": updated_history,
                "after_unsure": after_unsure,
                "restored_review": restored_review,
                "reviewed_export": reviewed_export,
                "failed_scan": failed_scan,
                "failed_detail": failed_detail,
                "failed_result": failed_result,
                "failed_export": failed_export,
            }
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_demo1_fixture_is_explicitly_synthetic_and_authorized_for_demo():
    assert DEMO_DATA.exists()
    assert "All rows in the demo CSV are synthetic" in DEMO_GUIDE.read_text(encoding="utf-8")
    assert "DEMO DATA IS SYNTHETIC" in DEMO_CONTRACT.read_text(encoding="utf-8")


def test_demo2_provider_none_is_enforced(demo):
    assert demo["configuration"].llm_demo_enabled is False
    assert demo["configuration"].llm_provider == "none"
    assert demo["configuration"].group_llm_provider == "none"


def test_demo3_all_three_scans_complete(demo):
    assert [item["status"] for item in demo["uploads"]] == ["COMPLETED"] * 3


def test_demo4_visible_product_ready_only_on_completion(demo):
    rows = demo["session"].query(ScanOrchestrationRun).filter(
        ScanOrchestrationRun.scan_id.in_(demo["scan_ids"])
    ).all()
    assert len(rows) == 3
    assert all(row.status == "COMPLETED" and row.visible_product_ready is True for row in rows)
    failed = demo["session"].query(ScanOrchestrationRun).filter_by(
        scan_id=demo["failed_scan"].id
    ).one()
    assert failed.status == "FAILED" and failed.visible_product_ready is False


def test_demo5_primary_result_is_authority_selected_group_first(demo):
    assert all(item["projection"]["projection_contract"] == "G2_V2" for item in demo["summaries"])
    page = (REPO_ROOT / "frontend/src/pages/ScanResults.jsx").read_text(encoding="utf-8")
    assert "Potential duplicate identities" in page
    assert "Advanced legacy pair diagnostics" in page


def test_demo6_accepted_and_review_groups_have_at_least_two_members(demo):
    assert all(
        len(group["members"]) >= 2
        for run in demo["details"]
        for group in run
    )


def test_demo7_fixture_exposes_a_three_member_identity_group(demo):
    assert [max(len(group["members"]) for group in run) for run in demo["details"]] == [3, 3, 3]


def test_demo8_conflict_and_deferred_outcomes_are_distinct(demo):
    assert [len(item["conflicts"]) for item in demo["outcomes"]] == [3, 3, 3]
    assert [len(item["deferred_work_units"]) for item in demo["outcomes"]] == [0, 0, 0]
    assert all("deferred_work_units" in item for item in demo["outcomes"])


def test_demo9_result_counts_reconcile(demo):
    session = demo["session"]
    for scan_id, summary, groups, outcomes in zip(
        demo["scan_ids"], demo["summaries"], demo["groups"], demo["outcomes"], strict=True
    ):
        discovery = session.query(IdentityDiscoveryRun).filter_by(scan_id=scan_id).one()
        evidence = session.query(IdentityEvidenceRun).filter_by(scan_id=scan_id).one()
        resolution = session.query(IdentityResolutionRun).filter_by(scan_id=scan_id).one()
        projection = session.query(G2V2ProjectionRun).filter_by(scan_id=scan_id).one()
        assert discovery.proposal_count == evidence.edge_count_persisted
        assert summary["group_count"] == groups["total"] == resolution.accepted_group_count == projection.accepted_group_count == 4
        assert summary["likely_group_count"] == resolution.likely_group_count == 1
        assert summary["review_group_count"] == resolution.review_group_count == 3
        assert summary["conflict_count"] == len(outcomes["conflicts"]) == resolution.conflict_count == 3
        assert summary["deferred_count"] == len(outcomes["deferred_work_units"]) == resolution.deferred_work_unit_count == 0
        assert summary["unassigned_count"] == len(outcomes["unassigned_records"]) == resolution.unassigned_record_count == 8


def test_demo10_review_read_works(demo):
    assert demo["review_history"].status_code == 200
    assert len(demo["review_history"].json()["items"]) == 1


def test_demo11_review_create_and_update_are_append_only(demo):
    assert demo["created_review"].status_code == 201
    assert demo["updated_review"].status_code == 201
    assert demo["restored_review"].status_code == 201
    items = demo["updated_history"].json()["items"]
    assert len(items) == 2 and sum(bool(item["is_current"]) for item in items) == 1
    assert items[-1]["supersedes_review_event_id"] == items[0]["review_event_id"]


def test_demo12_reviewed_export_contains_only_current_confirmed_review(demo):
    assert demo["before_review"].status_code == 200
    assert len(demo["before_review"].text.strip().splitlines()) == 1
    assert len(demo["after_unsure"].text.strip().splitlines()) == 1
    assert demo["reviewed_export"].status_code == 200
    assert len(demo["reviewed_export"].text.strip().splitlines()) == 4


def test_demo13_system_group_export_works(demo):
    assert all(response.status_code == 200 for response in demo["system_exports"])
    assert all(len(response.text.strip().splitlines()) == 10 for response in demo["system_exports"])


def test_demo14_exports_are_member_shaped_group_first(demo):
    header = demo["system_exports"][0].text.splitlines()[0].casefold()
    assert "group_key" in header and "stable_record_reference" in header
    assert "part_no_a" not in header and "part_no_b" not in header


def test_demo15_exports_and_results_do_not_leak_truth(demo):
    payload = "\n".join([
        *(response.text for response in demo["system_exports"]),
        demo["reviewed_export"].text,
        json.dumps(demo["summaries"]),
    ]).casefold()
    assert not any(value in payload for value in ("benchmark_truth", "truth_group", "expected_label"))


def test_demo16_no_secret_leaks_to_demo_surfaces(demo):
    payload = "\n".join([
        *(response.text for response in demo["system_exports"]),
        demo["reviewed_export"].text,
        demo["client"].get("/health").text,
        demo["client"].get("/ready").text,
        demo["client"].get("/api/llm/status").text,
    ])
    assert SENTINEL not in payload


def test_demo17_no_auto_merge_delete_or_writeback_contract():
    text = DEMO_CONTRACT.read_text(encoding="utf-8")
    assert "no automatic merge, deletion, source rewrite, or ERP/IFS writeback" in text


def test_demo18_failed_scan_is_non_authoritative(demo):
    assert demo["failed_detail"].status_code == 200
    assert demo["failed_detail"].json()["status"] == "FAILED"
    assert demo["failed_result"].status_code == 409
    assert demo["failed_export"].status_code == 409


def test_demo19_run_one_has_stable_product_fingerprint(demo):
    assert len(demo["semantic_fingerprints"][0]) == 64


def test_demo20_run_two_has_stable_product_fingerprint(demo):
    assert len(demo["semantic_fingerprints"][1]) == 64


def test_demo21_run_three_has_stable_product_fingerprint(demo):
    assert len(demo["semantic_fingerprints"][2]) == 64


def test_demo22_three_runs_are_semantically_deterministic_with_zero_providers(demo):
    assert len(set(demo["semantic_fingerprints"])) == 1
    assert demo["semantic_fingerprints"] == [
        "23b062eeb0558152fcac4097b0432b63fc49c19ccb7f414ae844e1f7cd2ae5ec"
    ] * 3
    assert demo["semantic_export_identities"][0] == demo["semantic_export_identities"][1] == demo["semantic_export_identities"][2]
    signatures = []
    for run in demo["details"]:
        signatures.append(tuple(sorted(
            (
                item["group_status"],
                tuple(sorted(member["part_no"] for member in item["members"])),
            )
            for item in run
        )))
    assert signatures[0] == signatures[1] == signatures[2]
    session = demo["session"]
    assert all(
        session.query(IdentityDiscoveryRun).filter_by(scan_id=scan_id).one().provider_request_count == 0
        and session.query(IdentityResolutionRun).filter_by(scan_id=scan_id).one().provider_request_count == 0
        for scan_id in demo["scan_ids"]
    )


def test_demo23_no_deployment_iam_or_tenancy_implementation_added():
    changed = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    forbidden = ("docker", "k8s/", "backend/app/db/", "backend/requirements")
    assert not [path for path in changed if path.casefold().startswith(forbidden)]


def test_demo24_no_production_decision_semantics_are_changed():
    changed = subprocess.run(
        ["git", "diff", "--name-only", "HEAD", "--", "backend/app"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert changed.splitlines() == []
    for document in (DEMO_CONTRACT, DEMO_RUNBOOK, PRESENTER_SCRIPT, ACCEPTANCE):
        assert document.exists()

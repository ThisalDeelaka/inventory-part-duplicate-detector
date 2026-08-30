"""PS1-PS24: bounded privacy, security, and data-boundary validation."""

from __future__ import annotations

import dataclasses
import inspect
import json
import subprocess
from pathlib import Path

import pytest

from app.api.routes_llm import _safe_http_error
from app.benchmarks.human_review_evaluation import evaluate_human_pilot_outcomes
from app.benchmarks.human_review_pilot import (
    BlindedReviewPack,
    PilotCandidateUnit,
    PrivateEvaluationManifest,
    build_synthetic_smoke_review_pack,
)
from app.benchmarks.human_review_protocol import (
    BlindedReviewRecord,
    DatasetClassification,
    HumanReviewValidationError,
    ReviewStratum,
    ValidationDatasetDescriptor,
)
from app.core.config import Settings
from app.llm.exceptions import LLMProviderConfigurationError
from app.llm.group_execution import DisabledGroupAdvisoryProvider
from app.llm.group_provider_factory import create_group_advisory_provider
from app.llm.runtime import get_llm_settings
from app.services.identity_read_export_service import (
    DEFERRED_IDENTITY_WORK_EXPORT_FIELDS,
    IDENTITY_CONFLICT_EXPORT_FIELDS,
    REVIEWED_IDENTITY_EXPORT_FIELDS_V2,
    SYSTEM_GROUP_EXPORT_FIELDS,
    _csv,
)


SENTINEL = "SYNTHETIC_TEST_SECRET_DO_NOT_EXPOSE"
BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"
REPO_ROOT = BACKEND_ROOT.parent


def _settings(**updates) -> Settings:
    values = {
        "llm_demo_enabled": False,
        "llm_provider": "none",
        "groq_api_key": "",
        "group_llm_provider": "none",
        "anthropic_api_key": "",
    }
    values.update(updates)
    return Settings(**values)


def _descriptor(dataset_id: str = "gf12-security-fixture"):
    return ValidationDatasetDescriptor(
        dataset_id=dataset_id,
        dataset_version="v1",
        dataset_fingerprint="b" * 64,
        classification=DatasetClassification.SYNTHETIC_ONLY,
    )


def _candidate(source_reference: str = "source-safe") -> PilotCandidateUnit:
    records = tuple(
        BlindedReviewRecord(
            stable_record_reference=f"safe-ref-{index}",
            source_row_reference=index,
            part_no=f"TEST-{index}",
            description=f"Synthetic safety fixture {index}",
            product_category="TEST",
            hsn_sac="0000",
            site_or_contract="TEST-SITE",
            uom="EA",
        )
        for index in (1, 2)
    )
    refs = tuple(record.stable_record_reference for record in records)
    return PilotCandidateUnit(
        source_unit_reference=source_reference,
        stratum=ReviewStratum.LIKELY_DUPLICATE_GROUP,
        records=records,
        system_status="LIKELY_DUPLICATE_GROUP",
        system_grouping=(refs,),
        internal_evidence=(("safe_reference", "synthetic-evidence"),),
    )


def _artifacts():
    return build_synthetic_smoke_review_pack(
        _descriptor(),
        production_result_fingerprint="synthetic-production-result",
        candidate_units=(_candidate(),),
    )


def _production_sources():
    return tuple(
        path for path in APP_ROOT.rglob("*.py") if "benchmarks" not in path.parts
    )


def test_ps1_provider_none_default_is_preserved():
    source = (APP_ROOT / "core" / "config.py").read_text(encoding="utf-8")
    assert 'os.getenv("GROUP_LLM_PROVIDER", "none")' in source
    assert _settings().group_llm_provider == "none"


def test_ps2_provider_none_makes_zero_external_calls():
    class NetworkMustNotRun:
        calls = 0

        async def post(self, *args, **kwargs):
            self.calls += 1
            raise AssertionError("network boundary invoked")

    client = NetworkMustNotRun()
    provider = create_group_advisory_provider(_settings(), client=client)
    assert isinstance(provider, DisabledGroupAdvisoryProvider)
    assert provider.enabled is False
    assert client.calls == 0


def test_ps3_benchmark_evaluator_cannot_trigger_provider():
    sources = tuple((APP_ROOT / "benchmarks").glob("gf12_*.py"))
    combined = "\n".join(path.read_text(encoding="utf-8") for path in sources).lower()
    for forbidden in ("httpx", "groq", "anthropic", "group_provider_factory"):
        assert forbidden not in combined


def test_ps4_human_review_tooling_cannot_trigger_provider():
    sources = tuple((APP_ROOT / "benchmarks").glob("human_review_*.py"))
    combined = "\n".join(path.read_text(encoding="utf-8") for path in sources).lower()
    for forbidden in ("httpx", "requests", "groq", "anthropic", "api_key"):
        assert forbidden not in combined
    assert _artifacts().blinded_pack.review_units


def test_ps5_synthetic_secret_absent_from_api_and_result_serialization(client):
    configuration = _settings(groq_api_key=SENTINEL, anthropic_api_key=SENTINEL)
    client.app.dependency_overrides[get_llm_settings] = lambda: configuration
    response = client.get("/api/llm/status")
    assert response.status_code == 200
    assert SENTINEL not in response.text
    assert SENTINEL not in json.dumps(response.json(), sort_keys=True)


def test_ps6_synthetic_secret_absent_from_exports():
    field_sets = (
        SYSTEM_GROUP_EXPORT_FIELDS,
        REVIEWED_IDENTITY_EXPORT_FIELDS_V2,
        IDENTITY_CONFLICT_EXPORT_FIELDS,
        DEFERRED_IDENTITY_WORK_EXPORT_FIELDS,
    )
    output = "\n".join(_csv(fields, []) for fields in field_sets)
    assert SENTINEL not in output
    assert not any("secret" in field.lower() or "api_key" in field.lower()
                   for fields in field_sets for field in fields)


def test_ps7_synthetic_secret_absent_from_human_review_artifacts():
    result = _artifacts()
    assert SENTINEL not in result.blinded_pack.to_json()
    assert SENTINEL not in result.private_manifest.to_json()


def test_ps8_synthetic_secret_absent_from_evaluation_artifacts():
    result = _artifacts()
    evaluation = evaluate_human_pilot_outcomes(
        result.blinded_pack, result.private_manifest, ()
    )
    assert SENTINEL not in evaluation.to_json()


def test_ps9_synthetic_secret_absent_from_captured_logs_and_errors(caplog):
    error = _safe_http_error(LLMProviderConfigurationError(SENTINEL))
    assert SENTINEL not in str(error.detail)
    assert error.detail == {
        "category": "configuration",
        "message": "LLM provider configuration is unavailable",
    }
    assert SENTINEL not in caplog.text


def test_ps10_failure_path_does_not_dump_environment():
    error = _safe_http_error(RuntimeError(SENTINEL))
    payload = json.dumps(error.detail, sort_keys=True).lower()
    assert SENTINEL.lower() not in payload
    assert "environ" not in payload
    assert "traceback" not in payload
    assert "locals" not in payload


def test_ps11_blinded_pack_field_allowlist_is_enforced():
    assert {field.name for field in dataclasses.fields(BlindedReviewRecord)} == {
        "stable_record_reference", "source_row_reference", "part_no",
        "description", "product_category", "hsn_sac", "site_or_contract", "uom",
    }
    assert {field.name for field in dataclasses.fields(BlindedReviewPack)} == {
        "review_protocol_version", "review_pack_version", "dataset_id",
        "dataset_version", "dataset_fingerprint", "evidence_classification",
        "sampling_seed", "review_units", "pack_fingerprint",
    }


def test_ps12_blinded_pack_hides_status_scores_truth_and_stratum():
    payload = _artifacts().blinded_pack.to_json().lower()
    for forbidden in (
        "system_status", "system_score", "retrieval_channel", "fusion_score",
        "rrf", "gf4", "gf5", "benchmark_truth", "expected_label",
        "sampling_stratum", "internal_evidence",
    ):
        assert forbidden not in payload


def test_ps13_private_manifest_excludes_secrets_and_unrelated_raw_fields():
    assert {field.name for field in dataclasses.fields(PrivateEvaluationManifest)} == {
        "review_protocol_version", "review_pack_version", "dataset_id",
        "dataset_version", "dataset_fingerprint", "evidence_classification",
        "production_result_fingerprint", "sampling_seed", "review_units",
        "sampling_counts", "exclusions", "blinded_pack_fingerprint",
        "manifest_fingerprint",
    }
    payload = _artifacts().private_manifest.to_json().lower()
    assert SENTINEL.lower() not in payload
    for forbidden in ("api_key", "authorization", "token", "raw_environment"):
        assert forbidden not in payload


def test_ps14_business_exports_exclude_benchmark_truth():
    fields = set(
        SYSTEM_GROUP_EXPORT_FIELDS + REVIEWED_IDENTITY_EXPORT_FIELDS_V2
        + IDENTITY_CONFLICT_EXPORT_FIELDS + DEFERRED_IDENTITY_WORK_EXPORT_FIELDS
    )
    assert not fields.intersection({
        "benchmark_truth", "expected_label", "truth_group_id",
        "evaluation_fingerprint", "exact_group_match_rate",
    })


def test_ps15_business_exports_exclude_offline_human_review_labels():
    fields = set(
        SYSTEM_GROUP_EXPORT_FIELDS + REVIEWED_IDENTITY_EXPORT_FIELDS_V2
        + IDENTITY_CONFLICT_EXPORT_FIELDS + DEFERRED_IDENTITY_WORK_EXPORT_FIELDS
    )
    assert not fields.intersection({
        "review_label_schema_version", "record_refs_presented",
        "same_item_groups", "unmatched_record_refs", "insufficient_evidence_refs",
        "reviewer_role", "sampling_stratum", "blinded_pack_fingerprint",
    })


def test_ps16_production_reverse_import_isolation():
    offenders = [
        path for path in _production_sources()
        if "app.benchmarks" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_ps17_output_path_from_valid_artifact_ids_stays_under_approved_directory(tmp_path):
    approved = (tmp_path / "approved-gf12-output").resolve()
    pack = _artifacts().blinded_pack
    for unit in pack.review_units:
        target = (approved / pack.dataset_id / f"{unit.review_unit_id}.json").resolve()
        assert target.is_relative_to(approved)


def test_ps18_path_traversal_identifier_is_rejected_fail_closed():
    with pytest.raises(HumanReviewValidationError) as exc_info:
        build_synthetic_smoke_review_pack(
            _descriptor("../outside"),
            production_result_fingerprint="synthetic-production-result",
            candidate_units=(_candidate(),),
        )
    assert exc_info.value.code == "DATASET_ID_INVALID"


def test_ps19_malformed_and_missing_column_inputs_fail_safely(client):
    malformed = client.post(
        "/api/scans/validate-only",
        files={"file": ("bad.csv", b"", "text/csv")},
    )
    assert malformed.status_code == 400
    assert malformed.json()["detail"] == "CSV file is empty"
    missing = client.post(
        "/api/scans/validate-only",
        files={"file": ("missing.csv", b"EXTRA\nvalue\n", "text/csv")},
    )
    assert missing.status_code == 200
    assert missing.json()["valid"] is False
    assert set(missing.json()["missing_required_columns"]) == {"PART_NO", "DESCRIPTION"}


def test_ps20_record_content_cannot_alter_provider_configuration(client):
    configuration = _settings()
    before = configuration.model_dump()
    response = client.post(
        "/api/scans/validate-only",
        files={
            "file": (
                "extra.csv",
                b"PART_NO,DESCRIPTION,GROUP_LLM_PROVIDER\n1,fixture,claude\n",
                "text/csv",
            )
        },
    )
    assert response.status_code == 200
    assert configuration.model_dump() == before
    assert configuration.group_llm_provider == "none"


def test_ps21_record_content_cannot_alter_output_path(tmp_path):
    source = "../../outside/record-controlled"
    result = build_synthetic_smoke_review_pack(
        _descriptor(),
        production_result_fingerprint="synthetic-production-result",
        candidate_units=(_candidate(source),),
    )
    unit_id = result.blinded_pack.review_units[0].review_unit_id
    assert unit_id.startswith("hru-")
    assert "/" not in unit_id and "\\" not in unit_id and ".." not in unit_id
    target = (tmp_path / f"{unit_id}.json").resolve()
    assert target.is_relative_to(tmp_path.resolve())


def test_ps22_source_mutation_remains_zero():
    candidate = _candidate()
    before = dataclasses.asdict(candidate)
    result = build_synthetic_smoke_review_pack(
        _descriptor(),
        production_result_fingerprint="synthetic-production-result",
        candidate_units=(candidate,),
    )
    evaluate_human_pilot_outcomes(result.blinded_pack, result.private_manifest, ())
    assert dataclasses.asdict(candidate) == before


def test_ps23_no_schema_or_migration_change():
    changed = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    forbidden = (
        "backend/app/db/models.py", "backend/app/db/migrations.py",
        "frontend/package", "docker",
    )
    assert not [path for path in changed if path.lower().startswith(forbidden)]


def test_ps24_only_bounded_xlsx_export_production_change():
    changed = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    production_changes = [
        path for path in changed
        if path.startswith("backend/app/") and not path.startswith("backend/app/benchmarks/")
    ]
    allowed = {
        "backend/app/api/routes_identity_groups.py",
        "backend/app/services/identity_read_export_service.py",
        "backend/app/services/identity_read_xlsx_export_service.py",
    }
    assert set(production_changes) <= allowed
    if production_changes:
        diff = subprocess.run(
            ["git", "diff", "--unified=0", "HEAD", "--", *production_changes],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert "authority_selected_system_groups_to_xlsx" in diff
        for forbidden in ("generate_candidate_pairs", "threshold", "score_candidate"):
            assert forbidden not in diff
    assert "app.benchmarks" not in inspect.getsource(
        __import__("app.services.scan_runner", fromlist=["ScanRunner"])
    )

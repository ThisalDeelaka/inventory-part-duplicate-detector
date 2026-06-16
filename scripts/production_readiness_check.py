import csv
import io
import json
import os
import statistics
import sys
import time
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient` is deprecated.*")

from fastapi.testclient import TestClient  # noqa: E402

from app.engine.scoring import score_candidate  # noqa: E402
from app.main import app  # noqa: E402


SELECTED_FIELDS = (
    "CONTRACT,TYPE_CODE,UNIT_MEAS,PRIME_COMMODITY,SECOND_COMMODITY,"
    "HAZARD_CODE,ACCOUNTING_GROUP,PART_PRODUCT_CODE,PART_PRODUCT_FAMILY,"
    "PRODUCT_CATEGORY_ID,HSN_SAC_CODE"
)


def timed(fn):
    started = time.perf_counter()
    value = fn()
    return value, round(time.perf_counter() - started, 3)


def post_file(client, path: Path, threshold=60):
    with path.open("rb") as handle:
        return client.post(
            "/api/scans/upload",
            files={"file": (path.name, handle, "text/csv")},
            data={
                "selected_fields": SELECTED_FIELDS,
                "threshold": str(threshold),
                "scan_name": f"Readiness scan - {path.name}",
            },
        )


def run_exact_export_check(client):
    exact_file = ROOT.parent / "data set.csv"
    response, elapsed = timed(lambda: post_file(client, exact_file))
    body = response.json()
    candidates = client.get(f"/api/scans/{body['scan_id']}/candidates").json() if response.status_code == 200 else []
    warnings = client.get(f"/api/scans/{body['scan_id']}/warnings").json() if response.status_code == 200 else []
    return {
        "status_code": response.status_code,
        "elapsed_seconds": elapsed,
        "records": body.get("total_records"),
        "candidates": len(candidates),
        "warnings": len(warnings),
        "top_score": candidates[0]["similarity_score"] if candidates else None,
        "passed": response.status_code == 200 and body.get("total_records") == 99 and len(candidates) > 0,
    }


def run_failure_checks(client):
    empty = client.post(
        "/api/scans/validate-only",
        files={"file": ("empty.csv", b"", "text/csv")},
        data={"selected_fields": "CONTRACT"},
    )
    missing_description = client.post(
        "/api/scans/validate-only",
        files={"file": ("missing.csv", b"PART_NO\nA\n", "text/csv")},
        data={"selected_fields": "CONTRACT"},
    )
    high_null = client.post(
        "/api/scans/validate-only",
        files={
            "file": (
                "high-null.csv",
                b"PART_NO,DESCRIPTION,CONTRACT,PRIME_COMMODITY\nA,MCB30A,S1,\nB,MCB 30 A,S1,\n",
                "text/csv",
            )
        },
        data={"selected_fields": "CONTRACT,PRIME_COMMODITY"},
    )
    return {
        "empty_file_status": empty.status_code,
        "missing_description_status": missing_description.status_code,
        "missing_description_valid": missing_description.json().get("valid"),
        "high_null_warnings": high_null.json().get("warnings", []),
        "passed": empty.status_code == 400
        and missing_description.status_code == 200
        and missing_description.json().get("valid") is False
        and any(w["warning_type"] == "HIGH_NULL_FIELD" for w in high_null.json().get("warnings", [])),
    }


def run_model_failure_checks():
    cases = [
        ("Generator Oil Filter", "Generator Air Filter", "critical_modifier"),
        ("Bolt 10MM", "Bolt 12MM", "numeric_mismatch"),
        ("Rubber Glove Left", "Rubber Glove Right", "direction_mismatch"),
        ("MCB30A", "MCB 30 Amp", "positive_control"),
    ]
    rows = []
    for a, b, label in cases:
        result = score_candidate(
            {"PART_NO": "A", "DESCRIPTION": a, "CONTRACT": "S1", "UNIT_MEAS": "PCS"},
            {"PART_NO": "B", "DESCRIPTION": b, "CONTRACT": "S1", "UNIT_MEAS": "PCS"},
            ["CONTRACT", "UNIT_MEAS"],
        )
        rows.append({"case": label, "score": result["final_score"], "confidence": result["confidence_level"], "explanation": result["explanation"]})
    return {
        "cases": rows,
        "passed": all(row["score"] < 75 for row in rows if row["case"] != "positive_control")
        and next(row for row in rows if row["case"] == "positive_control")["score"] >= 75,
    }


def run_load_checks(client):
    scenarios = [
        {"record_count": 500, "duplicate_rate": 0.15, "variation_rate": 0.3, "threshold": 70},
        {"record_count": 2000, "duplicate_rate": 0.15, "variation_rate": 0.3, "threshold": 70},
        {"record_count": 5000, "duplicate_rate": 0.15, "variation_rate": 0.3, "threshold": 70},
    ]
    results = []
    for scenario in scenarios:
        response, elapsed = timed(lambda s=scenario: client.post("/api/load-test/run", json=s))
        body = response.json()
        results.append({"status_code": response.status_code, "client_elapsed_seconds": elapsed, **body})
    times = [item["processing_time_seconds"] for item in results if item["status_code"] == 200]
    return {
        "results": results,
        "max_processing_seconds": max(times) if times else None,
        "median_processing_seconds": statistics.median(times) if times else None,
        "passed": all(item["status_code"] == 200 for item in results)
        and all(item["candidate_pair_count"] <= 20000 for item in results),
    }


def main():
    report_path = ROOT / "docs" / "production_readiness_results.json"
    os.environ.setdefault("MAX_CSV_RECORDS", "100000")
    with TestClient(app) as client:
        report = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "health": client.get("/health").json(),
            "ready": client.get("/ready").json(),
            "exact_erp_export": run_exact_export_check(client),
            "failure_handling": run_failure_checks(client),
            "model_failure_cases": run_model_failure_checks(),
            "load_tests": run_load_checks(client),
        }
    report["overall_passed"] = all(
        [
            report["health"].get("status") == "healthy",
            report["ready"].get("status") == "ready",
            report["exact_erp_export"]["passed"],
            report["failure_handling"]["passed"],
            report["model_failure_cases"]["passed"],
            report["load_tests"]["passed"],
        ]
    )
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["overall_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

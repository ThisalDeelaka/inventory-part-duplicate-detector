from app.engine.models import PartRecord
from app.engine.pipeline import build_pipeline_summary, run_duplicate_detection_pipeline


def record(part_no, description, contract="S1", **extra):
    raw = {
        "PART_NO": part_no,
        "DESCRIPTION": description,
        "CONTRACT": contract,
        "UNIT_MEAS": "PCS",
    }
    raw.update(extra)
    return PartRecord(part_no=part_no, description=description, contract=contract, raw=raw)


def statuses(results):
    return [result.status for result in results]


def test_pipeline_returns_duplicate_candidate_for_dec_synonyms():
    results = run_duplicate_detection_pipeline([
        record("DEC CO1", "Decicated Coconut type 1"),
        record("DEC C01", "Dec Coco 1"),
    ], ["CONTRACT", "UNIT_MEAS"])

    assert statuses(results) == ["DUPLICATE_CANDIDATE"]
    assert "desiccated coconut type 1" in results[0].explanation.lower()


def test_pipeline_returns_related_but_not_duplicate_for_variant_pairs():
    results = run_duplicate_detection_pipeline([
        record("MCB-20", "MCB 20A"),
        record("MCB-30", "MCB30A"),
        record("PAINT-RED", "RED PAINT 1L CAN"),
        record("PAINT-BLUE", "BLUE PAINT 1L CAN"),
        record("GEN-FUEL-FLT", "Generator Fuel Filter"),
        record("GEN-AIR-FLT", "Generator Air Filter"),
    ], ["CONTRACT", "UNIT_MEAS"])

    assert statuses(results).count("RELATED_BUT_NOT_DUPLICATE") >= 3
    explanations = " ".join(result.explanation.lower() for result in results)
    assert "rating differs" in explanations
    assert "color differs" in explanations
    assert "function/media differs" in explanations


def test_pipeline_does_not_mark_generic_labels_as_duplicate_candidate():
    results = run_duplicate_detection_pipeline([
        record("TR LABELS", "Labels"),
        record("TR WARNING LABELS", "Warning labels"),
    ], ["CONTRACT", "UNIT_MEAS"])

    assert results
    assert results[0].status != "DUPLICATE_CANDIDATE"


def test_pipeline_supports_cross_site_standardization_mode():
    results = run_duplicate_detection_pipeline([
        record("A", "SS Pipe", contract="S1"),
        record("B", "Stainless Steel Pipe", contract="S2"),
    ], ["UNIT_MEAS"], cross_site=True)

    assert statuses(results) == ["CROSS_SITE_STANDARDIZATION_CANDIDATE"]


def test_pipeline_summary_counts_results_by_status():
    results = run_duplicate_detection_pipeline([
        record("DEC CO1", "Decicated Coconut type 1"),
        record("DEC C01", "Dec Coco 1"),
        record("MCB-20", "MCB 20A"),
        record("MCB-30", "MCB30A"),
    ], ["CONTRACT", "UNIT_MEAS"])
    summary = build_pipeline_summary(results)

    assert summary["total_results"] == len(results)
    assert summary["counts_by_status"]["DUPLICATE_CANDIDATE"] == 1
    assert summary["counts_by_status"]["RELATED_BUT_NOT_DUPLICATE"] == 1

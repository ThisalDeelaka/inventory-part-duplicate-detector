from app.core.config import settings
from app.engine.models import PartRecord
from app.engine.pipeline import run_duplicate_detection_pipeline


CSV = b"""PART_NO,DESCRIPTION,CONTRACT,UNIT_MEAS
DEC CO1,Decicated Coconut type 1,SMBE,PCS
DEC C01,Dec Coco 1,SMBE,PCS
MCB-20,MCB 20A,SMBE,PCS
MCB-30,MCB30A,SMBE,PCS
PAINT-RED,RED PAINT 1L CAN,SMBE,PCS
PAINT-BLUE,BLUE PAINT 1L CAN,SMBE,PCS
SP-GEN-FUEL-FLT,Generator Fuel Filter,SMBE,PCS
SP-GEN-AIR-FLT,Generator Air Filter,SMBE,PCS
TR LABELS,Labels,SMBE,PCS
TR WARNING LABELS,Warning labels,SMBE,PCS
"""


def _pair_key(candidate):
    return frozenset({candidate["part_no_a"], candidate["part_no_b"]})


def _pipeline_statuses():
    records = [
        PartRecord(
            part_no="DEC CO1",
            description="Decicated Coconut type 1",
            contract="SMBE",
            raw={"PART_NO": "DEC CO1", "DESCRIPTION": "Decicated Coconut type 1", "CONTRACT": "SMBE", "UNIT_MEAS": "PCS"},
        ),
        PartRecord(
            part_no="DEC C01",
            description="Dec Coco 1",
            contract="SMBE",
            raw={"PART_NO": "DEC C01", "DESCRIPTION": "Dec Coco 1", "CONTRACT": "SMBE", "UNIT_MEAS": "PCS"},
        ),
        PartRecord(
            part_no="MCB-20",
            description="MCB 20A",
            contract="SMBE",
            raw={"PART_NO": "MCB-20", "DESCRIPTION": "MCB 20A", "CONTRACT": "SMBE", "UNIT_MEAS": "PCS"},
        ),
        PartRecord(
            part_no="MCB-30",
            description="MCB30A",
            contract="SMBE",
            raw={"PART_NO": "MCB-30", "DESCRIPTION": "MCB30A", "CONTRACT": "SMBE", "UNIT_MEAS": "PCS"},
        ),
        PartRecord(
            part_no="PAINT-RED",
            description="RED PAINT 1L CAN",
            contract="SMBE",
            raw={"PART_NO": "PAINT-RED", "DESCRIPTION": "RED PAINT 1L CAN", "CONTRACT": "SMBE", "UNIT_MEAS": "PCS"},
        ),
        PartRecord(
            part_no="PAINT-BLUE",
            description="BLUE PAINT 1L CAN",
            contract="SMBE",
            raw={"PART_NO": "PAINT-BLUE", "DESCRIPTION": "BLUE PAINT 1L CAN", "CONTRACT": "SMBE", "UNIT_MEAS": "PCS"},
        ),
    ]
    return {result.status for result in run_duplicate_detection_pipeline(records, ["CONTRACT", "UNIT_MEAS"])}


def test_redesigned_scan_api_shape_and_saved_statuses(client, monkeypatch):
    monkeypatch.setattr(settings, "use_redesigned_engine", True)

    upload = client.post(
        "/api/scans/upload",
        files={"file": ("parts.csv", CSV, "text/csv")},
        data={"selected_fields": '["CONTRACT","UNIT_MEAS"]', "threshold": "0", "scan_name": "Redesigned E2E"},
    )

    assert upload.status_code == 200
    scan = upload.json()
    assert scan["status"] == "COMPLETED"

    response = client.get(f"/api/scans/{scan['id']}/candidates")
    assert response.status_code == 200
    candidates = response.json()
    assert candidates

    sample = candidates[0]
    for field in (
        "similarity_score",
        "recommended_action",
        "review_status",
        "business_status",
        "confidence_level",
        "explanation",
    ):
        assert field in sample

    # The redesigned adapter includes confidence_score before persistence.
    # The current API persists similarity_score and confidence_level only.
    assert "confidence_score" not in sample

    by_pair = {_pair_key(candidate): candidate for candidate in candidates}
    dec = by_pair[frozenset({"DEC CO1", "DEC C01"})]
    assert dec["business_status"] == "DUPLICATE_CANDIDATE"
    assert dec["explanation"]

    mcb = by_pair[frozenset({"MCB-20", "MCB-30"})]
    assert mcb["business_status"] == "RELATED_BUT_NOT_DUPLICATE"

    paint = by_pair[frozenset({"PAINT-RED", "PAINT-BLUE"})]
    assert paint["business_status"] == "RELATED_BUT_NOT_DUPLICATE"

    labels = by_pair[frozenset({"TR LABELS", "TR WARNING LABELS"})]
    assert labels["business_status"] != "DUPLICATE_CANDIDATE"

    saved_statuses = {candidate["business_status"] for candidate in candidates}
    produced_statuses = _pipeline_statuses()
    assert "DUPLICATE_CANDIDATE" in saved_statuses
    assert "RELATED_BUT_NOT_DUPLICATE" in saved_statuses
    assert produced_statuses <= saved_statuses | {"INSUFFICIENT_DATA", "POSSIBLE_DUPLICATE_REVIEW"}

import pandas as pd

from app.core.config import settings
from app.services.scan_runner import ScanRunner


class FakeDb:
    def __init__(self):
        self.committed = False
        self.rolled_back = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class FakeScan:
    id = 101
    total_candidates = 0


class FakeScanRepository:
    def __init__(self):
        self.scan = FakeScan()
        self.updated = None

    def create(self, scan_name, selected_fields, threshold, source_type, scan_mode):
        self.scan.scan_name = scan_name
        self.scan.selected_fields = selected_fields
        self.scan.threshold = threshold
        self.scan.source_type = source_type
        self.scan.scan_mode = scan_mode
        return self.scan

    def update_status(self, scan, status, **kwargs):
        self.updated = {"status": status, **kwargs}
        for key, value in kwargs.items():
            setattr(scan, key, value)
        scan.status = status
        return scan


class FakeWarnings:
    def __init__(self):
        self.items = []

    def save(self, scan_id, warning):
        self.items.append((scan_id, warning))

    def count_for_scan(self, scan_id):
        return len(self.items)


class FakeCandidates:
    def __init__(self):
        self.items = []

    def save(self, scan_id, record_a, record_b, result):
        self.items.append((scan_id, record_a, record_b, result))


def frame():
    return pd.DataFrame([
        {
            "PART_NO": "DEC CO1",
            "DESCRIPTION": "Decicated Coconut type 1",
            "CONTRACT": "SMBE",
            "UNIT_MEAS": "PCS",
        },
        {
            "PART_NO": "DEC C01",
            "DESCRIPTION": "Dec Coco 1",
            "CONTRACT": "SMBE",
            "UNIT_MEAS": "PCS",
        },
    ])


def mixed_status_frame():
    return pd.DataFrame([
        {"PART_NO": "DEC CO1", "DESCRIPTION": "Decicated Coconut type 1", "CONTRACT": "SMBE", "UNIT_MEAS": "PCS"},
        {"PART_NO": "DEC C01", "DESCRIPTION": "Dec Coco 1", "CONTRACT": "SMBE", "UNIT_MEAS": "PCS"},
        {"PART_NO": "MCB-20", "DESCRIPTION": "MCB 20A", "CONTRACT": "SMBE", "UNIT_MEAS": "PCS"},
        {"PART_NO": "MCB-30", "DESCRIPTION": "MCB30A", "CONTRACT": "SMBE", "UNIT_MEAS": "PCS"},
        {"PART_NO": "TR LABELS", "DESCRIPTION": "Labels", "CONTRACT": "SMBE", "UNIT_MEAS": "PCS"},
        {"PART_NO": "TR WARNING LABELS", "DESCRIPTION": "Warning labels", "CONTRACT": "SMBE", "UNIT_MEAS": "PCS"},
        {"PART_NO": "BIKE-1", "DESCRIPTION": "Bicycle Tire", "CONTRACT": "SMBE", "UNIT_MEAS": "PCS"},
        {"PART_NO": "BRUSH-1", "DESCRIPTION": "Paint Brush", "CONTRACT": "SMBE", "UNIT_MEAS": "PCS"},
    ])


def runner():
    item = ScanRunner(FakeDb())
    item.scans = FakeScanRepository()
    item.warnings = FakeWarnings()
    item.candidates = FakeCandidates()
    return item


def test_legacy_mode_is_default():
    assert settings.use_redesigned_engine is False
    assert settings.redesigned_result_mode == "review"


def test_legacy_path_is_used_when_switch_false(monkeypatch):
    item = runner()
    calls = {"legacy": 0, "redesigned": 0}
    monkeypatch.setattr(settings, "use_redesigned_engine", False)
    monkeypatch.setattr(item, "_run_legacy", lambda *args: calls.__setitem__("legacy", calls["legacy"] + 1) or (0, 0))
    monkeypatch.setattr(item, "_run_redesigned", lambda *args: calls.__setitem__("redesigned", calls["redesigned"] + 1) or (0, 0))

    item.run(frame(), "scan", ["CONTRACT", "UNIT_MEAS"], 75)

    assert calls == {"legacy": 1, "redesigned": 0}


def test_redesigned_path_is_used_when_switch_true(monkeypatch):
    item = runner()
    calls = {"legacy": 0, "redesigned": 0}
    monkeypatch.setattr(settings, "use_redesigned_engine", True)
    monkeypatch.setattr(item, "_run_legacy", lambda *args: calls.__setitem__("legacy", calls["legacy"] + 1) or (0, 0))
    monkeypatch.setattr(item, "_run_redesigned", lambda *args: calls.__setitem__("redesigned", calls["redesigned"] + 1) or (0, 0))

    item.run(frame(), "scan", ["CONTRACT", "UNIT_MEAS"], 75)

    assert calls == {"legacy": 0, "redesigned": 1}


def test_redesigned_path_processes_dec_coconut_pair(monkeypatch):
    item = runner()
    monkeypatch.setattr(settings, "use_redesigned_engine", True)
    monkeypatch.setattr(settings, "redesigned_result_mode", "review")
    monkeypatch.setattr(settings, "redesigned_include_statuses", "")

    scan, pair_count = item.run(frame(), "scan", ["CONTRACT", "UNIT_MEAS"], 75)

    assert pair_count == 1
    assert scan.total_candidates == 1
    assert item.candidates.items
    result = item.candidates.items[0][3]
    assert result["business_status"] == "DUPLICATE_CANDIDATE"
    assert result["explanation"]
    assert "confidence_score" in result


def test_redesigned_review_mode_filters_noisy_statuses(monkeypatch):
    item = runner()
    monkeypatch.setattr(settings, "use_redesigned_engine", True)
    monkeypatch.setattr(settings, "redesigned_result_mode", "review")
    monkeypatch.setattr(settings, "redesigned_include_statuses", "")

    scan, _pair_count = item.run(mixed_status_frame(), "scan", ["CONTRACT", "UNIT_MEAS"], 0)
    statuses = [saved[3]["business_status"] for saved in item.candidates.items]

    assert scan.total_candidates == len(statuses)
    assert "DUPLICATE_CANDIDATE" in statuses
    assert "INSUFFICIENT_DATA" in statuses
    assert "RELATED_BUT_NOT_DUPLICATE" not in statuses
    assert "UNIQUE_NO_MATCH" not in statuses


def test_redesigned_all_mode_persists_debug_statuses(monkeypatch):
    item = runner()
    monkeypatch.setattr(settings, "use_redesigned_engine", True)
    monkeypatch.setattr(settings, "redesigned_result_mode", "all")
    monkeypatch.setattr(settings, "redesigned_include_statuses", "")

    item.run(mixed_status_frame(), "scan", ["CONTRACT", "UNIT_MEAS"], 0)
    statuses = [saved[3]["business_status"] for saved in item.candidates.items]

    assert "RELATED_BUT_NOT_DUPLICATE" in statuses
    assert "UNIQUE_NO_MATCH" in statuses


def test_explicit_redesigned_status_filter_overrides_mode(monkeypatch):
    item = runner()
    monkeypatch.setattr(settings, "use_redesigned_engine", True)
    monkeypatch.setattr(settings, "redesigned_result_mode", "all")
    monkeypatch.setattr(settings, "redesigned_include_statuses", "RELATED_BUT_NOT_DUPLICATE")

    item.run(mixed_status_frame(), "scan", ["CONTRACT", "UNIT_MEAS"], 0)
    statuses = [saved[3]["business_status"] for saved in item.candidates.items]

    assert statuses
    assert set(statuses) == {"RELATED_BUT_NOT_DUPLICATE"}

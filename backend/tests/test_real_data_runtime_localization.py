from pathlib import Path
from types import SimpleNamespace

import pytest

from app.benchmarks.real_data_runtime_localization import (
    _additional_instrumentation,
    _distribution,
    _load_real_csv,
    _work_shape_from_rows,
    inspect_database,
)
from app.benchmarks.residual_discovery_profile import _Collector
from app.services import hybrid_retrieval


def test_r3_distribution_is_bounded_aggregate_only():
    assert _distribution([2, 3, 4, 11, 26, 51, 101]) == {
        "count": 7,
        "min": 2,
        "median": 11,
        "p90": 51,
        "p95": 51,
        "p99": 51,
        "max": 101,
        "over_10": 4,
        "over_25": 3,
        "over_50": 2,
        "over_100": 1,
    }


def test_r3_work_shape_reports_counts_without_members():
    members = [
        SimpleNamespace(neighborhood_id=1, record_id=1),
        SimpleNamespace(neighborhood_id=1, record_id=2),
        SimpleNamespace(neighborhood_id=2, record_id=2),
        SimpleNamespace(neighborhood_id=2, record_id=3),
    ]
    proposals = [
        SimpleNamespace(record_id_1=1, record_id_2=2),
        SimpleNamespace(record_id_1=2, record_id_2=3),
    ]
    evidence = [
        SimpleNamespace(record_id_1=1, record_id_2=2, edge_class="CANNOT_LINK"),
        SimpleNamespace(record_id_1=2, record_id_2=3, edge_class="STRONG_SUPPORT"),
    ]
    result = _work_shape_from_rows(members, proposals, evidence)
    assert result["records_per_work_unit"]["max"] == 3
    assert result["candidate_edges_per_work_unit"]["max"] == 2
    assert result["cannot_links_per_work_unit"]["max"] == 1
    assert result["largest_work_unit_shapes"] == [{
        "records": 3, "candidate_edges": 2, "cannot_links": 1,
    }]
    assert "member_ids" not in repr(result)


def test_r3_instrumentation_restores_production_methods():
    original = hybrid_retrieval.HybridCandidateRetriever.retrieve
    collector = _Collector(python_profile_enabled=False)
    with _additional_instrumentation(collector):
        assert hybrid_retrieval.HybridCandidateRetriever.retrieve is not original
    assert hybrid_retrieval.HybridCandidateRetriever.retrieve is original


def test_r3_missing_database_is_unavailable(tmp_path):
    assert inspect_database(tmp_path / "absent.sqlite") == {"available": False}


def test_r3_rejects_unapproved_csv_before_parsing(tmp_path):
    path = tmp_path / "not-authorized.csv"
    path.write_text("PART_NO,DESCRIPTION\n1,synthetic\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256"):
        _load_real_csv(path)


def test_r3_module_has_no_environment_or_provider_dispatch_surface():
    source = Path(
        "app/benchmarks/real_data_runtime_localization.py"
    ).read_text(encoding="utf-8")
    assert "os.environ" not in source
    assert "settings." not in source
    assert "GROQ" not in source
    assert "ANTHROPIC" not in source
    assert "raw_business_rows_emitted\": False" in source

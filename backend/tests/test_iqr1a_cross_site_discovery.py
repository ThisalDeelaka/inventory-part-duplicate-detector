"""IQR-1A current-product cross-site discovery contracts."""

import json

import pandas as pd

from app.core.config import Settings
from app.db.models import (
    IdentityDiscoveryRun,
    IdentityEvidenceEdgeSnapshot,
    IdentityNeighborProposal,
    IdentityResolutionRun,
    ScanRecordSnapshot,
)
from app.engine.identity_edge import IdentityEdgeClass
from app.engine.identity_evidence_evaluator import (
    DeterministicIdentityContext,
    evaluate_canonical_identity_relationship,
)
from app.orchestration.contracts import (
    identity_discovery_scan_mode_for_orchestration,
)
from app.services.canonical_record_service import CanonicalScanRecord
from app.services.hybrid_retrieval import (
    CANONICAL_RECORD_REF_FIELD,
    HybridCandidateRetriever,
    MemoryEmbeddingVectorCache,
    _allowed_pair,
)
from app.services.scan_runner import ScanRunner


BICYCLES = (
    ("AB-BICYCLE", "AB-SA"),
    ("SD-BICYCLE", "SD-SA"),
    ("JS-BICYCLE", "JS-SA"),
    ("TD BICYCLE", "TD-SA"),
    ("HM-BICYCLE", "HM-SA"),
    ("SJ-BICYCLE", "SJ-SA"),
    ("UH-BICYCLE", "UH-SA"),
)


def record(part_no, description, site):
    return {
        "PART_NO": part_no,
        "DESCRIPTION": description,
        "CONTRACT": site,
        "UNIT_MEAS": "PCS",
        "TYPE": "Purchased",
    }


def canonical(record_id, part_no, description, site):
    return CanonicalScanRecord(
        record_id=record_id,
        scan_id=1,
        source_row_index=record_id,
        record_ref_key=f"record-{record_id}",
        source_record_fingerprint=f"source-{record_id}",
        part_no=part_no,
        description=description,
        contract=site,
        uom="PCS",
        type_code="Purchased",
        prime_commodity=None,
        second_commodity=None,
        accounting_group=None,
        part_product_code=None,
        part_product_family=None,
        product_category_id=None,
        hsn_sac_code=None,
        hazard_code=None,
        normalized_part_no=part_no.casefold(),
        normalized_description=description.casefold(),
        normalization_version="iqr1a-test-v1",
    )


def configuration(mode="group_first_primary"):
    return Settings(
        llm_provider="none",
        llm_demo_enabled=False,
        identity_orchestration_mode=mode,
        group_first_shadow_comparison_enabled=False,
        hybrid_retrieval_enabled=True,
        local_embedding_enabled=False,
        hybrid_retrieval_lexical_top_k=10,
        hybrid_retrieval_vector_top_k=10,
        hybrid_retrieval_final_top_k=10,
        hybrid_retrieval_max_pairs_per_scan=100,
        hybrid_retrieval_family_max=30,
        hybrid_retrieval_tier_a_max=100,
        hybrid_retrieval_tier_b_max=100,
        hybrid_retrieval_tier_c_max=100,
        identity_neighborhood_max_members=20,
    )


def retrieval_frame(rows):
    frame = pd.DataFrame(rows)
    frame[CANONICAL_RECORD_REF_FIELD] = [
        f"iqr1a-record-{index:04d}" for index in range(len(frame))
    ]
    return frame


def test_current_product_is_site_neutral_while_legacy_scope_is_preserved():
    assert identity_discovery_scan_mode_for_orchestration(
        "group_first_primary", "SAME_SITE_DUPLICATE"
    ) == "DISCOVERY"
    assert identity_discovery_scan_mode_for_orchestration(
        "legacy_primary", "SAME_SITE_DUPLICATE"
    ) == "SAME_SITE_DUPLICATE"
    assert identity_discovery_scan_mode_for_orchestration(
        "legacy_primary", "CROSS_SITE_STANDARDIZATION"
    ) == "CROSS_SITE_STANDARDIZATION"


def test_bounded_retrieval_recalls_all_bicycle_pairs_without_site_rejection():
    rows = retrieval_frame([record(part, "Bicycle", site) for part, site in BICYCLES])
    retriever = HybridCandidateRetriever(
        configuration(), cache=MemoryEmbeddingVectorCache()
    )

    legacy = retriever.retrieve(rows, "SAME_SITE_DUPLICATE")
    current = retriever.retrieve(
        rows, "DISCOVERY", cross_site_identity_discovery=True
    )

    assert not legacy.candidates
    assert len(current.candidates) == 21
    assert current.metrics.max_candidates_for_any_record == 6
    assert current.metrics.hybrid_candidates_skipped_by_cap == 0
    assert all(
        "CROSS_SITE_SCOPE" in candidate.evidence.blocking_signals
        for candidate in current.candidates
    )


def test_site_neutrality_does_not_create_support_or_bypass_safety():
    context = DeterministicIdentityContext("DISCOVERY", ("CONTRACT", "UNIT_MEAS"))
    unrelated = evaluate_canonical_identity_relationship(
        canonical(1, "PUMP-X500", "Pump X500", "S1"),
        canonical(2, "VALVE-Z900", "Valve Z900", "S2"),
        context,
    )
    directional_conflict = evaluate_canonical_identity_relationship(
        canonical(3, "PUMP L/S", "Pump", "S1"),
        canonical(4, "PUMP R/S", "Pump", "S2"),
        context,
    )

    assert unrelated.edge_class == IdentityEdgeClass.NON_GROUPABLE
    assert directional_conflict.edge_class == IdentityEdgeClass.CANNOT_LINK
    assert not _allowed_pair(
        record("COMMON-1", "First", "S1"),
        record("COMMON-1", "Second", "S2"),
        "DISCOVERY",
    )


def test_same_site_identity_retrieval_remains_available():
    rows = retrieval_frame([
        record("PUMP-X500-A", "Pump X500", "S1"),
        record("P-X500-B", "Pump X500", "S1"),
    ])
    result = HybridCandidateRetriever(
        configuration(), cache=MemoryEmbeddingVectorCache()
    ).retrieve(rows, "DISCOVERY", cross_site_identity_discovery=True)

    assert len(result.candidates) == 1
    assert "SAME_SITE_SCOPE" in result.candidates[0].evidence.blocking_signals


def test_weak_cross_site_channels_cannot_bridge_without_an_identity_anchor():
    rows = retrieval_frame([
        record("MTR10K-C", "Three phase electric motor 10 kW 415 V flange mounted", "S1"),
        record("MTR-5K-H1", "Electric motor 5 kW 415 V three phase", "S2"),
    ])
    result = HybridCandidateRetriever(
        configuration(), cache=MemoryEmbeddingVectorCache()
    ).retrieve(rows, "DISCOVERY", cross_site_identity_discovery=True)

    assert not result.candidates


def test_part_family_can_anchor_cross_site_discovery_without_exact_description():
    rows = retrieval_frame([
        record("AS-B38-FP", "Fuel pump assembly", "S1"),
        record("ES/AS-B38-FP", "Injection equipment", "S2"),
    ])
    result = HybridCandidateRetriever(
        configuration(), cache=MemoryEmbeddingVectorCache()
    ).retrieve(rows, "DISCOVERY", cross_site_identity_discovery=True)

    assert len(result.candidates) == 1
    assert "PART_NUMBER_FAMILY" in result.candidates[0].evidence.retrieval_sources


def test_group_first_scan_routes_bicycle_proposals_through_evidence_and_resolver(
    db, monkeypatch
):
    def provider_called(*_args, **_kwargs):
        raise AssertionError("IQR-1A deterministic scan invoked a provider")

    monkeypatch.setattr("app.llm.factory.create_llm_provider", provider_called)
    monkeypatch.setattr(
        "app.llm.groq_group_provider.create_group_advisory_provider", provider_called
    )
    rows = pd.DataFrame([record(part, "Bicycle", site) for part, site in BICYCLES])

    scan, _legacy_pair_count = ScanRunner(db, configuration()).run(
        rows,
        "IQR-1A Bicycle acceptance",
        ["CONTRACT", "UNIT_MEAS"],
        75,
        scan_mode="SAME_SITE_DUPLICATE",
        orchestration_mode="group_first_primary",
    )

    discovery = db.query(IdentityDiscoveryRun).filter_by(scan_id=scan.id).one()
    proposals = db.query(IdentityNeighborProposal).filter_by(scan_id=scan.id).all()
    catalog = db.query(ScanRecordSnapshot).filter_by(scan_id=scan.id).all()
    evidence = db.query(IdentityEvidenceEdgeSnapshot).filter_by(scan_id=scan.id).all()
    resolution = db.query(IdentityResolutionRun).filter_by(scan_id=scan.id).one()
    sites_by_id = {item.id: item.contract for item in catalog}

    assert scan.scan_mode == "SAME_SITE_DUPLICATE"
    assert json.loads(discovery.configuration_json)["scan_mode"] == "DISCOVERY"
    assert discovery.proposal_count == len(proposals) == 21
    assert all(sites_by_id[item.record_id_1] != sites_by_id[item.record_id_2] for item in proposals)
    assert len(evidence) == 21
    assert resolution.status == "COMPLETED"
    assert resolution.work_unit_count > 0
    assert discovery.provider_request_count == resolution.provider_request_count == 0

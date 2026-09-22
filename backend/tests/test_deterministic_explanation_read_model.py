from types import SimpleNamespace

from app.engine.identity_edge import IdentityEdgeClass
from app.g2_v2.contracts import G2V2EvidenceOrigin
from app.identity_read.contracts import (
    IdentityReadGroup,
    IdentityReadGroupMember,
    IdentityReadGroupStatus,
    IdentityReadProjectionContract,
    IdentityReadValidationMode,
    VersionedIdentityGroupKey,
)
from app.identity_read.deterministic_explanations import (
    GROUP_EXPLANATION_VERSION,
    PAIR_READ_MODEL_VERSION,
    project_group_explanation,
    render_reason_code,
)
from app.match_strength.contracts import MatchBand, MatchStrengthStatus
from app.resolution.pair_explanation import (
    PairExplanationAvailability,
    canonical_json,
    project_proposal_pair_explanation,
)
from app.identity_read.key_codec import serialize_versioned_identity_group_key
from test_group_first_backend_inversion import authoritative_group, review_scan


def _evaluated():
    return SimpleNamespace(
        record_id_1=1, record_id_2=2,
        edge_class=IdentityEdgeClass.REVIEW_SUPPORT,
        classification_reason_codes=(
            "CROSS_FIELD_IDENTITY_INCOHERENCE", "DETERMINISTIC_LIKELY_DUPLICATE",
            "LEXICAL_SUPPORT_NOT_INDEPENDENT",
        ),
        evaluation_algorithm_version="canonical-evaluator-v1",
        evidence_fingerprint="evidence-1-2", deterministic_score=97.5,
        component_scores_json=canonical_json({"description_similarity": 92.5}),
        rule_decision="ALLOW_REVIEW", rejection_reason="",
        protected_conflicts_json="[]",
        generic_evidence_json=canonical_json({"generic_description_warning": False}),
        technical_evidence_json=canonical_json({
            "normalized_description_1": "bearing 6205 left",
            "normalized_description_2": "bearing 6205 right",
        }),
        uom_context_json=canonical_json({
            "relationship": "SAME_BASIS", "reason_code": "UOM_SAME_BASIS",
            "mapping_quality": "EXACT",
        }),
        evaluation_context_json=canonical_json({"scan_mode": "SAME_SITE_DUPLICATE"}),
    )


def _member(record_id, reference, part, description, order):
    values = dict(
        record_id=record_id, stable_record_reference=reference,
        source_row_index=order, member_order=order, part_no=part,
        description=description, normalized_part_no=part.lower(),
        normalized_description=description.lower(), contract="S1", uom="EA",
        type_code=None, prime_commodity=None, second_commodity=None,
        accounting_group=None, part_product_code=None, part_product_family=None,
        product_category_id=None, hsn_sac_code=None, hazard_code=None,
    )
    return IdentityReadGroupMember(**values)


def _group(evidence):
    return IdentityReadGroup(
        versioned_group_key=VersionedIdentityGroupKey(
            1, IdentityReadProjectionContract.G2_V2, "group-1"
        ),
        status=IdentityReadGroupStatus.POSSIBLE_DUPLICATE_GROUP_REVIEW,
        member_count=2,
        members=(
            _member(1, "record-1", "A", "Bearing left", 0),
            _member(2, "record-2", "B", "Bearing right", 1),
        ),
        validation_mode=IdentityReadValidationMode.COMPLETE_PAIRWISE,
        validation_coverage=None, group_evidence_summary=None,
        bridge_risk_summary=None, genericity_risk_summary=None,
        missing_evidence_summary=None, internal_evidence=(evidence,),
        source_group_fingerprint="source", read_group_fingerprint="read",
    )


def _source():
    return SimpleNamespace(
        stable_record_reference_1="record-1",
        stable_record_reference_2="record-2",
        evidence_fingerprint="evidence-1-2",
        evidence_origin=G2V2EvidenceOrigin.PROPOSAL_EVIDENCE,
    )


def _strength():
    return SimpleNamespace(
        status=MatchStrengthStatus.SCORED, match_strength=97.5,
        match_band=MatchBand.HIGH_MATCH,
    )


def test_group_relationship_and_pair_read_models_are_specific_and_separate_score_from_state():
    source = _source()
    evidence = project_proposal_pair_explanation(
        _evaluated(), record_reference_1="record-1", record_reference_2="record-2"
    )
    result = project_group_explanation(
        _group(source), _strength(), {"evidence-1-2": evidence},
        include_details=True,
    )
    assert result.version == GROUP_EXPLANATION_VERSION
    assert result.relationship_coverage_complete is True
    assert result.group_summary.startswith("This 2-record candidate group")
    assert result.relationships[0].deterministic_score == 97.5
    assert result.relationships[0].signed_relationship == "REVIEW_SUPPORT"
    detail = result.pair_explanations[0]
    assert detail.version == PAIR_READ_MODEL_VERSION
    assert detail.availability == PairExplanationAvailability.COMPLETE.value
    assert {item.code for item in detail.safety_items} >= {
        "CROSS_FIELD_IDENTITY_INCOHERENCE", "LEXICAL_SUPPORT_NOT_INDEPENDENT"
    }
    assert any(item.numeric_value == 92.5 for item in detail.supporting_items)
    assert "caused" not in result.group_summary.lower()
    assert "decisive" not in result.group_summary.lower()


def test_unknown_reason_code_fails_safe_without_invented_semantics():
    item = render_reason_code("FUTURE_REASON_CODE")
    assert item.label == "FUTURE_REASON_CODE"
    assert item.detail == "Persisted classification reason code: FUTURE_REASON_CODE"
    assert item.source_field == "classification_reason_codes"


def test_missing_rich_source_is_explicit_partial_legacy_without_fabrication():
    source = _source()
    source.record_id_1 = 1
    source.record_id_2 = 2
    source.edge_class = IdentityEdgeClass.REVIEW_SUPPORT
    source.reason_codes = ("FUTURE_REASON_CODE",)
    source.evidence_summary = "Historical review state"
    source.evaluator_version = "legacy"
    source.deterministic_score = 75.0
    from app.identity_read.deterministic_explanations import sources_for_group
    result = project_group_explanation(
        _group(source), _strength(), sources_for_group(_group(source), {}),
        include_details=True,
    )
    detail = result.pair_explanations[0]
    assert detail.availability == "PARTIAL_LEGACY"
    assert detail.availability_message.startswith("Limited historical evidence")
    assert not detail.supporting_items


def test_complete_pair_items_are_traceable_to_persisted_fields():
    evidence = project_proposal_pair_explanation(
        _evaluated(), record_reference_1="record-1", record_reference_2="record-2"
    )
    result = project_group_explanation(
        _group(_source()), _strength(), {"evidence-1-2": evidence},
        include_details=True,
    )
    items = (
        result.pair_explanations[0].supporting_items
        + result.pair_explanations[0].weakening_items
        + result.pair_explanations[0].safety_items
    )
    assert items
    assert all(item.source_field for item in items)


def test_authoritative_api_adds_map_to_list_and_pair_details_only_to_detail(db, client):
    scan = review_scan(db)
    _snapshot, group = authoritative_group(db, scan)
    listing = client.get(f"/api/scans/{scan.id}/identity-read/groups")
    assert listing.status_code == 200
    list_explanation = listing.json()["items"][0]["deterministic_explanation"]
    assert list_explanation["version"] == GROUP_EXPLANATION_VERSION
    assert len(list_explanation["relationships"]) == 1
    assert list_explanation["pair_explanations"] == []

    key = serialize_versioned_identity_group_key(group.versioned_group_key)
    detail = client.get(f"/api/scans/{scan.id}/identity-read/groups/{key}")
    assert detail.status_code == 200
    explanation = detail.json()["deterministic_explanation"]
    assert len(explanation["pair_explanations"]) == 1
    pair = explanation["pair_explanations"][0]
    assert pair["availability"] == "COMPLETE"
    assert pair["supporting_items"]
    assert all(item["source_field"] for item in pair["supporting_items"])

import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from app.engine.identity_edge import IdentityEdgeClass
from app.resolution.contracts import (
    TARGETED_EVIDENCE_CONTRACT_V1,
    TARGETED_EVIDENCE_CONTRACT_V2,
    TARGETED_EVIDENCE_CONTRACT_VERSION,
    TargetedEvidenceReason,
    TargetedEvidenceRequest,
    TargetedEvidenceResult,
)
from app.resolution.pair_explanation import (
    PAIR_EXPLANATION_CONTRACT_VERSION,
    PairExplanationAvailability,
    canonical_json,
    project_proposal_pair_explanation,
    project_targeted_pair_explanation,
)
from app.resolution.validation import (
    targeted_result_from_evaluation,
    with_targeted_request_fingerprint,
)


def request():
    return with_targeted_request_fingerprint(TargetedEvidenceRequest(
        scan_id=1,
        record_id_1=10,
        record_id_2=20,
        reason=TargetedEvidenceReason.BRIDGE_CROSS_CHECK,
        requesting_work_unit_reference="neighborhood-1",
        request_fingerprint="",
        record_reference_1="scan-1-row-9",
        record_reference_2="scan-1-row-19",
    ))


def evaluated():
    return SimpleNamespace(
        record_id_1=10,
        record_id_2=20,
        edge_class=IdentityEdgeClass.REVIEW_SUPPORT,
        classification_reason_codes=(
            "DETERMINISTIC_LIKELY_DUPLICATE",
            "LEXICAL_SUPPORT_NOT_INDEPENDENT",
        ),
        evaluation_algorithm_version="canonical-identity-evaluator-v7",
        evidence_fingerprint="evidence-fingerprint-10-20",
        deterministic_score=94.41,
        component_scores_json=canonical_json({
            "description_similarity": 98.2,
            "tfidf_score": 97.1,
            "fuzzy_score": 99.3,
            "part_no_similarity": 70.0,
            "technical_token_score": 88.0,
        }),
        rule_decision="ALLOW",
        rejection_reason="",
        protected_conflicts_json=canonical_json([{
            "group": "UNIT_MEAS",
            "values_a": ["EA"],
            "values_b": ["PC"],
        }]),
        generic_evidence_json=canonical_json({
            "description_1_generic": False,
            "description_2_generic": False,
            "generic_description_warning": False,
            "generic_guard_reason": "",
        }),
        technical_evidence_json=canonical_json({
            "normalized_description_1": "bearing skf 6205",
            "normalized_description_2": "bearing skf 6205",
            "normalized_part_no_1": "skf6205a",
            "normalized_part_no_2": "skf6205",
            "variant_attributes_1": {"SIZE": ["6205"]},
            "variant_attributes_2": {"SIZE": ["6205"]},
            "identity_discriminator": {"protected_conflicts": []},
            "lexical_trust_assessment": {
                "requires_strong_downgrade": True,
                "risk_reasons": ["LEXICAL_SUPPORT_NOT_INDEPENDENT"],
            },
        }),
        uom_context_json=canonical_json({
            "relationship": "CONVERTIBLE",
            "reason_code": "UOM_CONVERTIBLE",
            "mapping_quality": "APPROVED",
            "penalty": 2.0,
            "identity_authority": False,
        }),
        evaluation_context_json=canonical_json({
            "evaluator_version": "canonical-identity-evaluator-v7",
            "edge_classifier_version": "identity-edge-classifier-v1",
            "identity_discriminator_version": "identity-discriminator-v1",
            "scan_mode": "SAME_SITE_DUPLICATE",
            "selected_fields": ["CONTRACT", "UNIT_MEAS"],
            "uom_is_mapping_context": True,
        }),
    )


def test_targeted_v3_preserves_rich_evaluator_facts_with_proposal_parity():
    source = evaluated()
    targeted = targeted_result_from_evaluation(request(), source)
    targeted_projection = project_targeted_pair_explanation(targeted)
    proposal_projection = project_proposal_pair_explanation(
        source,
        record_reference_1=targeted.request.record_reference_1,
        record_reference_2=targeted.request.record_reference_2,
    )

    assert targeted.evidence_contract_version == TARGETED_EVIDENCE_CONTRACT_VERSION
    assert targeted.pair_explanation_contract_version == (
        PAIR_EXPLANATION_CONTRACT_VERSION
    )
    assert targeted_projection.availability == PairExplanationAvailability.COMPLETE
    for field in (
        "deterministic_score",
        "signed_relationship",
        "component_scores",
        "classification_reason_codes",
        "rule_decision",
        "rejection_reason",
        "protected_conflicts",
        "generic_evidence",
        "technical_evidence",
        "uom_context",
        "evaluation_context",
        "evaluator_version",
        "source_evidence_fingerprint",
    ):
        assert getattr(targeted_projection, field) == getattr(proposal_projection, field)
    assert targeted_projection.missing_fields == ()


def test_explanation_serialization_and_fingerprint_are_canonical_and_deterministic():
    first = targeted_result_from_evaluation(request(), evaluated())
    payload = json.loads(first.explanation_evidence_json)
    reordered = evaluated()
    reordered.component_scores_json = json.dumps(
        dict(reversed(list(payload["component_scores"].items())))
    )
    second = targeted_result_from_evaluation(request(), reordered)

    assert first.explanation_evidence_json == canonical_json(payload)
    assert first.explanation_evidence_json == second.explanation_evidence_json
    assert first.pair_explanation_fingerprint == second.pair_explanation_fingerprint


@pytest.mark.parametrize(
    ("version", "score"),
    [
        (TARGETED_EVIDENCE_CONTRACT_V1, None),
        (TARGETED_EVIDENCE_CONTRACT_V2, 94.41),
    ],
)
def test_legacy_projection_is_explicitly_partial_without_fabricated_detail(
    version, score
):
    legacy = TargetedEvidenceResult(
        request=request(),
        edge_class=IdentityEdgeClass.REVIEW_SUPPORT,
        reason_codes=("DETERMINISTIC_REVIEW_CANDIDATE",),
        evidence_summary="ALLOW",
        evaluator_version="canonical-identity-evaluator-v7",
        evidence_fingerprint="legacy-evidence",
        evidence_contract_version=version,
        deterministic_score=score,
    )

    projection = project_targeted_pair_explanation(legacy)

    assert projection.availability == PairExplanationAvailability.PARTIAL_LEGACY
    assert projection.component_scores == {}
    assert projection.technical_evidence == {}
    assert projection.protected_conflicts == ()
    assert projection.rule_decision == "ALLOW"
    assert projection.missing_fields


def test_tampered_persisted_explanation_is_rejected_by_its_own_fingerprint():
    targeted = targeted_result_from_evaluation(request(), evaluated())
    payload = json.loads(targeted.explanation_evidence_json)
    payload["component_scores"]["description_similarity"] = 0.0
    tampered = replace(
        targeted,
        explanation_evidence_json=canonical_json(payload),
    )

    with pytest.raises(ValueError, match="fingerprint"):
        project_targeted_pair_explanation(tampered)


def test_high_match_review_safety_reason_remains_exact():
    projection = project_targeted_pair_explanation(
        targeted_result_from_evaluation(request(), evaluated())
    )

    assert projection.deterministic_score == 94.41
    assert projection.signed_relationship == IdentityEdgeClass.REVIEW_SUPPORT
    assert projection.classification_reason_codes == (
        "DETERMINISTIC_LIKELY_DUPLICATE",
        "LEXICAL_SUPPORT_NOT_INDEPENDENT",
    )
    assert projection.technical_evidence["lexical_trust_assessment"][
        "requires_strong_downgrade"
    ] is True

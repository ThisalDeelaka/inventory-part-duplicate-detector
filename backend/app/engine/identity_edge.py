import json
from dataclasses import dataclass
from enum import Enum
from itertools import combinations
from typing import Hashable, Mapping


IDENTITY_EDGE_CLASSIFIER_VERSION = "identity-edge-classifier-v1"


class IdentityEdgeClass(str, Enum):
    STRONG_SUPPORT = "STRONG_SUPPORT"
    REVIEW_SUPPORT = "REVIEW_SUPPORT"
    CANNOT_LINK = "CANNOT_LINK"
    NON_GROUPABLE = "NON_GROUPABLE"


@dataclass(frozen=True)
class IdentityEdgeClassification:
    edge_class: IdentityEdgeClass
    reason_codes: tuple[str, ...]


_NON_IDENTITY_MISMATCH_GROUPS = frozenset({"CONTRACT", "UNIT_MEAS"})
_IDENTITY_REJECTION_REASONS = frozenset({
    "HSN_SAC_CODE_MISMATCH",
    "PRODUCT_CATEGORY_ID_MISMATCH",
})


def _attribute(value, name: str, default=None):
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _critical_mismatches(evidence) -> tuple[list[dict], bool]:
    value = _attribute(evidence, "critical_mismatches", [])
    if value in (None, ""):
        return [], True
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, json.JSONDecodeError):
            return [], False
    if not isinstance(value, list):
        return [], False
    rows = []
    for item in value:
        if not isinstance(item, dict) or not str(item.get("group") or "").strip():
            return [], False
        rows.append(item)
    return rows, True


def _human_decision(evidence, feedback) -> str:
    if feedback is not None:
        decision = feedback if isinstance(feedback, str) else _attribute(
            feedback, "user_decision", ""
        )
    else:
        decision = _attribute(evidence, "review_status", "")
    return str(decision or "").strip().upper()


def _affirmative_identity_mismatch_groups(mismatches: list[dict]) -> tuple[str, ...]:
    groups = set()
    for mismatch in mismatches:
        group = str(mismatch["group"]).strip().upper()
        values_a = mismatch.get("values_a")
        values_b = mismatch.get("values_b")
        if group in _NON_IDENTITY_MISMATCH_GROUPS:
            continue
        if isinstance(values_a, list) and values_a and isinstance(values_b, list) and values_b:
            groups.add(group)
    return tuple(sorted(groups))


def classify_identity_edge(evidence, *, feedback=None) -> IdentityEdgeClassification:
    """Classify pair evidence for future grouping without provider or retrieval input."""
    human_decision = _human_decision(evidence, feedback)
    if human_decision == "NOT_DUPLICATE":
        return IdentityEdgeClassification(
            IdentityEdgeClass.CANNOT_LINK, ("HUMAN_NON_DUPLICATE",)
        )

    mismatches, valid_mismatches = _critical_mismatches(evidence)
    if not valid_mismatches:
        return IdentityEdgeClassification(
            IdentityEdgeClass.NON_GROUPABLE,
            ("INVALID_CRITICAL_MISMATCH_EVIDENCE",),
        )

    conflict_groups = _affirmative_identity_mismatch_groups(mismatches)
    if conflict_groups:
        return IdentityEdgeClassification(
            IdentityEdgeClass.CANNOT_LINK,
            tuple(f"CRITICAL_MISMATCH_{group}" for group in conflict_groups),
        )

    rejection_reason = str(_attribute(evidence, "rejection_reason", "") or "").upper()
    if rejection_reason in _IDENTITY_REJECTION_REASONS:
        return IdentityEdgeClassification(
            IdentityEdgeClass.CANNOT_LINK,
            (f"IDENTITY_RULE_{rejection_reason}",),
        )

    if human_decision == "DUPLICATE":
        return IdentityEdgeClassification(
            IdentityEdgeClass.STRONG_SUPPORT, ("HUMAN_DUPLICATE",)
        )

    business_status = str(_attribute(evidence, "business_status", "") or "").upper()
    rule_decision = str(_attribute(evidence, "rule_decision", "") or "").upper()
    if business_status == "LIKELY_DUPLICATE" and rule_decision == "ALLOW":
        return IdentityEdgeClassification(
            IdentityEdgeClass.STRONG_SUPPORT,
            ("DETERMINISTIC_LIKELY_DUPLICATE",),
        )
    if (
        business_status == "POSSIBLE_DUPLICATE_REVIEW"
        and rule_decision in {"ALLOW", "DOWNGRADE"}
        and not mismatches
    ):
        return IdentityEdgeClassification(
            IdentityEdgeClass.REVIEW_SUPPORT,
            ("DETERMINISTIC_REVIEW_CANDIDATE",),
        )

    if rejection_reason == "UNIT_MEAS_MISMATCH" or any(
        str(item.get("group") or "").upper() == "UNIT_MEAS" for item in mismatches
    ):
        reason = "UOM_MAPPING_ONLY"
    elif rule_decision == "CROSS_SITE" or rejection_reason == "CONTRACT_MISMATCH_IN_SAME_SITE_MODE":
        reason = "CROSS_SITE_SCOPE_ONLY"
    elif rejection_reason == "SAME_PART_NO":
        reason = "SAME_PART_REFERENCE"
    elif mismatches:
        reason = "NON_TERMINAL_OR_ONE_SIDED_MISMATCH"
    else:
        reason = "DETERMINISTIC_NON_GROUPABLE"
    return IdentityEdgeClassification(IdentityEdgeClass.NON_GROUPABLE, (reason,))


def group_has_cannot_link(
    members: list[Hashable] | tuple[Hashable, ...] | set[Hashable],
    edge_lookup: Mapping[frozenset[Hashable], IdentityEdgeClassification],
) -> bool:
    """Apply only the future-group cannot-link veto; this does not construct groups."""
    for left, right in combinations(members, 2):
        edge = edge_lookup.get(frozenset((left, right)))
        if edge is not None and edge.edge_class == IdentityEdgeClass.CANNOT_LINK:
            return True
    return False

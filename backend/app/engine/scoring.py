from app.engine.decision_engine import confidence_for, evaluate_candidate


def score_candidate(
    record_a, record_b, selected_fields, scan_mode="SAME_SITE_DUPLICATE",
    strict_custom_fields=None,
    *, allow_uom_mapping_review=False,
    features_a=None, features_b=None,
):
    return evaluate_candidate(
        record_a, record_b, selected_fields, scan_mode,
        allow_uom_mapping_review=allow_uom_mapping_review,
        strict_custom_fields=strict_custom_fields,
        features_a=features_a,
        features_b=features_b,
    )

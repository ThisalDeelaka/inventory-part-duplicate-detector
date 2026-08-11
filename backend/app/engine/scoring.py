from app.engine.decision_engine import confidence_for, evaluate_candidate


def score_candidate(
    record_a, record_b, selected_fields, scan_mode="SAME_SITE_DUPLICATE",
    *, allow_uom_mapping_review=False,
):
    return evaluate_candidate(
        record_a, record_b, selected_fields, scan_mode,
        allow_uom_mapping_review=allow_uom_mapping_review,
    )

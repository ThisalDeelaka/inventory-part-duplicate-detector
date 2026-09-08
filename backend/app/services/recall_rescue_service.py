import json
from collections import defaultdict

import pandas as pd
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import (
    DuplicateCandidate,
    LlmEnhancementRun,
    RecallRescuePair,
    RuleExclusionAudit,
)
from app.engine.business_rules import evaluate_hard_business_rules
from app.engine.generic_description_guard import has_generic_description
from app.engine.normalizer import extract_technical_tokens, normalize_description, normalize_part_no_with_dictionary
from app.engine.similarity_model import (
    calculate_fuzzy_similarity,
    calculate_part_no_similarity,
    calculate_technical_token_score,
    calculate_tfidf_similarity,
)
from app.engine.scoring import score_candidate
from app.services.semantic_enrichment_service import (
    bounded_record_evidence,
    semantic_evidence_fingerprint,
)


def _identity_key(record: dict) -> tuple[str, str, str]:
    return (
        str(record.get("CONTRACT") or "").strip().casefold(),
        normalize_part_no_with_dictionary(record.get("PART_NO", "")),
        normalize_description(record.get("DESCRIPTION", "")),
    )


def _pair_key(left: dict, right: dict):
    return tuple(sorted((_identity_key(left), _identity_key(right))))


def _candidate_record(candidate, side: str) -> dict:
    return {
        "CONTRACT": getattr(candidate, f"contract_{side}"),
        "PART_NO": getattr(candidate, f"part_no_{side}"),
        "DESCRIPTION": getattr(candidate, f"description_{side}"),
    }


def _score(left: dict, right: dict) -> tuple[float, list[str]]:
    tfidf = calculate_tfidf_similarity(left.get("DESCRIPTION"), right.get("DESCRIPTION"))
    fuzzy = calculate_fuzzy_similarity(left.get("DESCRIPTION"), right.get("DESCRIPTION"))
    part = calculate_part_no_similarity(left.get("PART_NO"), right.get("PART_NO"))
    technical = calculate_technical_token_score(
        extract_technical_tokens(left.get("DESCRIPTION")),
        extract_technical_tokens(right.get("DESCRIPTION")),
    )
    score = round(tfidf * .45 + fuzzy * .35 + technical * .15 + part * .05, 2)
    signals = []
    if tfidf >= 60: signals.append("TFIDF_DESCRIPTION")
    if fuzzy >= 65: signals.append("FUZZY_DESCRIPTION")
    if technical >= 70: signals.append("TECHNICAL_TOKEN_ALIGNMENT")
    if part >= 65: signals.append("PART_NUMBER_VARIATION")
    return score, signals


def build_recall_pool(
    df: pd.DataFrame,
    *,
    scan_id: int,
    scan_mode: str,
    standard_pairs: set,
    excluded_pairs: set,
    configuration: Settings,
) -> tuple[list[dict], int]:
    records = [row.to_dict() for _, row in df.head(
        configuration.llm_semantic_enrichment_max_records_per_scan
    ).iterrows() if str(row.get("DESCRIPTION", "")).strip()]
    ranked_by_row: dict[int, list[tuple[float, int, list[str]]]] = defaultdict(list)
    pair_data = {}
    for i, left in enumerate(records):
        for j in range(i + 1, len(records)):
            right = records[j]
            key = _pair_key(left, right)
            if key in standard_pairs or key in excluded_pairs:
                continue
            if _identity_key(left)[1] and _identity_key(left)[1] == _identity_key(right)[1]:
                continue
            if has_generic_description(left.get("DESCRIPTION", ""), right.get("DESCRIPTION", "")):
                continue
            rule = evaluate_hard_business_rules(left, right, scan_mode)
            if rule["blocked"]:
                continue
            deterministic = score_candidate(left, right, [], scan_mode)
            if deterministic["critical_mismatches"] or deterministic["rule_decision"] in {"REJECT", "DATA_CONFLICT", "CROSS_SITE"}:
                continue
            score, signals = _score(left, right)
            if score < configuration.llm_recall_rescue_min_score or len(signals) < 2:
                continue
            ranked_by_row[i].append((score, j, signals))
            ranked_by_row[j].append((score, i, signals))
            pair_data[(i, j)] = (left, right, score, signals)

    top_neighbors = {}
    for index, values in ranked_by_row.items():
        values.sort(key=lambda item: (-item[0], item[1]))
        top_neighbors[index] = {
            other for _, other, _ in values[:configuration.llm_recall_rescue_top_k_per_row]
        }
    selected = []
    for (i, j), (left, right, score, signals) in pair_data.items():
        left_top = j in top_neighbors.get(i, set())
        right_top = i in top_neighbors.get(j, set())
        if not (left_top or right_top):
            continue
        selected.append({
            "left": left,
            "right": right,
            "score": score,
            "signals": signals + (["RECIPROCAL_TOP_K"] if left_top and right_top else []),
            "reciprocal": left_top and right_top,
            "stable_key": _pair_key(left, right),
        })
    selected.sort(key=lambda item: (-int(item["reciprocal"]), -item["score"], item["stable_key"]))
    cap = configuration.llm_recall_rescue_max_candidates_per_scan
    skipped = max(0, len(selected) - cap)
    for rank, item in enumerate(selected[:cap], 1):
        item["rank"] = rank
    return selected[:cap], skipped


def prepare_recall_rescue(
    db: Session,
    scan,
    df: pd.DataFrame,
    configuration: Settings,
) -> int:
    run = db.query(LlmEnhancementRun).filter_by(scan_id=scan.id).first()
    if run is None:
        run = LlmEnhancementRun(scan_id=scan.id)
        db.add(run)
    standard = db.query(DuplicateCandidate).filter_by(scan_id=scan.id).all()
    exclusions = db.query(RuleExclusionAudit).filter_by(scan_id=scan.id).all()
    run.standard_candidate_count = len(standard)
    if not configuration.llm_recall_rescue_enabled:
        db.commit()
        return 0
    standard_pairs = {
        _pair_key(_candidate_record(item, "a"), _candidate_record(item, "b"))
        for item in standard
    }
    excluded_pairs = {
        _pair_key(_candidate_record(item, "a"), _candidate_record(item, "b"))
        for item in exclusions
    }
    pool, skipped = build_recall_pool(
        df,
        scan_id=scan.id,
        scan_mode=scan.scan_mode,
        standard_pairs=standard_pairs,
        excluded_pairs=excluded_pairs,
        configuration=configuration,
    )
    for item in pool:
        left = bounded_record_evidence(f"scan-{scan.id}-recall-{item['rank']}-a", item["left"])
        right = bounded_record_evidence(f"scan-{scan.id}-recall-{item['rank']}-b", item["right"])
        left_fp = semantic_evidence_fingerprint(left, configuration.groq_model)
        right_fp = semantic_evidence_fingerprint(right, configuration.groq_model)
        if right_fp < left_fp:
            left, right, left_fp, right_fp = right, left, right_fp, left_fp
        db.add(RecallRescuePair(
            scan_id=scan.id,
            left_fingerprint=left_fp,
            right_fingerprint=right_fp,
            left_evidence_json=json.dumps(left.model_dump(mode="json"), separators=(",", ":"), ensure_ascii=True),
            right_evidence_json=json.dumps(right.model_dump(mode="json"), separators=(",", ":"), ensure_ascii=True),
            rescue_score=item["score"],
            rank=item["rank"],
            signals_json=json.dumps(item["signals"], separators=(",", ":"), ensure_ascii=True),
        ))
    run.rescue_pool_considered_count = len(pool)
    run.rescue_skipped_by_cap_count = skipped
    db.commit()
    return len(pool)

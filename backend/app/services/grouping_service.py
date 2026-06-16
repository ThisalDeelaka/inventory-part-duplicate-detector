import json
from collections import defaultdict

from app.engine.scoring import confidence_for


def _candidate_to_pair(candidate):
    return {
        "candidate_id": candidate.id,
        "part_no_a": candidate.part_no_a,
        "description_a": candidate.description_a,
        "contract_a": candidate.contract_a,
        "part_no_b": candidate.part_no_b,
        "description_b": candidate.description_b,
        "contract_b": candidate.contract_b,
        "similarity_score": candidate.similarity_score,
        "confidence_level": candidate.confidence_level,
        "matched_fields": json.loads(candidate.matched_fields),
        "mismatched_fields": json.loads(candidate.mismatched_fields),
        "explanation": candidate.explanation,
    }


def _node_key(contract, part_no, description):
    return f"{contract or ''}|{part_no or ''}|{description or ''}"


def _node(contract, part_no, description):
    return {
        "key": _node_key(contract, part_no, description),
        "contract": contract,
        "part_no": part_no,
        "description": description,
    }


def _group_name(parts):
    descriptions = [part["description"] for part in parts if part.get("description")]
    if not descriptions:
        return "Possible duplicate group"
    return sorted(descriptions, key=lambda value: (len(value), value.lower()))[0]


def build_duplicate_groups(candidates, minimum_score=75.0):
    """Build business-friendly duplicate clusters from pair-level candidates.

    Pair scoring remains the source of truth. This function only creates connected
    components from medium/high confidence pairs so reviewers can see clusters.
    """
    parent = {}
    nodes = {}
    edges = []

    def find(key):
        parent.setdefault(key, key)
        if parent[key] != key:
            parent[key] = find(parent[key])
        return parent[key]

    def union(left, right):
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for candidate in candidates:
        if candidate.similarity_score < minimum_score or candidate.confidence_level not in {"HIGH", "MEDIUM"}:
            continue
        left = _node(candidate.contract_a, candidate.part_no_a, candidate.description_a)
        right = _node(candidate.contract_b, candidate.part_no_b, candidate.description_b)
        nodes[left["key"]] = left
        nodes[right["key"]] = right
        union(left["key"], right["key"])
        edges.append((left["key"], right["key"], _candidate_to_pair(candidate)))

    grouped_nodes = defaultdict(list)
    grouped_pairs = defaultdict(list)
    for key, value in nodes.items():
        grouped_nodes[find(key)].append(value)
    for left, _right, pair in edges:
        grouped_pairs[find(left)].append(pair)

    groups = []
    for root, parts in grouped_nodes.items():
        if len(parts) < 2:
            continue
        pairs = sorted(grouped_pairs[root], key=lambda item: item["similarity_score"], reverse=True)
        scores = [pair["similarity_score"] for pair in pairs]
        avg_score = round(sum(scores) / len(scores), 2) if scores else 0.0
        max_score = round(max(scores), 2) if scores else 0.0
        matched_fields = sorted({field for pair in pairs for field in pair["matched_fields"]})
        mismatched_fields = sorted({field for pair in pairs for field in pair["mismatched_fields"]})
        groups.append({
            "group_id": len(groups) + 1,
            "group_name": _group_name(parts),
            "part_count": len(parts),
            "pair_count": len(pairs),
            "average_score": avg_score,
            "top_score": max_score,
            "confidence_level": confidence_for(max_score),
            "matched_fields": matched_fields,
            "mismatched_fields": mismatched_fields,
            "summary": _build_group_summary(parts, pairs, matched_fields, mismatched_fields),
            "parts": sorted(parts, key=lambda item: (item.get("part_no") or "", item.get("contract") or "")),
            "pairs": pairs,
        })

    return sorted(groups, key=lambda item: (item["top_score"], item["part_count"]), reverse=True)


def _build_group_summary(parts, pairs, matched_fields, mismatched_fields):
    if not pairs:
        return "No qualifying medium/high confidence pairs were found for this group."
    matched = f"Matched fields: {', '.join(matched_fields)}." if matched_fields else "No shared business fields were available."
    mismatch = f" Mismatched fields: {', '.join(mismatched_fields)}." if mismatched_fields else ""
    return (
        f"{len(parts)} parts are connected by {len(pairs)} medium/high confidence candidate pair(s). "
        f"{matched}{mismatch} Review the pair-level evidence before making a master-data decision."
    )

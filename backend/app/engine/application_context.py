import re


CONTEXT_MAP = {
    "gen": "generator",
    "generator": "generator",
    "hvac": "hvac",
    "elec": "electrical",
    "electrical": "electrical",
    "hyd": "hydraulic",
    "hydraulic": "hydraulic",
    "pneu": "pneumatic",
    "pneumatic": "pneumatic",
    "auto": "vehicle",
    "veh": "vehicle",
    "vehicle": "vehicle",
    "pump": "pump",
    "comp": "compressor",
    "compressor": "compressor",
}


def _tokens(*values) -> list[str]:
    joined = " ".join("" if value is None else str(value).lower() for value in values)
    return re.sub(r"[^a-z0-9]+", " ", joined).split()


def extract_application_context(part_no: str, description: str) -> list[str]:
    contexts = []
    for token in _tokens(part_no, description):
        context = CONTEXT_MAP.get(token)
        if context and context not in contexts:
            contexts.append(context)
    return contexts


def find_application_context_mismatch(record_a, record_b) -> dict | None:
    contexts_a = extract_application_context(record_a.get("PART_NO"), record_a.get("DESCRIPTION"))
    contexts_b = extract_application_context(record_b.get("PART_NO"), record_b.get("DESCRIPTION"))
    if contexts_a and contexts_b and set(contexts_a) != set(contexts_b):
        return {"values_a": contexts_a, "values_b": contexts_b}
    return None

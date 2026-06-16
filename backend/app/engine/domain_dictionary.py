import re
from functools import lru_cache
from typing import Any


DOMAIN_TOKEN_MAP = {
    "dec": "desiccated",
    "desicated": "desiccated",
    "decicated": "desiccated",
    "decicatted": "desiccated",
    "coco": "coconut",
    "co": "coconut",
    "c01": "type 1",
    "co1": "type 1",
    "c02": "type 2",
    "co2": "type 2",
    "flt": "filter",
    "filt": "filter",
    "gen": "generator",
    "hvac": "hvac",
    "ss": "stainless steel",
    "stl": "steel",
    "bat": "battery",
    "temp": "temperature",
    "press": "pressure",
}


def _tokenize(text: Any) -> list[str]:
    if text is None:
        return []
    value = str(text).strip().lower()
    if value in {"", "nan", "none"}:
        return []
    value = re.sub(r"[^a-z0-9]+", " ", value)
    tokens = []
    for token in value.split():
        if token in DOMAIN_TOKEN_MAP:
            tokens.append(token)
        else:
            tokens.extend(re.sub(r"(?<=[a-z])(?=\d)|(?<=\d)(?=[a-z])", " ", token).split())
    return tokens


@lru_cache(maxsize=100_000)
def expand_domain_tokens(text: Any) -> str:
    words = []
    for token in _tokenize(text):
        replacement = DOMAIN_TOKEN_MAP.get(token, token)
        words.extend(replacement.split())
    return " ".join(words)


@lru_cache(maxsize=100_000)
def normalize_description_with_dictionary(text: Any) -> str:
    return expand_domain_tokens(text)


@lru_cache(maxsize=100_000)
def normalize_part_no_with_dictionary(part_no: Any) -> str:
    return expand_domain_tokens(part_no)

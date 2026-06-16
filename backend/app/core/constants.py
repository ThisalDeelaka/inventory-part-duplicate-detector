MODEL_VERSION = "hybrid-nlp-v1"

FIELD_DEFINITIONS = [
    {"field": "CONTRACT", "display": "Site", "required": False},
    {"field": "PART_NO", "display": "Part No", "required": True},
    {"field": "DESCRIPTION", "display": "Item Description", "required": True},
    {"field": "TYPE_CODE", "display": "Purchase Type", "required": False},
    {"field": "UNIT_MEAS", "display": "Inventory UOM", "required": False},
    {"field": "PRIME_COMMODITY", "display": "Com Group 01", "required": False},
    {"field": "SECOND_COMMODITY", "display": "Com Group 02", "required": False},
    {"field": "HAZARD_CODE", "display": "Safety Code", "required": False},
    {"field": "ACCOUNTING_GROUP", "display": "Accounting Group", "required": False},
    {"field": "PART_PRODUCT_CODE", "display": "Product Code", "required": False},
    {"field": "PART_PRODUCT_FAMILY", "display": "Product Family", "required": False},
    {"field": "PRODUCT_CATEGORY_ID", "display": "Product Category", "required": False},
    {"field": "HSN_SAC_CODE", "display": "HSN/SAC Code", "required": False},
]

REQUIRED_FIELDS = ["PART_NO", "DESCRIPTION"]
OPTIONAL_FIELDS = [item["field"] for item in FIELD_DEFINITIONS if not item["required"]]
SELECTABLE_FIELDS = [f for f in OPTIONAL_FIELDS]

FIELD_ALIASES = {
    "PART_TYPE": "TYPE_CODE",
    "INVENTORY_UOM": "UNIT_MEAS",
    "COMMODITY_GROUP_1": "PRIME_COMMODITY",
    "COMMODITY_GROUP_2": "SECOND_COMMODITY",
    "SAFETY_CODE": "HAZARD_CODE",
}

CONFIDENCE_ACTIONS = {
    "HIGH": "Review as likely duplicate",
    "MEDIUM": "Manual review recommended",
    "LOW": "Weak match; review only in discovery mode",
    "IGNORE": "Not likely duplicate",
}

CRITICAL_MODIFIERS = {
    "oil", "fuel", "air", "water", "hydraulic", "cabin", "lube", "coolant",
    "stainless", "carbon", "rubber", "copper", "pvc", "left", "right",
    "red", "blue", "green", "yellow", "black", "white", "orange", "purple",
    "grey", "gray", "brown", "silver", "gold",
}

STRICT_MISMATCH_FIELDS = {
    "UNIT_MEAS",
    "HSN_SAC_CODE",
    "HAZARD_CODE",
}

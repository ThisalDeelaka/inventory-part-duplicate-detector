MODEL_VERSION = "hybrid-nlp-v1"
SOURCE_ROW_INDEX_FIELD = "__SOURCE_ROW_INDEX"

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
    "STOCK_REF": "PART_NO",
    "PART_NUMBER": "PART_NO",
    "ITEM_NO": "PART_NO",
    "ITEM_NUMBER": "PART_NO",
    "ITEM_NARRATIVE": "DESCRIPTION",
    "PART_DESCRIPTION": "DESCRIPTION",
    "ITEM_DESCRIPTION": "DESCRIPTION",
    "SITE": "CONTRACT",
    "SITE_CODE": "CONTRACT",
    "CONTRACT_CODE": "CONTRACT",
    "PART_TYPE": "TYPE_CODE",
    "PURCHASE_TYPE": "TYPE_CODE",
    "INVENTORY_UOM": "UNIT_MEAS",
    "INVENTORY_UNIT_OF_MEASURE": "UNIT_MEAS",
    "UNIT_OF_MEASURE": "UNIT_MEAS",
    "UOM": "UNIT_MEAS",
    "COMMODITY_GROUP_1": "PRIME_COMMODITY",
    "COM_GROUP_01": "PRIME_COMMODITY",
    "PRIMARY_COMMODITY": "PRIME_COMMODITY",
    "COMMODITY_GROUP_2": "SECOND_COMMODITY",
    "COM_GROUP_02": "SECOND_COMMODITY",
    "SECONDARY_COMMODITY": "SECOND_COMMODITY",
    "SAFETY_CODE": "HAZARD_CODE",
    "PRODUCT_CODE": "PART_PRODUCT_CODE",
    "PRODUCT_FAMILY": "PART_PRODUCT_FAMILY",
    "PRODUCT_CATEGORY": "PRODUCT_CATEGORY_ID",
    "HSN_CODE": "HSN_SAC_CODE",
    "SAC_CODE": "HSN_SAC_CODE",
}

# These historical IFS labels are valid only as fallbacks.  Some exports include
# both "Part Description in Use" and "Part Description"; mapping both eagerly
# would make the required DESCRIPTION field ambiguous.  The validation service
# therefore uses these aliases only when no primary DESCRIPTION source exists.
FALLBACK_FIELD_ALIASES = {
    "PART_DESCRIPTION_IN_USE": "DESCRIPTION",
    "DESCRIPTION_IN_USE": "DESCRIPTION",
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

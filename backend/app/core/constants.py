MODEL_VERSION = "hybrid-nlp-v1"
SOURCE_ROW_INDEX_FIELD = "__SOURCE_ROW_INDEX"

PART_TYPES = {"INVENTORY", "PURCHASE", "SALES"}
DEFAULT_PART_TYPE = "INVENTORY"
ALL_PART_TYPES = ["INVENTORY", "PURCHASE", "SALES"]

FIELD_DEFINITIONS = [
    {"field": "CONTRACT", "display": "Site", "required": False, "part_types": ["INVENTORY", "PURCHASE"]},
    {"field": "PART_NO", "display": "Part No", "required": True, "part_types": ALL_PART_TYPES},
    {"field": "DESCRIPTION", "display": "Item Description", "required": True, "part_types": ALL_PART_TYPES},
    {"field": "TYPE_CODE", "display": "Purchase Type", "required": False, "part_types": ["INVENTORY"]},
    {"field": "UNIT_MEAS", "display": "Inventory UOM", "required": False, "part_types": ["INVENTORY"]},
    {"field": "PRIME_COMMODITY", "display": "Com Group 01", "required": False, "part_types": ["INVENTORY"]},
    {"field": "SECOND_COMMODITY", "display": "Com Group 02", "required": False, "part_types": ["INVENTORY"]},
    {"field": "HAZARD_CODE", "display": "Safety Code", "required": False, "part_types": ["INVENTORY"]},
    {"field": "ACCOUNTING_GROUP", "display": "Accounting Group", "required": False, "part_types": ["INVENTORY"]},
    {"field": "PART_PRODUCT_CODE", "display": "Product Code", "required": False, "part_types": ["INVENTORY"]},
    {"field": "PART_PRODUCT_FAMILY", "display": "Product Family", "required": False, "part_types": ["INVENTORY"]},
    {"field": "PRODUCT_CATEGORY_ID", "display": "Product Category", "required": False, "part_types": ["INVENTORY"]},
    {"field": "HSN_SAC_CODE", "display": "HSN/SAC Code", "required": False, "part_types": ["INVENTORY"]},
    {"field": "DEFAULT_UOM", "display": "Default UOM", "required": False, "part_types": ["PURCHASE"]},
    {"field": "BUYER_ID", "display": "Buyer Id", "required": False, "part_types": ["PURCHASE"]},
    {"field": "TECH_COORDINATOR", "display": "Tech Coordinator", "required": False, "part_types": ["PURCHASE"]},
    {"field": "PURCHASE_GROUP", "display": "Purchase Group", "required": False, "part_types": ["PURCHASE"]},
    {"field": "ORDER_PROC_TYPE", "display": "Order Proc Type", "required": False, "part_types": ["PURCHASE"]},
    {"field": "SALES_PART_DESCRIPTION", "display": "Sales Part Description", "required": False, "part_types": ["SALES"]},
    {"field": "SALES_UOM", "display": "Sales UOM", "required": False, "part_types": ["SALES"]},
    {"field": "PRICE_UOM", "display": "Price UOM", "required": False, "part_types": ["SALES"]},
    {"field": "SALES_PRICE_GROUP", "display": "Sales Price Group", "required": False, "part_types": ["SALES"]},
    {"field": "SALES_GROUP", "display": "Sales Group", "required": False, "part_types": ["SALES"]},
]

REQUIRED_FIELDS = ["PART_NO", "DESCRIPTION"]
OPTIONAL_FIELDS = [item["field"] for item in FIELD_DEFINITIONS if not item["required"]]
SELECTABLE_FIELDS = [f for f in OPTIONAL_FIELDS]

# UOM-style fields for the non-Inventory part types: a mismatch hard-rejects the pair,
# the same severity as the existing UNIT_MEAS (Inventory UOM) rule below.
BUILT_IN_STRICT_FIELDS = [
    {"field_key": "DEFAULT_UOM", "display_label": "Default UOM"},
    {"field_key": "SALES_UOM", "display_label": "Sales UOM"},
    {"field_key": "PRICE_UOM", "display_label": "Price UOM"},
]

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
    "DEFAULT_UNIT_OF_MEASURE": "DEFAULT_UOM",
    "PURCHASE_UOM": "DEFAULT_UOM",
    "BUYER": "BUYER_ID",
    "BUYER_CODE": "BUYER_ID",
    "TECHNICAL_COORDINATOR": "TECH_COORDINATOR",
    "ORDER_PROCUREMENT_TYPE": "ORDER_PROC_TYPE",
    "PROC_TYPE": "ORDER_PROC_TYPE",
    "SALES_DESCRIPTION": "SALES_PART_DESCRIPTION",
    "SALES_PART_DESC": "SALES_PART_DESCRIPTION",
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

CUSTOM_FIELD_MODES = {"SUPPORTING", "STRICT"}
CUSTOM_STRICT_SCORE_CAP = 45.0

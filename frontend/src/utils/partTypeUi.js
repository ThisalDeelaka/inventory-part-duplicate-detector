export const PART_TYPE_OPTIONS = [
  ['INVENTORY', 'Inventory Parts'],
  ['PURCHASE', 'Purchase Parts'],
  ['SALES', 'Sales Parts'],
]

export const DEFAULT_PART_TYPE = 'INVENTORY'

export function filterFieldsForPartType(fields, partType) {
  if (!Array.isArray(fields)) return []
  return fields.filter(field => (
    field.required || !Array.isArray(field.part_types) || field.part_types.includes(partType)
  ))
}

const INVENTORY_OVERLAP_PART_TYPES = new Set(['PURCHASE', 'SALES'])

export function supportsInventoryPartExclusion(partType) {
  return INVENTORY_OVERLAP_PART_TYPES.has(partType)
}

export const INVENTORY_PART_FILTER_HELP = {
  PURCHASE: 'Excluding skips rows whose "Inventory Part" column is Yes and scans only the rows marked No.',
  SALES: 'Excluding skips rows whose "Type of Sales Part" column is Inventory Part and scans the other types.',
}

const HIDDEN_CODE_FIELDS = new Set(['INVENTORY_PART_NO', 'INVENTORY_PART_FLAG', 'SALES_PART_TYPE'])

export function shouldShowFieldCode(field) {
  return !HIDDEN_CODE_FIELDS.has(field.field)
}

const SALES_DISPLAY_OVERRIDES = { PART_NO: 'Sales Part No' }

export function fieldDisplayForPartType(field, partType) {
  if (partType === 'SALES' && SALES_DISPLAY_OVERRIDES[field.field]) return SALES_DISPLAY_OVERRIDES[field.field]
  return field.display
}

export function partTypeLabel(partType) {
  return new Map(PART_TYPE_OPTIONS).get(partType) || 'Unknown part type'
}

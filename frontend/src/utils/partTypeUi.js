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

export function partTypeLabel(partType) {
  return new Map(PART_TYPE_OPTIONS).get(partType) || 'Unknown part type'
}

const MODES = new Set(['SUPPORTING', 'STRICT'])

export function customFieldCreatePayload(label, mode, sourceColumn) {
  const trimmed = String(label || '').trim()
  if (!trimmed) throw new Error('A label is required.')
  if (!MODES.has(mode)) throw new Error('Invalid custom field mode.')
  const payload = { display_label: trimmed, mode }
  if (typeof sourceColumn === 'string' && sourceColumn.trim()) {
    payload.source_column = sourceColumn
  }
  return payload
}

export function mergeCustomFields(builtInFields, customFields) {
  const builtIn = Array.isArray(builtInFields) ? builtInFields : []
  const custom = Array.isArray(customFields) ? customFields : []
  const asMappingField = field => ({
    field: field.field_key,
    display: field.display_label,
    required: false,
    custom: true,
    mode: field.mode,
  })
  const mappingFields = [...builtIn, ...custom.map(asMappingField)]
  const checklistFields = [
    ...builtIn.filter(field => !field.required),
    ...custom.filter(field => field.mode === 'SUPPORTING').map(asMappingField),
  ]
  return { mappingFields, checklistFields }
}

export function customFieldModeLabel(mode) {
  return mode === 'STRICT' ? 'Strict (hard mismatch rejects)' : 'Supporting (blocking + scoring)'
}

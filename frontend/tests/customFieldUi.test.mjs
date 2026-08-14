import assert from 'node:assert/strict'
import test from 'node:test'

import {
  customFieldCreatePayload,
  customFieldModeLabel,
  mergeCustomFields,
} from '../src/utils/customFieldUi.js'

test('builds a create payload and validates label/mode', () => {
  assert.deepEqual(
    customFieldCreatePayload('  Manufacturer Code  ', 'SUPPORTING', 'Mfr Code'),
    { display_label: 'Manufacturer Code', mode: 'SUPPORTING', source_column: 'Mfr Code' },
  )
  assert.deepEqual(
    customFieldCreatePayload('Manufacturer Code', 'STRICT'),
    { display_label: 'Manufacturer Code', mode: 'STRICT' },
  )
  assert.throws(() => customFieldCreatePayload('   ', 'SUPPORTING'), /label is required/)
  assert.throws(() => customFieldCreatePayload('Manufacturer Code', 'BOGUS'), /Invalid custom field mode/)
})

test('merges custom fields into mapping and duplicate-checking checklists', () => {
  const builtIn = [
    { field: 'PART_NO', display: 'Part No', required: true },
    { field: 'DESCRIPTION', display: 'Item Description', required: true },
    { field: 'CONTRACT', display: 'Site', required: false },
  ]
  const custom = [
    { id: 1, field_key: 'MANUFACTURER_CODE', display_label: 'Manufacturer Code', mode: 'SUPPORTING', aliases: [] },
    { id: 2, field_key: 'WAREHOUSE_ZONE', display_label: 'Warehouse Zone', mode: 'STRICT', aliases: ['ZONE'] },
  ]

  const { mappingFields, checklistFields } = mergeCustomFields(builtIn, custom)

  assert.deepEqual(mappingFields.map(f => f.field), ['PART_NO', 'DESCRIPTION', 'CONTRACT', 'MANUFACTURER_CODE', 'WAREHOUSE_ZONE'])

  // Only SUPPORTING custom fields (and non-required built-ins) become duplicate-checking checkboxes;
  // STRICT fields participate through the hard-reject rule instead, never the business-score checklist.
  assert.deepEqual(checklistFields.map(f => f.field), ['CONTRACT', 'MANUFACTURER_CODE'])
})

test('handles missing/empty inputs safely', () => {
  assert.deepEqual(mergeCustomFields(undefined, undefined), { mappingFields: [], checklistFields: [] })
})

test('describes custom field modes for display', () => {
  assert.match(customFieldModeLabel('STRICT'), /hard mismatch/)
  assert.match(customFieldModeLabel('SUPPORTING'), /blocking/)
})

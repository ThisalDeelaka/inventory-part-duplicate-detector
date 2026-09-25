import assert from 'node:assert/strict'
import test from 'node:test'

import {
  PART_TYPE_OPTIONS,
  fieldDisplayForPartType,
  filterFieldsForPartType,
  partTypeLabel,
  shouldShowFieldCode,
  supportsInventoryPartExclusion,
} from '../src/utils/partTypeUi.js'

const FIELDS = [
  { field: 'PART_NO', display: 'Part No', required: true, part_types: ['INVENTORY', 'PURCHASE', 'SALES'] },
  { field: 'DESCRIPTION', display: 'Item Description', required: true, part_types: ['INVENTORY', 'PURCHASE', 'SALES'] },
  { field: 'UNIT_MEAS', display: 'Inventory UOM', required: false, part_types: ['INVENTORY'] },
  { field: 'DEFAULT_UOM', display: 'Default UOM', required: false, part_types: ['PURCHASE'] },
  { field: 'PRICE_UOM', display: 'Price UOM', required: false, part_types: ['SALES'] },
]

test('filters optional fields to the selected part type but always keeps required ones', () => {
  assert.deepEqual(
    filterFieldsForPartType(FIELDS, 'INVENTORY').map(f => f.field),
    ['PART_NO', 'DESCRIPTION', 'UNIT_MEAS'],
  )
  assert.deepEqual(
    filterFieldsForPartType(FIELDS, 'PURCHASE').map(f => f.field),
    ['PART_NO', 'DESCRIPTION', 'DEFAULT_UOM'],
  )
  assert.deepEqual(
    filterFieldsForPartType(FIELDS, 'SALES').map(f => f.field),
    ['PART_NO', 'DESCRIPTION', 'PRICE_UOM'],
  )
})

test('keeps fields with no part_types tag and handles non-array input safely', () => {
  const untagged = [{ field: 'X', required: false }]
  assert.deepEqual(filterFieldsForPartType(untagged, 'SALES').map(f => f.field), ['X'])
  assert.deepEqual(filterFieldsForPartType(undefined, 'SALES'), [])
})

test('exposes three part type options with human labels', () => {
  assert.equal(PART_TYPE_OPTIONS.length, 3)
  assert.equal(partTypeLabel('SALES'), 'Sales Parts')
  assert.equal(partTypeLabel('BOGUS'), 'Unknown part type')
})

test('asks the include/exclude inventory parts question only for purchase and sales parts', () => {
  assert.equal(supportsInventoryPartExclusion('PURCHASE'), true)
  assert.equal(supportsInventoryPartExclusion('SALES'), true)
  assert.equal(supportsInventoryPartExclusion('INVENTORY'), false)
})

test('labels the sales base key as Sales Part No only for sales parts', () => {
  const partNo = { field: 'PART_NO', display: 'Part No' }
  assert.equal(fieldDisplayForPartType(partNo, 'SALES'), 'Sales Part No')
  assert.equal(fieldDisplayForPartType(partNo, 'PURCHASE'), 'Part No')
})

test('hides internal codes for the sales part no and inventory filter fields only', () => {
  assert.equal(shouldShowFieldCode({ field: 'INVENTORY_PART_NO' }), false)
  assert.equal(shouldShowFieldCode({ field: 'INVENTORY_PART_FLAG' }), false)
  assert.equal(shouldShowFieldCode({ field: 'SALES_PART_TYPE' }), false)
  assert.equal(shouldShowFieldCode({ field: 'SALES_UOM' }), true)
})

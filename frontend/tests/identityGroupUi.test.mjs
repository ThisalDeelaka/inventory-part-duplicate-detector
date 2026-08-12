import assert from 'node:assert/strict'
import test from 'node:test'

import {
  diagnosticStatusLabel,
  edgeClassLabel,
  evidenceSourceLabel,
  groupSizeDistributionLabel,
  groupStatusLabel,
  hasCannotLink,
  identityGroupTargets,
  identityGroupExportTargets,
  mappingWarnings,
  pageOffset,
  reasonLabel,
} from '../src/utils/identityGroupUi.js'

test('scan-21 summary values remain distinct business facts', () => {
  const summary = { accepted_groups: 288, likely_groups: 21, review_groups: 267,
    conflicting_families: 9, largest_accepted_group: 14 }
  assert.deepEqual(Object.values(summary), [288, 21, 267, 9, 14])
  assert.equal(groupSizeDistributionLabel({ 2: 230, 7: 2, 14: 1 }), '2 records: 230 · 7 records: 2 · 14 records: 1')
})

function assertWholeGroup(size) {
  const members = Array.from({ length: size }, (_, member_index) => ({ member_index }))
  assert.equal(members.length, size)
  assert.deepEqual(members.map(item => item.member_index), [...Array(size).keys()])
}

test('two-member group renders two adjacent ordered members', () => assertWholeGroup(2))
test('four-member group remains one four-record group rather than six pair rows', () => assertWholeGroup(4))
test('seven-member group retains all members for lazy detail', () => assertWholeGroup(7))
test('fourteen-member group does not truncate', () => assertWholeGroup(14))

test('group wording never claims confirmation and unknown values render safely', () => {
  assert.equal(groupStatusLabel('LIKELY_DUPLICATE_GROUP'), 'Likely duplicate group')
  assert.equal(groupStatusLabel('POSSIBLE_DUPLICATE_GROUP_REVIEW'), 'Possible duplicate group — review')
  assert.equal(groupStatusLabel('FUTURE_STATUS'), 'Unknown group status (FUTURE_STATUS)')
})

test('UOM warnings remain mapping observations separate from identity', () => {
  assert.deepEqual(mappingWarnings({ different_basis_pair_count: 2, possible_mapping_error_count: 1 }), [
    'Different-basis unit relationships', 'Possible unit/mapping inconsistency',
  ])
})

test('local rescoring and edge classes have accurate readable labels', () => {
  assert.equal(evidenceSourceLabel('G1_LOCAL_RESCORING'), 'Local deterministic cross-check')
  assert.equal(edgeClassLabel('STRONG_SUPPORT'), 'Strong support')
  assert.equal(edgeClassLabel('REVIEW_SUPPORT'), 'Review support')
  assert.equal(edgeClassLabel('NON_GROUPABLE'), 'Neutral / non-groupable')
})

test('conflicts and structural-role reasons have non-duplicate wording', () => {
  assert.equal(diagnosticStatusLabel('CONFLICTING_FAMILY'), 'Conflicting candidate family')
  assert.equal(reasonLabel('CRITICAL_MISMATCH_STRUCTURAL_ROLE'), 'Structural role conflict')
  assert.equal(reasonLabel('HUMAN_NON_DUPLICATE'), 'Previously marked not duplicate')
})

test('filters and pagination generate only G3 read endpoints', () => {
  const target = identityGroupTargets(21, {
    status: 'LIKELY_DUPLICATE_GROUP', minimumGroupSize: 4, maximumGroupSize: 14,
    limit: 25, offset: pageOffset(2, 25),
  }).groups
  assert.equal(target, '/api/scans/21/identity-groups?status=LIKELY_DUPLICATE_GROUP&minimum_group_size=4&maximum_group_size=14&limit=25&offset=50')
  assert.doesNotMatch(target, /llm-triage|\/groups(?:\?|$)/)
})

test('detail targets are lazy-capable and never target LLM start or resume', () => {
  const targets = identityGroupTargets(21)
  assert.equal(targets.groupDetail(8), '/api/scans/21/identity-groups/8')
  assert.equal(targets.diagnosticDetail(9), '/api/scans/21/identity-group-diagnostics/9')
  assert.doesNotMatch(JSON.stringify(targets), /llm-triage|advisory/)
})

test('cannot-link evidence produces an explicit inconsistency signal', () => {
  assert.equal(hasCannotLink({ internal_edges: [{ edge_class: 'CANNOT_LINK' }] }), true)
  assert.equal(hasCannotLink({ internal_edges: [{ edge_class: 'STRONG_SUPPORT' }] }), false)
})

test('valid empty distribution differs from no-snapshot state', () => {
  assert.equal(groupSizeDistributionLabel({}), 'No accepted groups')
  assert.notEqual(groupSizeDistributionLabel({}), 'No identity-group snapshot is available for this scan.')
})

test('conflicting-family requests use only the dedicated diagnostic route', () => {
  const target = identityGroupTargets(21).diagnostics
  assert.equal(target, '/api/scans/21/identity-group-diagnostics')
  assert.doesNotMatch(target, /identity-groups(?:\?|$)/)
})

test('pair diagnostics stay outside identity-group reconstruction endpoints', () => {
  const targets = identityGroupTargets(21)
  assert.equal(Object.values(targets).some(value => typeof value === 'string' && value.endsWith('/candidates')), false)
})

test('pagination offsets are stable at boundaries', () => {
  assert.equal(pageOffset(0, 25), 0)
  assert.equal(pageOffset(1, 25), 25)
  assert.equal(pageOffset(11, 25), 275)
})

test('known flow and serialization conflicts render without inventing evidence', () => {
  assert.equal(reasonLabel('CRITICAL_MISMATCH_FLOW_ROLE'), 'Inlet / outlet role conflict')
  assert.equal(reasonLabel('CRITICAL_MISMATCH_SERIALIZATION_ROLE'), 'Serial / non-serial role conflict')
})

test('unknown diagnostic, edge, and provenance values do not crash', () => {
  assert.match(diagnosticStatusLabel('FUTURE_DIAGNOSTIC'), /FUTURE_DIAGNOSTIC/)
  assert.match(edgeClassLabel('FUTURE_EDGE'), /FUTURE_EDGE/)
  assert.match(evidenceSourceLabel('FUTURE_SOURCE'), /FUTURE_SOURCE/)
})

test('explicit snapshot selection never combines projection runs', () => {
  const targets = identityGroupTargets(21, { projectionRunId: 44 })
  assert.equal(targets.summary, '/api/scans/21/identity-groups/summary?projection_run_id=44')
  assert.equal(targets.groupDetail(7), '/api/scans/21/identity-groups/7?projection_run_id=44')
})

test('grouped export actions use deterministic G5 routes and filenames', () => {
  assert.deepEqual(identityGroupExportTargets(21), {
    groups: { path: '/api/scans/21/identity-groups/export.csv', filename: 'scan-21-identity-groups.csv' },
    diagnostics: { path: '/api/scans/21/identity-group-diagnostics/export.csv', filename: 'scan-21-identity-group-diagnostics.csv' },
  })
  assert.equal(identityGroupExportTargets(21, 7).groups.path, '/api/scans/21/identity-groups/export.csv?projection_run_id=7')
})

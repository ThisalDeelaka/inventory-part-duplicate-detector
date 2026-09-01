import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  exportFailureFeedback,
  exportSuccessFeedback,
  reviewedExportGuidance,
  summarizeReviewedExportAvailability,
} from '../src/utils/identityExportUi.js'
import { identityReadExportTargets } from '../src/utils/identityGroupUi.js'

const panel = readFileSync(new URL('../src/components/ExportAuthorityPanel.jsx', import.meta.url), 'utf8')
const page = readFileSync(new URL('../src/pages/ScanResults.jsx', import.meta.url), 'utf8')
const state = decision => ({ review_state: decision ? { reviewed: true, current_decision_type: decision } : { reviewed: false } })

test('E1 zero reviews disables meaningful reviewed output with truthful guidance', () => {
  const result = summarizeReviewedExportAvailability([state(), state()], 2)
  assert.equal(result.has_confirmed_sets, false)
  assert.match(reviewedExportGuidance(result), /No confirmed duplicate sets are available yet/)
})

test('E2 only Reject decisions create no reviewed duplicate set', () => {
  const result = summarizeReviewedExportAvailability([state('KEEP_ALL_SEPARATE')])
  assert.equal(result.has_confirmed_sets, false)
  assert.match(reviewedExportGuidance(result), /Reject or Defer decisions create no reviewed duplicate set/)
})

test('E3 only Defer decisions create no reviewed duplicate set', () => {
  assert.equal(summarizeReviewedExportAvailability([state('UNSURE')]).affirmative_groups, 0)
})

test('E4 one current Confirm enables reviewed export authority', () => {
  assert.equal(summarizeReviewedExportAvailability([state('CONFIRM_ALL_AS_ONE')]).has_confirmed_sets, true)
})

test('E5 multiple current Confirm variants remain affirmative', () => {
  const result = summarizeReviewedExportAvailability([
    state('CONFIRM_ALL_AS_ONE'), state('CONFIRM_SELECTED'), state('SPLIT_PARTITIONS'),
  ])
  assert.equal(result.affirmative_groups, 3)
})

test('E6 Confirm superseded by Reject is excluded because only current chain-head state is read', () => {
  assert.equal(summarizeReviewedExportAvailability([state('KEEP_ALL_SEPARATE')]).has_confirmed_sets, false)
})

test('E7 Confirm superseded by Defer is excluded because only current chain-head state is read', () => {
  assert.equal(summarizeReviewedExportAvailability([state('UNSURE')]).has_confirmed_sets, false)
})

test('E8 Reject superseded by Confirm is included through the current chain head', () => {
  assert.equal(summarizeReviewedExportAvailability([state('CONFIRM_SELECTED')]).has_confirmed_sets, true)
})

test('E9 partially reviewed scans state the export is partial', () => {
  const result = summarizeReviewedExportAvailability([state('CONFIRM_ALL_AS_ONE'), state()], 2)
  assert.equal(result.is_partial_review, true)
  assert.match(reviewedExportGuidance(result), /Some system groups remain unreviewed/)
})

test('E10 unreviewed system groups remain suggestions and are excluded from reviewed authority', () => {
  const result = summarizeReviewedExportAvailability([state(), state('CONFIRM_ALL_AS_ONE')], 2)
  assert.equal(result.affirmative_groups, 1)
  assert.match(panel, /system-generated groups for analysis and review/)
})

test('E11 System CSV route, filename, and accessible label remain explicit', () => {
  const target = identityReadExportTargets(9).systemGroups
  assert.deepEqual(target, { path: '/api/scans/9/identity-read/system-groups/export.csv', filename: 'scan-9-system-group-suggestions.csv' })
  assert.match(panel, /Export system suggestions as CSV/)
})

test('E12 System XLSX route, filename, and accessible label remain explicit', () => {
  const target = identityReadExportTargets(9).systemGroupsExcel
  assert.deepEqual(target, { path: '/api/scans/9/identity-read/system-groups/export.xlsx', filename: 'scan-9-system-group-suggestions.xlsx' })
  assert.match(panel, /Export system suggestions as Excel/)
})

test('E13 Reviewed CSV route and feedback identify current human authority only', () => {
  const target = identityReadExportTargets(9).reviewedIdentities
  assert.deepEqual(target, { path: '/api/scans/9/identity-read/reviewed-identities/export.csv', filename: 'scan-9-reviewed-identity-sets.csv' })
  assert.match(exportSuccessFeedback('reviewed'), /current human-confirmed identity sets only/)
  assert.match(page, /api\.download\(target\.path, target\.filename\)/)
})

test('E14 export failures distinguish 404, 409, 422, and network errors accessibly', () => {
  assert.match(exportFailureFeedback('reviewed', 404), /not available/)
  assert.match(exportFailureFeedback('reviewed', 409), /not ready/)
  assert.match(exportFailureFeedback('reviewed', 422), /selected authoritative result/)
  assert.match(exportFailureFeedback('reviewed'), /Check your connection/)
  assert.match(panel, /aria-busy/)
  assert.match(panel, /'alert' : 'status'/)
})

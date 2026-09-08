import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  identityReadErrorState,
  identityReadExportTargets,
  identityReadTargets,
  validationCoverageLabel,
  validationModeLabel,
} from '../src/utils/identityGroupUi.js'
import {
  buildVersionedGroupReviewPayload,
  versionedIdentityGroupReviewTargets,
} from '../src/utils/identityGroupReviewUi.js'

const page = readFileSync(new URL('../src/pages/ScanResults.jsx', import.meta.url), 'utf8')
const panel = readFileSync(new URL('../src/components/GroupReviewPanel.jsx', import.meta.url), 'utf8')
const exportPanel = readFileSync(new URL('../src/components/ExportAuthorityPanel.jsx', import.meta.url), 'utf8')
const client = readFileSync(new URL('../src/api/client.js', import.meta.url), 'utf8')
const opaqueKey = 'igk1.eyJwcm9qZWN0aW9uX2NvbnRyYWN0IjoiRzJfVjIifQ'
const members = [1, 2, 3].map(index => ({
  stable_record_reference: String(index).repeat(64), part_no: `P${index}`,
  description: `Item ${index}`,
}))

test('F1 historical v1 uses the authority-selected summary/list/detail endpoints', () => {
  const targets = identityReadTargets(21)
  assert.equal(targets.summary, '/api/scans/21/identity-read/summary')
  assert.equal(targets.groups, '/api/scans/21/identity-read/groups')
  assert.equal(targets.groupDetail(opaqueKey), `/api/scans/21/identity-read/groups/${opaqueKey}`)
})

test('F2 legacy-primary v1 is rendered through truthful legacy validation semantics', () => {
  assert.equal(validationModeLabel('LEGACY_COMPLETE_PAIRWISE'), 'Legacy complete pairwise validation')
})

test('F3 group-first v2 uses the same backend-selected summary/list/detail client', () => {
  assert.match(client, /getIdentityReadSummary/)
  assert.match(client, /getIdentityReadGroups/)
  assert.match(client, /getIdentityReadGroupDetail/)
})

test('F4 no legacy identity-group route can become the product fallback', () => {
  assert.doesNotMatch(page, /getIdentityGroupSummary|getIdentityGroups|getIdentityGroupDetail/)
  assert.match(page, /getIdentityReadSummary/)
})

test('F5 progressive coverage is exact and names missing non-required work', () => {
  assert.equal(validationCoverageLabel({
    evaluated_internal_pair_count: 2,
    possible_internal_pair_count: 3,
    missing_nonrequired_pair_count: 1,
  }), '2 of 3 relationships evaluated · 1 missing non-required')
  assert.match(page, /Missing non-required relationships are not synthesized/)
})

test('F6 conflicts and deferred outcomes have separate product sections', () => {
  assert.match(page, /Identity conflicts/)
  assert.match(page, /Deferred \/ unresolved work/)
})

test('F7 unassigned is never described as confirmed unique', () => {
  assert.match(page, /They are not confirmed unique/)
  assert.doesNotMatch(page, /Unique records|Confirmed unique records/)
})

test('F8 409 is a distinct not-ready state and has no fallback instruction', () => {
  assert.deepEqual(identityReadErrorState(409, 'missing'), {
    kind: 'not-ready', title: 'Identity result is not ready', message: 'missing',
  })
})

test('F9 review target uses the opaque versioned group key', () => {
  assert.equal(
    versionedIdentityGroupReviewTargets(21, opaqueKey).create,
    `/api/scans/21/identity-read/groups/${opaqueKey}/reviews`,
  )
  assert.match(panel, /detail\.versioned_group_key/)
  assert.doesNotMatch(panel, /detail\.group_snapshot_id/)
})

test('F10 review state is loaded only from the exact versioned target chain', () => {
  assert.match(panel, /getVersionedGroupReviewHistory/)
  assert.doesNotMatch(panel, /getIdentityGroupReviewHistory/)
})

test('F11 complete-pairwise advisory eligibility is backend-owned', () => {
  assert.match(page, /eligibility\.eligible/)
  assert.match(page, /Eligible for a projection-scoped group advisory/)
})

test('F12 progressive advisory ineligibility is shown without execution', () => {
  assert.match(page, /progressive validation is not supported for advisory yet/)
  assert.doesNotMatch(page, /requestVersionedGroupAdvisory|startGroupAdvisory/)
})

test('F13 likely advisory ineligibility remains the backend reason', () => {
  assert.match(page, /eligibility\.details/)
  assert.doesNotMatch(page, /group_status\s*===\s*['"]LIKELY.*eligible/)
})

test('F14 pair diagnostics are demoted under Advanced and have no review controls', () => {
  assert.match(page, /Advanced legacy pair diagnostics/)
  assert.match(page, /It is not the business result, review unit, or export unit/)
  assert.doesNotMatch(page, /postJson\(`\/api\/candidates|CandidateLlmTools/)
  assert.match(page, /not generated because they are not applicable to this group-first scan/)
  assert.match(client, /error\.category = category/)
})

test('F15 product export controls use only canonical authority-selected endpoints', () => {
  assert.deepEqual(identityReadExportTargets(21), {
    systemGroups: { path: '/api/scans/21/identity-read/system-groups/export.csv', filename: 'scan-21-system-group-suggestions.csv' },
    systemGroupsExcel: { path: '/api/scans/21/identity-read/system-groups/export.xlsx', filename: 'scan-21-system-group-suggestions.xlsx' },
    reviewedIdentities: { path: '/api/scans/21/identity-read/reviewed-identities/export.csv', filename: 'scan-21-reviewed-identity-sets.csv' },
    conflicts: { path: '/api/scans/21/identity-read/conflicts/export.csv', filename: 'scan-21-identity-conflicts.csv' },
    deferred: { path: '/api/scans/21/identity-read/deferred/export.csv', filename: 'scan-21-deferred-identity-work.csv' },
  })
  assert.match(exportPanel, /Export system suggestions as CSV/)
  assert.match(exportPanel, /Export system suggestions as Excel/)
  assert.match(exportPanel, /Export confirmed duplicate sets \(CSV\)/)
})

test('F16 valid zero-group rendering is distinct from not-ready rendering', () => {
  assert.match(page, /ready authoritative snapshot contains zero potential duplicate groups/)
  assert.match(page, /identity-\$\{summaryError\.kind\}/)
})

test('F17 opaque igk1 keys are encoded and never parsed for business meaning', () => {
  const target = identityReadTargets(21).groupDetail(`${opaqueKey}/still-opaque`)
  assert.match(target, /%2Fstill-opaque$/)
  assert.doesNotMatch(page, /atob|JSON\.parse.*versioned_group_key|split\(['"]\.['"]\)/)
})

test('F18 frontend has no current-process orchestration authority logic', () => {
  const all = `${page}\n${client}`
  assert.doesNotMatch(all, /IDENTITY_ORCHESTRATION_MODE|group_first_primary|legacy_primary|import\.meta\.env.*ORCHESTRATION/)
  const newScan = readFileSync(new URL('../src/pages/NewScan.jsx', import.meta.url), 'utf8')
  assert.match(newScan, /f\.append\('product_authority', 'current_product'\)/)
})

test('versioned review payload omits legacy projection and numeric identities', () => {
  const payload = buildVersionedGroupReviewPayload({
    detail: { versioned_group_key: opaqueKey, members },
    decisionType: 'CONFIRM_ALL_AS_ONE', reviewer: 'reviewer',
  })
  assert.equal('projection_run_id' in payload, false)
  assert.equal('group_hypothesis_key' in payload, false)
  assert.equal('group_snapshot_id' in payload, false)
})

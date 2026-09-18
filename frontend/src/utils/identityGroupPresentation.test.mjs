import assert from 'node:assert/strict'
import test from 'node:test'

import {
  groupAuthorityLabel,
  groupEvidenceTierLabel,
  groupReviewAuthorityLabel,
  groupStatusLabel,
} from './identityGroupUi.js'
import { summarizeReviewedExportAvailability } from './identityExportUi.js'
import { groupReviewLabel } from './identityGroupReviewUi.js'

const LIKELY = 'LIKELY_DUPLICATE_GROUP'
const REVIEW = 'POSSIBLE_DUPLICATE_GROUP_REVIEW'

test('both unreviewed internal statuses map to the safe candidate label', () => {
  assert.equal(groupStatusLabel(LIKELY), 'Potential Same-Identity Group')
  assert.equal(groupStatusLabel(REVIEW), 'Potential Same-Identity Group')
  assert.equal(groupReviewAuthorityLabel({ reviewed: false }), 'Requires Human Review')
  assert.equal(groupReviewLabel({ reviewed: false }), 'Requires Human Review')
  assert.ok(!groupAuthorityLabel(LIKELY, { reviewed: false }).includes('Confirmed'))
})

test('system evidence tiers do not claim probability or confidence', () => {
  assert.equal(groupEvidenceTierLabel(LIKELY), 'Stronger deterministic evidence')
  assert.equal(groupEvidenceTierLabel(REVIEW), 'Needs additional review')
  for (const status of [LIKELY, REVIEW]) {
    assert.doesNotMatch(groupEvidenceTierLabel(status), /confidence|probability|accuracy|%/i)
  }
})

test('human confirmation visually overrides the system suggestion', () => {
  for (const decision of ['CONFIRM_ALL_AS_ONE', 'CONFIRM_SELECTED']) {
    const state = { reviewed: true, current_decision_type: decision }
    assert.equal(groupAuthorityLabel(LIKELY, state), 'Human Confirmed Same-Identity Group')
    assert.equal(groupReviewAuthorityLabel(state), 'Human Confirmed Same-Identity Group')
  }
})

test('human rejection and defer states visually override the system suggestion', () => {
  const rejected = { reviewed: true, current_decision_type: 'KEEP_ALL_SEPARATE' }
  const deferred = { reviewed: true, current_decision_type: 'UNSURE' }
  assert.equal(groupAuthorityLabel(LIKELY, rejected), 'Human Rejected Candidate')
  assert.equal(groupReviewLabel(rejected), 'Human Rejected Candidate')
  assert.equal(groupAuthorityLabel(REVIEW, deferred), 'Review Deferred')
  assert.equal(groupReviewLabel(deferred), 'Review Deferred')
})

test('summary counts separate system suggestions from human authority', () => {
  const state = summarizeReviewedExportAvailability([
    { review_state: { reviewed: true, current_decision_type: 'CONFIRM_ALL_AS_ONE' } },
    { review_state: { reviewed: true, current_decision_type: 'KEEP_ALL_SEPARATE' } },
    { review_state: { reviewed: true, current_decision_type: 'UNSURE' } },
    { review_state: { reviewed: false } },
  ])
  assert.equal(state.total_groups, 4)
  assert.equal(state.affirmative_groups, 1)
  assert.equal(state.rejected_groups, 1)
  assert.equal(state.deferred_groups, 1)
  assert.equal(state.unreviewed_groups, 1)
})

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  buildVersionedGroupReviewPayload,
  reviewDecisionOutcome,
  reviewDecisionPresentation,
  reviewSaveErrorState,
} from '../src/utils/identityGroupReviewUi.js'

const panel = readFileSync(new URL('../src/components/GroupReviewPanel.jsx', import.meta.url), 'utf8')
const page = readFileSync(new URL('../src/pages/ScanResults.jsx', import.meta.url), 'utf8')
const utility = readFileSync(new URL('../src/utils/identityGroupReviewUi.js', import.meta.url), 'utf8')

function review(decision_type, partitions = []) {
  return { decision_type, partitions, review_event_id: 9, is_current: true }
}

function detail(size) {
  return {
    versioned_group_key: 'igk1:test',
    members: Array.from({ length: size }, (_, index) => ({
      stable_record_reference: String(index).padStart(64, '0'),
    })),
  }
}

test('R1 two-member Confirm is plain language and maps to CONFIRM_ALL_AS_ONE', () => {
  assert.equal(reviewDecisionPresentation('CONFIRM_ALL_AS_ONE', 2).label, 'Confirm as same item')
  assert.equal(buildVersionedGroupReviewPayload({ detail: detail(2), decisionType: 'CONFIRM_ALL_AS_ONE', reviewer: 'r' }).decision_type, 'CONFIRM_ALL_AS_ONE')
})

test('R2 two-member Reject is distinct and maps to KEEP_ALL_SEPARATE', () => {
  const value = reviewDecisionPresentation('KEEP_ALL_SEPARATE', 2)
  assert.equal(value.label, 'Reject duplicate hypothesis')
  assert.match(value.secondary, /Keep these records separate/)
})

test('R3 two-member Defer is unresolved and maps to UNSURE', () => {
  const value = reviewDecisionPresentation('UNSURE', 2)
  assert.equal(value.label, 'Defer decision')
  assert.match(value.consequence, /unresolved for later review/)
})

test('R4 three-plus-member Confirm says all and preserves full-group action', () => {
  assert.equal(reviewDecisionPresentation('CONFIRM_ALL_AS_ONE', 4).label, 'Confirm all as same item')
  assert.match(panel, /these \{memberCount\} records represent the same underlying inventory item/)
})

test('R5 Confirm selected names its subset result and leaves others unresolved', () => {
  const outcome = reviewDecisionOutcome(review('CONFIRM_SELECTED', [['a', 'b', 'c']]), 5)
  assert.equal(outcome.title, 'Selected records confirmed as one identity')
  assert.match(outcome.effect, /3 selected records; 2 records remain unresolved/)
})

test('R6 Split partitions explains exact disjoint identity sets', () => {
  const outcome = reviewDecisionOutcome(review('SPLIT_PARTITIONS', [['a', 'b'], ['c']]), 3)
  assert.match(outcome.effect, /2 reviewed identity sets/)
  assert.match(outcome.effect, /exactly one set/)
})

test('R7 saved Confirm shows current authoritative result', () => {
  const outcome = reviewDecisionOutcome(review('CONFIRM_ALL_AS_ONE', [['a', 'b']]), 2)
  assert.equal(outcome.title, 'Confirmed as one identity')
  assert.match(panel, /Current decision controls Reviewed Identity Export|current decision controls Reviewed Identity Export/)
})

test('R8 saved Reject says no reviewed duplicate set was created', () => {
  const outcome = reviewDecisionOutcome(review('KEEP_ALL_SEPARATE'), 2)
  assert.equal(outcome.title, 'Rejected — keep separate')
  assert.match(outcome.effect, /No reviewed duplicate set was created/)
})

test('R9 saved Defer remains unresolved and is not Reject', () => {
  const outcome = reviewDecisionOutcome(review('UNSURE'), 2)
  assert.equal(outcome.title, 'Deferred')
  assert.match(outcome.effect, /remains unresolved/)
  assert.doesNotMatch(outcome.title, /Reject/)
})

test('R10 superseded affirmative review is marked previous and non-authoritative', () => {
  assert.match(panel, /Previous decision/)
  assert.match(panel, /no longer operationally authoritative/)
})

test('R11 superseded rejected or deferred review remains in decision history', () => {
  assert.match(panel, /Decision history/)
  assert.match(panel, /previous decision remains in review history/i)
})

test('R12 concurrency conflict reloads latest state without auto-resubmit', () => {
  assert.deepEqual(reviewSaveErrorState(409), {
    reload: true,
    resubmit: false,
    message: 'Decision not saved because another review became current. The latest decision was reloaded; check it before trying again.',
  })
  assert.match(panel, /await loadHistory\(\)/)
})

test('R13 validation and network failures never claim success', () => {
  assert.match(reviewSaveErrorState(422).message, /^Decision not saved/)
  assert.match(reviewSaveErrorState(undefined).message, /^Decision not saved/)
  assert.doesNotMatch(reviewSaveErrorState(422).message, /saved successfully/i)
})

test('R14 Change decision preserves history and PRM-1 separation', () => {
  assert.match(panel, /Change decision/)
  assert.match(panel, /Saving creates a new current decision/)
  assert.match(page, /SystemExplanation[\s\S]*GroupReviewPanel/)
  assert.doesNotMatch(panel + utility, /â|Ã|Â/)
})

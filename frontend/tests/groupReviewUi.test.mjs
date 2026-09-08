import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  buildGroupReviewPayload,
  canonicalSplitPartitions,
  groupReviewLabel,
  identityGroupReviewTargets,
  relationshipCounts,
  reviewPreview,
  reviewSaveErrorState,
  staleReviewHandling,
} from '../src/utils/identityGroupReviewUi.js'


function detail(size) {
  return {
    group_snapshot_id: 8,
    hypothesis_key: 'a'.repeat(64),
    group_status: 'POSSIBLE_DUPLICATE_GROUP_REVIEW',
    projection: { projection_run_id: 44 },
    members: Array.from({ length: size }, (_, index) => ({
      record_ref_key: `ref-${String(index).padStart(2, '0')}`,
      part_no: `P-${index}`, description: `Part ${index}`, contract: 'S1', uom: 'PCS',
    })),
  }
}


function base(size, decisionType, extra = {}) {
  return { detail: detail(size), decisionType, reviewer: ' reviewer ', ...extra }
}


test('not-reviewed and every reviewed indicator are separate from system status', () => {
  assert.equal(groupReviewLabel({ reviewed: false }), 'Not reviewed')
  for (const decision of ['CONFIRM_ALL_AS_ONE', 'CONFIRM_SELECTED', 'SPLIT_PARTITIONS', 'KEEP_ALL_SEPARATE', 'UNSURE']) {
    assert.match(groupReviewLabel({ reviewed: true, current_decision_type: decision }), /^Reviewed/)
  }
})

test('typed review targets are group scoped and provider free', () => {
  assert.deepEqual(identityGroupReviewTargets(21, 8), {
    history: '/api/scans/21/identity-groups/8/reviews',
    current: '/api/scans/21/identity-groups/8/reviews/current',
    create: '/api/scans/21/identity-groups/8/reviews',
  })
  assert.doesNotMatch(JSON.stringify(identityGroupReviewTargets(21, 8)), /llm|triage|advisory/i)
})

test('confirm-all size four creates exact immutable-context payload and preview', () => {
  const input = base(4, 'CONFIRM_ALL_AS_ONE')
  const payload = buildGroupReviewPayload(input)
  assert.equal(payload.projection_run_id, 44)
  assert.equal(payload.group_hypothesis_key, 'a'.repeat(64))
  assert.deepEqual(payload.selected_record_ref_keys, [])
  assert.deepEqual(reviewPreview(input), { member_count: 4, partition_sizes: [], must_link_count: 6, cannot_link_count: 0 })
})

test('confirm-selected four of five submits only four and leaves fifth unresolved', () => {
  const group = detail(5)
  const selected = group.members.slice(0, 4).map(member => member.record_ref_key)
  const payload = buildGroupReviewPayload({ detail: group, decisionType: 'CONFIRM_SELECTED', reviewer: 'r', selectedRecordRefKeys: selected })
  assert.deepEqual(payload.selected_record_ref_keys, selected)
  assert.equal(payload.selected_record_ref_keys.includes(group.members[4].record_ref_key), false)
  assert.deepEqual(relationshipCounts('CONFIRM_SELECTED', 5, [selected]), { must_link_count: 6, cannot_link_count: 0 })
})

test('confirm-selected fewer than two members is blocked', () => {
  assert.throws(() => buildGroupReviewPayload(base(5, 'CONFIRM_SELECTED', { selectedRecordRefKeys: ['ref-00'] })), /at least two/)
})

test('split four plus one assigns every member once and previews 6/4', () => {
  const assignments = { 'ref-00': 0, 'ref-01': 0, 'ref-02': 0, 'ref-03': 0, 'ref-04': 1 }
  const input = base(5, 'SPLIT_PARTITIONS', { assignments, setCount: 2 })
  const payload = buildGroupReviewPayload(input)
  assert.deepEqual(payload.partitions.map(block => block.length), [4, 1])
  assert.deepEqual(reviewPreview(input), { member_count: 5, partition_sizes: [4, 1], must_link_count: 6, cannot_link_count: 4 })
})

test('split two plus two plus one produces stable three-set payload', () => {
  const assignments = { 'ref-00': 2, 'ref-01': 2, 'ref-02': 0, 'ref-03': 0, 'ref-04': 1 }
  const partitions = canonicalSplitPartitions(detail(5).members, assignments, 3)
  assert.deepEqual(partitions, [['ref-00', 'ref-01'], ['ref-02', 'ref-03'], ['ref-04']])
  assert.deepEqual(relationshipCounts('SPLIT_PARTITIONS', 5, partitions), { must_link_count: 2, cannot_link_count: 8 })
})

test('invalid split missing assignment blocks submission', () => {
  assert.throws(() => canonicalSplitPartitions(detail(5).members, { 'ref-00': 0 }, 2), /Every member/)
})

test('invalid split with an empty set blocks submission', () => {
  const assignments = Object.fromEntries(detail(5).members.map(member => [member.record_ref_key, 0]))
  assert.throws(() => canonicalSplitPartitions(detail(5).members, assignments, 2), /cannot be empty/)
})

test('duplicate immutable members cannot form a split payload', () => {
  const group = detail(2); group.members[1].record_ref_key = group.members[0].record_ref_key
  assert.throws(() => canonicalSplitPartitions(group.members, { 'ref-00': 0 }, 2), /unique/)
})

test('keep-all-separate payload has no client constraints and previews six cannot links', () => {
  const input = base(4, 'KEEP_ALL_SEPARATE')
  const payload = buildGroupReviewPayload(input)
  assert.deepEqual(payload.partitions, [])
  assert.deepEqual(reviewPreview(input), { member_count: 4, partition_sizes: [], must_link_count: 0, cannot_link_count: 6 })
})

test('unsure submits no selections or partitions and derives no links', () => {
  const input = base(7, 'UNSURE')
  const payload = buildGroupReviewPayload(input)
  assert.deepEqual([payload.selected_record_ref_keys, payload.partitions], [[], []])
  assert.deepEqual(relationshipCounts('UNSURE', 7), { must_link_count: 0, cannot_link_count: 0 })
})

test('edit review uses the exact current event as supersession token', () => {
  const payload = buildGroupReviewPayload(base(2, 'UNSURE', { currentReviewEventId: 91 }))
  assert.equal(payload.supersedes_review_event_id, 91)
})

test('409 reloads and never automatically resubmits', () => {
  assert.deepEqual(staleReviewHandling(409), {
    reload: true, resubmit: false,
    message: 'Decision not saved because another review became current. The latest decision was reloaded; check it before trying again.',
  })
  assert.equal(reviewSaveErrorState(409).resubmit, false)
})

test('review payload cannot mutate system status, members, exports, or projection', () => {
  const payload = buildGroupReviewPayload(base(2, 'CONFIRM_ALL_AS_ONE'))
  assert.equal('group_status' in payload, false)
  assert.equal('members' in payload, false)
  assert.equal('run_projection' in payload, false)
  assert.equal('export' in payload, false)
})

test('2, 7, and 14 members remain whole-group review inputs without pair expansion', () => {
  for (const size of [2, 7, 14]) {
    const group = detail(size)
    assert.equal(group.members.length, size)
    assert.equal(buildGroupReviewPayload({ detail: group, decisionType: 'CONFIRM_ALL_AS_ONE', reviewer: 'r' }).selected_record_ref_keys.length, 0)
  }
})

test('review UI exposes keyboard-native labeled controls and append-only history', () => {
  const source = readFileSync(new URL('../src/components/GroupReviewPanel.jsx', import.meta.url), 'utf8')
  assert.match(source, /<fieldset>/)
  assert.match(source, /type="checkbox"/)
  assert.match(source, /aria-label=/)
  assert.match(source, /Current decision.*Previous decision/s)
  assert.match(source, /supersedes_review_event_id|currentReviewEventId/)
})

test('diagnostic cards and pair diagnostics contain no group-review workflow', () => {
  const source = readFileSync(new URL('../src/pages/ScanResults.jsx', import.meta.url), 'utf8')
  const diagnostic = source.slice(source.indexOf('function DiagnosticView'), source.indexOf('export default function ScanResults'))
  const pair = source.slice(source.indexOf('function PairTable'), source.indexOf('function TriagePanel'))
  assert.doesNotMatch(diagnostic, /GroupReviewPanel|Review group|Edit review/)
  assert.doesNotMatch(pair, /GroupReviewPanel|identity-groups.*reviews/)
})

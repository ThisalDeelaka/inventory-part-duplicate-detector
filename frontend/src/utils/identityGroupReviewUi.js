export const GROUP_REVIEW_DECISIONS = [
  ['CONFIRM_ALL_AS_ONE', 'Confirm all as one item'],
  ['CONFIRM_SELECTED', 'Confirm selected as one item'],
  ['SPLIT_PARTITIONS', 'Split into identity sets'],
  ['KEEP_ALL_SEPARATE', 'Keep all separate'],
  ['UNSURE', 'Unsure â€” keep for later review'],
]

const REVIEW_LABELS = {
  CONFIRM_ALL_AS_ONE: 'Reviewed â€” all confirmed as one',
  CONFIRM_SELECTED: 'Reviewed â€” selected members confirmed',
  SPLIT_PARTITIONS: 'Reviewed â€” split',
  KEEP_ALL_SEPARATE: 'Reviewed â€” kept separate',
  UNSURE: 'Reviewed â€” unsure',
}

export function groupReviewLabel(state) {
  if (!state?.reviewed) return 'Not reviewed'
  return REVIEW_LABELS[state.current_decision_type]
    || `Reviewed â€” unknown decision (${String(state.current_decision_type || 'unspecified')})`
}

function positive(value, name) {
  const number = Number(value)
  if (!Number.isInteger(number) || number <= 0) throw new Error(`${name} must be a positive integer`)
  return number
}

export function identityGroupReviewTargets(scanId, groupSnapshotId) {
  const scan = positive(scanId, 'scanId')
  const group = positive(groupSnapshotId, 'groupSnapshotId')
  const base = `/api/scans/${scan}/identity-groups/${group}/reviews`
  return { history: base, current: `${base}/current`, create: base }
}

export function relationshipCounts(decisionType, memberCount, partitions = []) {
  const n = Number(memberCount)
  const choose2 = value => value * (value - 1) / 2
  if (decisionType === 'CONFIRM_ALL_AS_ONE') return { must_link_count: choose2(n), cannot_link_count: 0 }
  if (decisionType === 'CONFIRM_SELECTED') {
    const selected = partitions[0]?.length || 0
    return { must_link_count: choose2(selected), cannot_link_count: 0 }
  }
  if (decisionType === 'KEEP_ALL_SEPARATE') return { must_link_count: 0, cannot_link_count: choose2(n) }
  if (decisionType === 'UNSURE') return { must_link_count: 0, cannot_link_count: 0 }
  const sizes = partitions.map(block => block.length)
  const within = sizes.reduce((total, size) => total + choose2(size), 0)
  return { must_link_count: within, cannot_link_count: choose2(n) - within }
}

export function canonicalSplitPartitions(members, assignments, setCount) {
  const refs = members.map(member => member.record_ref_key)
  if (new Set(refs).size !== refs.length) throw new Error('Group members must be unique')
  const count = Number(setCount)
  if (!Number.isInteger(count) || count < 2 || count > refs.length) throw new Error('Use between 2 and N identity sets')
  const blocks = Array.from({ length: count }, () => [])
  for (const ref of refs) {
    const assigned = Number(assignments[ref])
    if (!Number.isInteger(assigned) || assigned < 0 || assigned >= count) {
      throw new Error('Every member must be assigned to exactly one identity set')
    }
    blocks[assigned].push(ref)
  }
  if (blocks.some(block => block.length === 0)) throw new Error('Identity sets cannot be empty')
  return blocks.map(block => block.sort()).sort((left, right) => left[0].localeCompare(right[0]))
}

export function buildGroupReviewPayload({
  detail, decisionType, reviewer, comment = '', selectedRecordRefKeys = [],
  assignments = {}, setCount = 2, currentReviewEventId = null,
}) {
  if (!detail?.projection?.projection_run_id || !detail?.hypothesis_key) throw new Error('Immutable group context is required')
  const name = String(reviewer || '').trim()
  if (!name) throw new Error('Reviewer name is required')
  const members = detail.members || []
  const validRefs = new Set(members.map(member => member.record_ref_key))
  const payload = {
    projection_run_id: detail.projection.projection_run_id,
    group_hypothesis_key: detail.hypothesis_key,
    decision_type: decisionType,
    reviewer: name,
    comment: String(comment || '').trim() || null,
    supersedes_review_event_id: currentReviewEventId || null,
    selected_record_ref_keys: [],
    partitions: [],
  }
  if (decisionType === 'CONFIRM_SELECTED') {
    const selected = [...selectedRecordRefKeys]
    if (selected.length < 2 || new Set(selected).size !== selected.length || selected.some(ref => !validRefs.has(ref))) {
      throw new Error('Select at least two unique members from this group')
    }
    payload.selected_record_ref_keys = selected.sort()
  } else if (decisionType === 'SPLIT_PARTITIONS') {
    payload.partitions = canonicalSplitPartitions(members, assignments, setCount)
  } else if (!GROUP_REVIEW_DECISIONS.some(([value]) => value === decisionType)) {
    throw new Error('Choose a valid review decision')
  }
  return payload
}

export function reviewPreview(input) {
  const payload = buildGroupReviewPayload(input)
  const members = input.detail.members || []
  const partitions = payload.decision_type === 'CONFIRM_SELECTED'
    ? [payload.selected_record_ref_keys]
    : payload.partitions
  return {
    member_count: members.length,
    partition_sizes: partitions.map(block => block.length),
    ...relationshipCounts(payload.decision_type, members.length, partitions),
  }
}

export function staleReviewHandling(status) {
  return Number(status) === 409
    ? { reload: true, resubmit: false, message: 'Another review became current. The latest review was reloaded; review your choices before saving again.' }
    : { reload: false, resubmit: false, message: '' }
}

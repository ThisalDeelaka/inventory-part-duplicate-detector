export const GROUP_REVIEW_DECISIONS = [
  ['CONFIRM_ALL_AS_ONE', 'Confirm as same item'],
  ['CONFIRM_SELECTED', 'Confirm selected records as same item'],
  ['SPLIT_PARTITIONS', 'Split into separate identity sets'],
  ['KEEP_ALL_SEPARATE', 'Reject duplicate hypothesis'],
  ['UNSURE', 'Defer decision'],
]

const REVIEW_LABELS = {
  CONFIRM_ALL_AS_ONE: 'Reviewed — all confirmed as one identity',
  CONFIRM_SELECTED: 'Reviewed — selected records confirmed as one identity',
  SPLIT_PARTITIONS: 'Reviewed — split into identity sets',
  KEEP_ALL_SEPARATE: 'Reviewed — rejected and kept separate',
  UNSURE: 'Reviewed — deferred / unsure',
}

const DECISION_PRESENTATION = {
  CONFIRM_ALL_AS_ONE: {
    label: 'Confirm as same item',
    secondary: 'Confirm all records as the same underlying inventory item.',
    consequence: 'Creates one human-confirmed reviewed identity set.',
  },
  CONFIRM_SELECTED: {
    label: 'Confirm selected records as same item',
    secondary: 'Confirm only the selected records together; unselected records remain unresolved.',
    consequence: 'Creates one reviewed identity set containing only the selected records.',
  },
  SPLIT_PARTITIONS: {
    label: 'Split into separate identity sets',
    secondary: 'Assign every record to exactly one reviewed identity set.',
    consequence: 'Creates the reviewed identity sets shown below and keeps those sets separate.',
  },
  KEEP_ALL_SEPARATE: {
    label: 'Reject duplicate hypothesis',
    secondary: 'Keep these records separate.',
    consequence: 'No reviewed duplicate set is created.',
  },
  UNSURE: {
    label: 'Defer decision',
    secondary: 'Not enough information / review later.',
    consequence: 'Leaves the group unresolved for later review.',
  },
}

export function reviewDecisionPresentation(decisionType, memberCount = 0) {
  const presentation = DECISION_PRESENTATION[decisionType]
  if (!presentation) return {
    label: 'Choose Confirm, Reject, or Defer',
    secondary: 'Select the human decision that matches your review.',
    consequence: 'No decision is saved until you submit the form.',
  }
  if (decisionType === 'CONFIRM_ALL_AS_ONE' && Number(memberCount) > 2) {
    return { ...presentation, label: 'Confirm all as same item' }
  }
  return presentation
}

export function reviewDecisionOutcome(review, memberCount = 0) {
  if (!review) return {
    title: 'No human decision saved',
    effect: 'Confirm, Reject, or Defer after reviewing the system hypothesis and record details.',
  }
  const partitions = review.partitions || []
  if (review.decision_type === 'CONFIRM_ALL_AS_ONE') return {
    title: 'Confirmed as one identity',
    effect: `One reviewed identity set contains all ${Number(memberCount) || partitions[0]?.length || 0} records.`,
  }
  if (review.decision_type === 'CONFIRM_SELECTED') {
    const selected = partitions[0]?.length || 0
    const unresolved = Math.max(0, Number(memberCount || 0) - selected)
    return {
      title: 'Selected records confirmed as one identity',
      effect: `One reviewed identity set contains ${selected} selected records; ${unresolved} records remain unresolved.`,
    }
  }
  if (review.decision_type === 'SPLIT_PARTITIONS') return {
    title: 'Split into identity sets',
    effect: `${partitions.length} reviewed identity sets were recorded; every member belongs to exactly one set.`,
  }
  if (review.decision_type === 'KEEP_ALL_SEPARATE') return {
    title: 'Rejected — keep separate',
    effect: 'No reviewed duplicate set was created; the records remain separate.',
  }
  if (review.decision_type === 'UNSURE') return {
    title: 'Deferred',
    effect: 'No reviewed duplicate set was created; the group remains unresolved for later review.',
  }
  return { title: 'Unknown saved decision', effect: 'Review history contains a decision this interface cannot describe.' }
}

export function groupReviewLabel(state) {
  if (!state?.reviewed) return 'Not reviewed'
  return REVIEW_LABELS[state.current_decision_type]
    || 'Reviewed — unknown decision'
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

export function versionedIdentityGroupReviewTargets(scanId, versionedGroupKey) {
  const scan = positive(scanId, 'scanId')
  const key = String(versionedGroupKey || '').trim()
  if (!key) throw new Error('versionedGroupKey is required')
  const base = `/api/scans/${scan}/identity-read/groups/${encodeURIComponent(key)}/reviews`
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
  const refs = members.map(member => member.stable_record_reference || member.record_ref_key)
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
  const validRefs = new Set(members.map(member => member.stable_record_reference || member.record_ref_key))
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

export function buildVersionedGroupReviewPayload(input) {
  const legacy = buildGroupReviewPayload({
    ...input,
    detail: {
      ...input.detail,
      projection: { projection_run_id: 1 },
      hypothesis_key: 'versioned-target',
    },
  })
  const {
    projection_run_id: _projectionRunId,
    group_hypothesis_key: _hypothesisKey,
    ...payload
  } = legacy
  return payload
}

export function versionedReviewPreview(input) {
  const payload = buildVersionedGroupReviewPayload(input)
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

export function reviewSaveErrorState(status) {
  if (Number(status) === 409) return {
    reload: true,
    resubmit: false,
    message: 'Decision not saved because another review became current. The latest decision was reloaded; check it before trying again.',
  }
  if (Number(status) === 422) return {
    reload: false,
    resubmit: false,
    message: 'Decision not saved. Check the selected records, identity sets, and reviewer details, then try again.',
  }
  return {
    reload: false,
    resubmit: false,
    message: 'Decision not saved because the review service could not be reached. Check your connection and try again.',
  }
}

export function staleReviewHandling(status) {
  const state = reviewSaveErrorState(status)
  return Number(status) === 409 ? state : { reload: false, resubmit: false, message: '' }
}

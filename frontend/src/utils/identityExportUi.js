const AFFIRMATIVE_DECISIONS = new Set([
  'CONFIRM_ALL_AS_ONE',
  'CONFIRM_SELECTED',
  'SPLIT_PARTITIONS',
])

export function summarizeReviewedExportAvailability(groups = [], totalGroups = groups.length) {
  const states = groups.map(group => group?.review_state || {})
  const reviewedGroups = states.filter(state => state.reviewed).length
  const affirmativeGroups = states.filter(state => (
    state.reviewed && AFFIRMATIVE_DECISIONS.has(state.current_decision_type)
  )).length
  const rejectedGroups = states.filter(state => (
    state.reviewed && state.current_decision_type === 'KEEP_ALL_SEPARATE'
  )).length
  const deferredGroups = states.filter(state => (
    state.reviewed && state.current_decision_type === 'UNSURE'
  )).length
  const unreviewedGroups = Math.max(0, (Number(totalGroups) || 0) - reviewedGroups)
  return {
    status: 'ready',
    total_groups: Number(totalGroups) || 0,
    reviewed_groups: reviewedGroups,
    affirmative_groups: affirmativeGroups,
    rejected_groups: rejectedGroups,
    deferred_groups: deferredGroups,
    unreviewed_groups: unreviewedGroups,
    has_confirmed_sets: affirmativeGroups > 0,
    is_partial_review: reviewedGroups < (Number(totalGroups) || 0),
  }
}

export function reviewedExportGuidance(state) {
  if (!state || state.status === 'loading') {
    return 'Checking current human decisions before enabling the reviewed export…'
  }
  if (state.status === 'error') {
    return 'Reviewed export availability could not be checked. Reload the current review state before exporting.'
  }
  if (!state.has_confirmed_sets) {
    if (state.reviewed_groups > 0) {
      return 'No human-confirmed same-identity sets are available. Current Reject or Defer decisions create no reviewed identity set.'
    }
    return 'No human-confirmed same-identity sets are available yet. Review candidates before exporting operational results.'
  }
  if (state.is_partial_review) {
    return 'This export contains only currently confirmed identity sets. Some system groups remain unreviewed; rejected, deferred, and superseded decisions are excluded.'
  }
  return 'This export contains only current human-confirmed identity sets. Rejected, deferred, and superseded decisions are excluded.'
}

export function exportSuccessFeedback(kind) {
  if (kind === 'reviewed' || kind === 'reviewed-xlsx') return 'Reviewed identity export prepared. This file contains current human-confirmed same-identity sets only.'
  if (kind === 'system-csv' || kind === 'system-xlsx') return 'System suggestions export prepared. This file contains machine-generated review hypotheses.'
  return 'Supporting analytical export prepared.'
}

export function exportFailureFeedback(kind, status) {
  const subject = (kind === 'reviewed' || kind === 'reviewed-xlsx') ? 'Reviewed identity export' : 'System suggestions export'
  if (Number(status) === 404) return `${subject} is not available for this scan.`
  if (Number(status) === 409) return `${subject} could not be prepared because the identity result is not ready. Reload the scan result and try again.`
  if (Number(status) === 422) return `${subject} could not be prepared from the selected authoritative result.`
  return `${subject} failed. Check your connection and try again.`
}

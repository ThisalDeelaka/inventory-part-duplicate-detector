const GROUP_STATUS_LABELS = {
  LIKELY_DUPLICATE_GROUP: 'Likely duplicate group',
  POSSIBLE_DUPLICATE_GROUP_REVIEW: 'Possible duplicate group — review',
}

const EDGE_CLASS_LABELS = {
  STRONG_SUPPORT: 'Strong support',
  REVIEW_SUPPORT: 'Review support',
  NON_GROUPABLE: 'Neutral / non-groupable',
  CANNOT_LINK: 'Cannot link — inconsistent accepted group',
}

const EVIDENCE_SOURCE_LABELS = {
  PERSISTED_CANDIDATE: 'Saved candidate evidence',
  PERSISTED_EXCLUSION: 'Saved exclusion evidence',
  HUMAN_FEEDBACK: 'Previous human decision',
  G1_LOCAL_RESCORING: 'Local deterministic cross-check',
}

const DIAGNOSTIC_STATUS_LABELS = {
  CONFLICTING_FAMILY: 'Conflicting candidate family',
  DEFERRED_OVERSIZED_FAMILY: 'Deferred oversized candidate family',
  DEFERRED_AMBIGUOUS_RECORD_FAMILY: 'Deferred ambiguous-record family',
}

const REASON_LABELS = {
  CRITICAL_MISMATCH_STRUCTURAL_ROLE: 'Structural role conflict',
  CRITICAL_MISMATCH_END_POSITION: 'Drive-end / non-drive-end conflict',
  CRITICAL_MISMATCH_SERIALIZATION_ROLE: 'Serial / non-serial role conflict',
  CRITICAL_MISMATCH_FLOW_ROLE: 'Inlet / outlet role conflict',
  HUMAN_NON_DUPLICATE: 'Previously marked not duplicate',
  AMBIGUOUS_SCAN_LOCAL_RECORD_REF: 'Ambiguous scan-local record evidence',
}

function fallbackLabel(value, fallback) {
  const text = String(value || '').trim()
  return text ? `${fallback} (${text})` : fallback
}

export const groupStatusLabel = status => GROUP_STATUS_LABELS[status]
  || fallbackLabel(status, 'Unknown group status')
export const edgeClassLabel = value => EDGE_CLASS_LABELS[value]
  || fallbackLabel(value, 'Unknown edge class')
export const evidenceSourceLabel = value => EVIDENCE_SOURCE_LABELS[value]
  || fallbackLabel(value, 'Unknown evidence source')
export const diagnosticStatusLabel = value => DIAGNOSTIC_STATUS_LABELS[value]
  || fallbackLabel(value, 'Unknown diagnostic status')
export const reasonLabel = value => REASON_LABELS[value]
  || String(value || 'Unspecified reason').toLowerCase().replaceAll('_', ' ')

export function identityGroupTargets(scanId, options = {}) {
  const id = Number(scanId)
  if (!Number.isInteger(id) || id <= 0) throw new Error('scanId must be a positive integer')
  const base = `/api/scans/${id}`
  const query = new URLSearchParams()
  if (options.projectionRunId) query.set('projection_run_id', String(options.projectionRunId))
  if (options.status) query.set('status', options.status)
  if (options.minimumGroupSize) query.set('minimum_group_size', String(options.minimumGroupSize))
  if (options.maximumGroupSize) query.set('maximum_group_size', String(options.maximumGroupSize))
  if (options.limit) query.set('limit', String(options.limit))
  if (options.offset) query.set('offset', String(options.offset))
  const suffix = query.toString() ? `?${query}` : ''
  return {
    projections: `${base}/identity-group-projections`,
    summary: `${base}/identity-groups/summary${options.projectionRunId ? `?projection_run_id=${options.projectionRunId}` : ''}`,
    groups: `${base}/identity-groups${suffix}`,
    groupDetail: groupId => `${base}/identity-groups/${Number(groupId)}${options.projectionRunId ? `?projection_run_id=${options.projectionRunId}` : ''}`,
    diagnostics: `${base}/identity-group-diagnostics${suffix}`,
    diagnosticDetail: diagnosticId => `${base}/identity-group-diagnostics/${Number(diagnosticId)}${options.projectionRunId ? `?projection_run_id=${options.projectionRunId}` : ''}`,
  }
}

export function identityReadTargets(scanId, options = {}) {
  const id = Number(scanId)
  if (!Number.isInteger(id) || id <= 0) throw new Error('scanId must be a positive integer')
  const base = `/api/scans/${id}/identity-read`
  const query = new URLSearchParams()
  if (options.status) query.set('status', options.status)
  if (options.minimumGroupSize) query.set('minimum_group_size', String(options.minimumGroupSize))
  if (options.maximumGroupSize) query.set('maximum_group_size', String(options.maximumGroupSize))
  if (options.limit) query.set('limit', String(options.limit))
  if (options.offset) query.set('offset', String(options.offset))
  const suffix = query.toString() ? `?${query}` : ''
  const groupPath = key => `${base}/groups/${encodeURIComponent(String(key))}`
  return {
    summary: `${base}/summary`,
    groups: `${base}/groups${suffix}`,
    groupDetail: groupPath,
    outcomes: `${base}/outcomes`,
    reviewHistory: key => `${groupPath(key)}/reviews`,
    currentReview: key => `${groupPath(key)}/reviews/current`,
    createReview: key => `${groupPath(key)}/reviews`,
    advisoryEligibility: key => `${groupPath(key)}/advisory/eligibility`,
  }
}

export function identityReadExportTargets(scanId) {
  const id = Number(scanId)
  if (!Number.isInteger(id) || id <= 0) throw new Error('scanId must be a positive integer')
  const base = `/api/scans/${id}/identity-read`
  return {
    systemGroups: {
      path: `${base}/system-groups/export.csv`,
      filename: `scan-${id}-system-groups.csv`,
    },
    reviewedIdentities: {
      path: `${base}/reviewed-identities/export.csv`,
      filename: `scan-${id}-reviewed-identities.csv`,
    },
    conflicts: {
      path: `${base}/conflicts/export.csv`,
      filename: `scan-${id}-identity-conflicts.csv`,
    },
    deferred: {
      path: `${base}/deferred/export.csv`,
      filename: `scan-${id}-deferred-identity-work.csv`,
    },
  }
}

export const validationModeLabel = mode => ({
  LEGACY_COMPLETE_PAIRWISE: 'Legacy complete pairwise validation',
  COMPLETE_PAIRWISE: 'Complete pairwise validation',
  PROGRESSIVE_TARGETED: 'Progressive targeted validation',
}[mode] || fallbackLabel(mode, 'Unknown validation mode'))

export function validationCoverageLabel(coverage = {}) {
  const evaluated = Number(coverage.evaluated_internal_pair_count || 0)
  const possible = Number(coverage.possible_internal_pair_count || 0)
  const missing = Number(coverage.missing_nonrequired_pair_count || 0)
  return `${evaluated} of ${possible} relationships evaluated${missing ? ` · ${missing} missing non-required` : ''}`
}

export function identityReadErrorState(status, message = '') {
  if (Number(status) === 409) return {
    kind: 'not-ready',
    title: 'Identity result is not ready',
    message: message || 'The authoritative identity snapshot is not ready yet.',
  }
  if (Number(status) === 422) return {
    kind: 'inconsistent',
    title: 'Identity authority is inconsistent',
    message: message || 'The authoritative identity snapshot could not be validated.',
  }
  return { kind: 'error', title: 'Identity result could not be loaded', message }
}

export function identityGroupExportTargets(scanId, projectionRunId) {
  const id = Number(scanId)
  if (!Number.isInteger(id) || id <= 0) throw new Error('scanId must be a positive integer')
  const suffix = projectionRunId ? `?projection_run_id=${Number(projectionRunId)}` : ''
  return {
    groups: {
      path: `/api/scans/${id}/identity-groups/export.csv${suffix}`,
      filename: `scan-${id}-identity-groups.csv`,
    },
    diagnostics: {
      path: `/api/scans/${id}/identity-group-diagnostics/export.csv${suffix}`,
      filename: `scan-${id}-identity-group-diagnostics.csv`,
    },
  }
}

export function reviewedIdentityExportTarget(scanId, projectionRunId) {
  const id = Number(scanId)
  if (!Number.isInteger(id) || id <= 0) throw new Error('scanId must be a positive integer')
  const run = projectionRunId == null ? null : Number(projectionRunId)
  if (run != null && (!Number.isInteger(run) || run <= 0)) {
    throw new Error('projectionRunId must be a positive integer')
  }
  const suffix = run ? `?projection_run_id=${run}` : ''
  return {
    path: `/api/scans/${id}/identity-groups/reviewed-export.csv${suffix}`,
    filename: `scan-${id}-reviewed-identity-decisions.csv`,
  }
}

export function mappingWarnings(summary = {}) {
  const warnings = []
  if ((summary.different_basis_pair_count || 0) > 0) warnings.push('Different-basis unit relationships')
  if ((summary.missing_or_wildcard_pair_count || 0) > 0) warnings.push('Missing or wildcard units')
  if ((summary.malformed_or_unknown_pair_count || 0) > 0) warnings.push('Unknown unit relationships')
  if ((summary.possible_mapping_error_count || 0) > 0) warnings.push('Possible unit/mapping inconsistency')
  return warnings
}

export function hasCannotLink(detail) {
  return Boolean(detail?.internal_edges?.some(edge => edge.edge_class === 'CANNOT_LINK'))
}

export function groupSizeDistributionLabel(distribution = {}) {
  const rows = Object.entries(distribution).sort((a, b) => Number(a[0]) - Number(b[0]))
  return rows.length ? rows.map(([size, count]) => `${size} records: ${count}`).join(' · ') : 'No accepted groups'
}

export function pageOffset(page, limit) {
  return Math.max(0, Number(page) || 0) * Math.max(1, Number(limit) || 1)
}

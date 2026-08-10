export const DETERMINISTIC_AUTHORITY_LABEL =
  'Deterministic result — authoritative'
export const ADVISORY_AUTHORITY_LABEL =
  'Advisory only — the deterministic result remains authoritative.'

const CONTEXTS = new Set(['PART_NO', 'DESCRIPTION'])
const SAFE_CATEGORIES = new Set([
  'disabled',
  'configuration',
  'timeout',
  'rate_limited',
  'provider_5xx',
  'provider_timeout',
  'network_failure',
  'provider_failure',
  'invalid_provider_output',
  'llm_failure',
])

export const EFFECTIVE_STATUS_OPTIONS = [
  ['', 'All'],
  ['LLM_LIKELY_DUPLICATE', 'LLM likely duplicate'],
  ['LLM_DOWNGRADED', 'LLM downgraded'],
  ['HUMAN_REVIEW', 'Human review'],
  ['LLM_PENDING', 'LLM pending'],
  ['LLM_FAILED', 'LLM failed'],
  ['NOT_APPLICABLE', 'Not applicable'],
]

export const AI_ENHANCEMENT_FILTERS = [
  ['', 'All'],
  ['STANDARD', 'Standard deterministic'],
  ['RECALL', 'Recall rescue'],
  ['SEMANTIC', 'Semantic-profile resolution'],
  ['PAIRWISE', 'Pairwise LLM fallback'],
]

const TRIAGE_STATES = new Set([
  'QUEUED', 'RUNNING', 'PAUSED', 'COMPLETED', 'COMPLETED_WITH_FAILURES', 'FAILED',
])

const TRIAGE_FAILURE_LABELS = new Map([
  ['rate_limited', 'Rate limited'],
  ['provider_5xx', 'Provider unavailable'],
  ['provider_timeout', 'Provider timeout'],
  ['network_failure', 'Network failure'],
  ['invalid_provider_output', 'Invalid provider output'],
  ['provider_failure', 'Other provider failure'],
])

const STATUS_FALLBACKS = {
  404: 'Candidate unavailable.',
  422: 'Invalid bounded input.',
  502: 'LLM provider response was unavailable or invalid.',
  503: 'LLM assistance is disabled or not configured.',
  504: 'LLM provider request timed out.',
}

function safeMessage(value) {
  if (typeof value !== 'string' || !value.trim()) return ''
  const text = value.trim().slice(0, 240)
  if (/api[_-]?key|authorization|bearer\s|gsk_|sk-|secret|password|token|cookie|headers?|request id|exception|traceback|stack trace|prompt|raw response/i.test(text)) {
    return ''
  }
  return text
}

export function normalizeLlmError(status, payload) {
  const detail = payload && typeof payload === 'object' ? payload.detail : null
  const category = detail && typeof detail === 'object' && SAFE_CATEGORIES.has(detail.category)
    ? detail.category
    : status === 404
      ? 'candidate_unavailable'
      : status === 422
        ? 'invalid_input'
        : 'unavailable'
  const backendMessage = detail && typeof detail === 'object'
    ? safeMessage(detail.message)
    : safeMessage(detail)
  return {
    status,
    category,
    message: backendMessage || STATUS_FALLBACKS[status] || 'LLM assistance is unavailable.',
  }
}

export function deriveLlmStatus(status, failed = false) {
  if (failed || !status) {
    return { label: 'Unavailable', tone: 'unavailable', detail: 'Status could not be loaded.' }
  }
  if (!status.enabled) {
    return { label: 'Off', tone: 'off', detail: 'Optional LLM assistance is disabled.' }
  }
  if (status.provider_configured) {
    return {
      label: 'Ready',
      tone: 'ready',
      detail: status.provider + ' · ' + status.model,
    }
  }
  return { label: 'Unavailable', tone: 'unavailable', detail: 'Provider is not configured.' }
}

export function cleanColumnSamples(values) {
  if (!Array.isArray(values)) return []
  return values
    .filter(value => typeof value === 'string' && value.trim())
    .slice(0, 5)
    .map(value => value.slice(0, 512))
}

export function assertDifficultContext(context) {
  if (!CONTEXTS.has(context)) throw new Error('Invalid difficult-value context.')
  return context
}

export function assertPositiveCandidateId(candidateId) {
  const value = Number(candidateId)
  if (!Number.isInteger(value) || value <= 0) throw new Error('Candidate ID must be positive.')
  return value
}

export function candidateAdvisoryRequest(candidateId) {
  const id = assertPositiveCandidateId(candidateId)
  return { path: '/api/llm/candidates/' + id + '/advisory', options: { method: 'POST' } }
}

export function scanExportTargets(scanId) {
  const id = assertPositiveCandidateId(scanId)
  return {
    candidates: {
      path: `/api/scans/${id}/export`,
      filename: `scan-${id}-candidates.csv`,
    },
    exclusions: {
      path: `/api/scans/${id}/rejections/export`,
      filename: `scan-${id}-rule-exclusions.csv`,
    },
    candidatesWithLlm: {
      path: `/api/scans/${id}/export-with-llm`,
      filename: `scan-${id}-candidates-with-llm.csv`,
    },
    exclusionsWithLlm: {
      path: `/api/scans/${id}/rejections/export-with-llm`,
      filename: `scan-${id}-rule-exclusions-with-llm.csv`,
    },
  }
}

export function scanTriageTargets(scanId) {
  const id = assertPositiveCandidateId(scanId)
  const base = `/api/scans/${id}/llm-triage`
  return {
    status: { path: base, options: {} },
    start: { path: base, options: { method: 'POST' } },
    retryFailed: { path: `${base}/retry-failed`, options: { method: 'POST' } },
  }
}

export function normalizeTriageStatus(value) {
  if (!value || typeof value !== 'object' || !TRIAGE_STATES.has(value.state)) {
    throw new Error('Invalid LLM triage status.')
  }
  const numeric = key => Math.max(0, Number.isFinite(Number(value[key])) ? Number(value[key]) : 0)
  const total = numeric('total_eligible')
  const processed = numeric('processed_count')
  const skipped = numeric('skipped_count')
  const rawCategories = value.failure_categories && typeof value.failure_categories === 'object'
    ? value.failure_categories
    : {}
  const failureCategories = Object.fromEntries(
    [...TRIAGE_FAILURE_LABELS.keys()]
      .filter(key => Number(rawCategories[key]) > 0)
      .map(key => [key, Math.max(0, Number(rawCategories[key]))]),
  )
  return {
    ...value,
    total_eligible: total,
    processed_count: processed,
    likely_duplicate_count: numeric('likely_duplicate_count'),
    downgraded_count: numeric('downgraded_count'),
    human_review_count: numeric('human_review_count'),
    failed_count: numeric('failed_count'),
    skipped_count: skipped,
    failure_categories: failureCategories,
    progress_percent: total ? Math.min(100, Math.round((processed + skipped) * 10000 / total) / 100) : 100,
  }
}

export function triageFailureLabel(category) {
  return TRIAGE_FAILURE_LABELS.get(category) || 'Provider failure'
}

export function shouldPollTriage(state) {
  return state === 'QUEUED' || state === 'RUNNING'
}

export function effectiveStatusLabel(status) {
  return new Map(EFFECTIVE_STATUS_OPTIONS).get(status) || 'Unknown'
}

export function filterAndPrioritizeCandidates(candidates, selectedStatus = '') {
  if (!Array.isArray(candidates)) return []
  const predicates = {
    STANDARD: candidate => candidate.candidate_source !== 'DETERMINISTIC_RECALL_EXPANSION',
    RECALL: candidate => candidate.candidate_source === 'DETERMINISTIC_RECALL_EXPANSION',
    SEMANTIC: candidate => candidate.resolution_source === 'SEMANTIC_PROFILE_COMPARISON',
    PAIRWISE: candidate => candidate.resolution_source === 'PAIRWISE_LLM_FALLBACK',
  }
  const filtered = selectedStatus
    ? candidates.filter(predicates[selectedStatus] || (candidate => candidate.effective_status === selectedStatus))
    : [...candidates]
  return filtered.sort((left, right) => {
    const leftPriority = left.effective_status === 'LLM_LIKELY_DUPLICATE' ? 0 : 1
    const rightPriority = right.effective_status === 'LLM_LIKELY_DUPLICATE' ? 0 : 1
    return leftPriority - rightPriority
  })
}

export function columnSuggestionStateKey(sourceColumn) {
  return 'column:' + String(sourceColumn)
}

export function difficultValueStateKey(candidateId, side, context) {
  return 'candidate:' + assertPositiveCandidateId(candidateId) + ':' + side + ':' + assertDifficultContext(context)
}

export function isCurrentRequest(currentRequestId, responseRequestId) {
  return currentRequestId === responseRequestId
}

export function nextValidationToken(currentRequestId, fileGeneration) {
  return {
    requestId: currentRequestId + 1,
    fileGeneration,
  }
}

export function isCurrentValidationToken(token, currentRequestId, currentFileGeneration) {
  return Boolean(
    token
    && token.requestId === currentRequestId
    && token.fileGeneration === currentFileGeneration
  )
}

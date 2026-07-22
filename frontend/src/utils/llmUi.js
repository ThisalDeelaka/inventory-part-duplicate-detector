export const DETERMINISTIC_AUTHORITY_LABEL =
  'Deterministic result — authoritative'
export const ADVISORY_AUTHORITY_LABEL =
  'Advisory only — the deterministic result remains authoritative.'

const CONTEXTS = new Set(['PART_NO', 'DESCRIPTION'])
const SAFE_CATEGORIES = new Set([
  'disabled',
  'configuration',
  'timeout',
  'provider_failure',
  'invalid_provider_output',
  'llm_failure',
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

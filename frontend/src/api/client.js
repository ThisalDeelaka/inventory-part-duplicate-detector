import {
  assertDifficultContext,
  assertPositiveCandidateId,
  candidateAdvisoryRequest,
  cleanColumnSamples,
  normalizeLlmError,
} from '../utils/llmUi'

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, options)
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try { const body = await response.json(); message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail || body) } catch {}
    throw new Error(message)
  }
  return response
}

async function llmJson(path, options = {}) {
  const response = await fetch(API + path, options)
  let payload = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }
  if (!response.ok) {
    const safe = normalizeLlmError(response.status, payload)
    const error = new Error(safe.message)
    error.category = safe.category
    error.status = safe.status
    throw error
  }
  return payload
}

export const getLlmStatus = () => llmJson('/api/llm/status')

export function requestColumnSuggestion(sourceColumn, sampleValues) {
  const samples = cleanColumnSamples(sampleValues)
  if (!String(sourceColumn).trim() || !samples.length) {
    throw new Error('A source column and at least one nonblank sample are required.')
  }
  return llmJson('/api/llm/column-suggestions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ source_column: sourceColumn, sample_values: samples }),
  })
}

export function interpretDifficultValue(rawValue, fieldContext, itemFamilyContext) {
  assertDifficultContext(fieldContext)
  if (typeof rawValue !== 'string' || !rawValue.trim()) {
    throw new Error('A nonblank visible value is required.')
  }
  const body = { raw_value: rawValue, field_context: fieldContext }
  if (typeof itemFamilyContext === 'string' && itemFamilyContext.trim()) {
    body.item_family_context = itemFamilyContext.trim().slice(0, 128)
  }
  return llmJson('/api/llm/difficult-values/interpret', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function requestCandidateAdvisory(candidateId) {
  assertPositiveCandidateId(candidateId)
  const { path, options } = candidateAdvisoryRequest(candidateId)
  return llmJson(path, options)
}

export const api = {
  json: async (path, options) => (await request(path, options)).json(),
  get: (path) => api.json(path),
  postJson: (path, body) => api.json(path, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) }),
  postForm: (path, body) => api.json(path, { method: 'POST', body }),
  download: async (path, filename, options) => {
    const blob = await (await request(path, options)).blob()
    const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url)
  },
  baseUrl: API,
  getLlmStatus,
  requestColumnSuggestion,
  interpretDifficultValue,
  requestCandidateAdvisory,
}

import {
  assertDifficultContext,
  assertPositiveCandidateId,
  candidateAdvisoryRequest,
  cleanColumnSamples,
  normalizeLlmError,
  normalizeTriageStatus,
  scanTriageTargets,
} from '../utils/llmUi'
import { identityGroupTargets, identityReadTargets } from '../utils/identityGroupUi'
import {
  identityGroupReviewTargets,
  versionedIdentityGroupReviewTargets,
} from '../utils/identityGroupReviewUi'

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, options)
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    let category = null
    try {
      const body = await response.json()
      const detail = body.detail || body
      message = typeof detail === 'string' ? detail : (detail.message || JSON.stringify(detail))
      category = typeof detail === 'object' ? detail.category : null
    } catch {}
    const error = new Error(message)
    error.status = response.status
    error.category = category
    throw error
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

async function triageRequest(scanId, action) {
  const target = scanTriageTargets(scanId)[action]
  return normalizeTriageStatus(await llmJson(target.path, target.options))
}

export const getLlmTriageStatus = scanId => triageRequest(scanId, 'status')
export const startLlmTriage = scanId => triageRequest(scanId, 'start')
export const retryFailedLlmTriage = scanId => triageRequest(scanId, 'retryFailed')

export const getIdentityGroupSummary = (scanId, options = {}) =>
  api.get(identityGroupTargets(scanId, options).summary)
export const getIdentityGroups = (scanId, options = {}) =>
  api.get(identityGroupTargets(scanId, options).groups)
export const getIdentityGroupDetail = (scanId, groupId, options = {}) =>
  api.get(identityGroupTargets(scanId, options).groupDetail(groupId))
export const getIdentityDiagnostics = (scanId, options = {}) =>
  api.get(identityGroupTargets(scanId, options).diagnostics)
export const getIdentityDiagnosticDetail = (scanId, diagnosticId, options = {}) =>
  api.get(identityGroupTargets(scanId, options).diagnosticDetail(diagnosticId))
export const getIdentityGroupReviewHistory = (scanId, groupId) =>
  api.get(identityGroupReviewTargets(scanId, groupId).history)
export const getIdentityGroupCurrentReview = (scanId, groupId) =>
  api.get(identityGroupReviewTargets(scanId, groupId).current)
export const createIdentityGroupReview = (scanId, groupId, body) =>
  api.postJson(identityGroupReviewTargets(scanId, groupId).create, body)
export const getIdentityReadSummary = scanId => api.get(identityReadTargets(scanId).summary)
export const getIdentityReadGroups = (scanId, options = {}) =>
  api.get(identityReadTargets(scanId, options).groups)
export const getIdentityReadGroupDetail = (scanId, groupKey) =>
  api.get(identityReadTargets(scanId).groupDetail(groupKey))
export const getIdentityReadOutcomes = scanId => api.get(identityReadTargets(scanId).outcomes)
export const getVersionedGroupReviewHistory = (scanId, groupKey) =>
  api.get(versionedIdentityGroupReviewTargets(scanId, groupKey).history)
export const getVersionedGroupCurrentReview = (scanId, groupKey) =>
  api.get(versionedIdentityGroupReviewTargets(scanId, groupKey).current)
export const createVersionedGroupReview = (scanId, groupKey, body) =>
  api.postJson(versionedIdentityGroupReviewTargets(scanId, groupKey).create, body)
export const getVersionedGroupAdvisoryEligibility = (scanId, groupKey) =>
  api.get(identityReadTargets(scanId).advisoryEligibility(groupKey))

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
  getLlmTriageStatus,
  startLlmTriage,
  retryFailedLlmTriage,
  getIdentityGroupSummary,
  getIdentityGroups,
  getIdentityGroupDetail,
  getIdentityDiagnostics,
  getIdentityDiagnosticDetail,
  getIdentityGroupReviewHistory,
  getIdentityGroupCurrentReview,
  createIdentityGroupReview,
  getIdentityReadSummary,
  getIdentityReadGroups,
  getIdentityReadGroupDetail,
  getIdentityReadOutcomes,
  getVersionedGroupReviewHistory,
  getVersionedGroupCurrentReview,
  createVersionedGroupReview,
  getVersionedGroupAdvisoryEligibility,
}

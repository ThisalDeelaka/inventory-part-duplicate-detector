import assert from 'node:assert/strict'
import test from 'node:test'

import {
  AI_ENHANCEMENT_FILTERS,
  HYBRID_RETRIEVAL_METRIC_LABELS,
  RETRIEVAL_CHANNEL_LABELS,
  ADVISORY_AUTHORITY_LABEL,
  DETERMINISTIC_AUTHORITY_LABEL,
  EFFECTIVE_STATUS_OPTIONS,
  assertDifficultContext,
  assertPositiveCandidateId,
  candidateAdvisoryRequest,
  cleanColumnSamples,
  columnSuggestionStateKey,
  deriveLlmStatus,
  effectiveStatusLabel,
  filterAndPrioritizeCandidates,
  difficultValueStateKey,
  isCurrentRequest,
  isCurrentValidationToken,
  nextValidationToken,
  normalizeLlmError,
  normalizeTriageStatus,
  retrievalChannelLabel,
  scanExportTargets,
  scanTriageTargets,
  shouldPollTriage,
  triageFailureLabel,
} from '../src/utils/llmUi.js'

test('AI enhancement filters expose retrieval and advisory views', () => {
  assert.deepEqual(AI_ENHANCEMENT_FILTERS.map(item => item[1]), [
    'All', 'Standard deterministic', 'Hybrid retrieval', 'Recall rescue',
    'Semantic-profile resolution', 'Pairwise LLM fallback',
  ])
})

test('AI enhancement filters separate provenance and resolution source', () => {
  const rows = [
    { id: 1, candidate_source: 'DETERMINISTIC_STANDARD', resolution_source: 'SEMANTIC_PROFILE_COMPARISON' },
    { id: 2, candidate_source: 'DETERMINISTIC_RECALL_EXPANSION', resolution_source: 'PAIRWISE_LLM_FALLBACK' },
    { id: 3, candidate_source: 'HYBRID_RETRIEVAL', resolution_source: null },
  ]
  assert.deepEqual(filterAndPrioritizeCandidates(rows, 'STANDARD').map(item => item.id), [1])
  assert.deepEqual(filterAndPrioritizeCandidates(rows, 'RECALL').map(item => item.id), [2])
  assert.deepEqual(filterAndPrioritizeCandidates(rows, 'HYBRID').map(item => item.id), [3])
  assert.deepEqual(filterAndPrioritizeCandidates(rows, 'SEMANTIC').map(item => item.id), [1])
  assert.deepEqual(filterAndPrioritizeCandidates(rows, 'PAIRWISE').map(item => item.id), [2])
})

test('hybrid retrieval filtering does not treat retrieval score as assisted status', () => {
  const rows = [
    { id: 1, candidate_source: 'HYBRID_RETRIEVAL', retrieval_score: 99, effective_status: 'HUMAN_REVIEW' },
    { id: 2, candidate_source: 'DETERMINISTIC_STANDARD', retrieval_score: null, effective_status: 'LLM_LIKELY_DUPLICATE' },
  ]
  assert.deepEqual(filterAndPrioritizeCandidates(rows, 'HYBRID').map(item => item.id), [1])
  assert.equal(filterAndPrioritizeCandidates(rows, 'HYBRID')[0].effective_status, 'HUMAN_REVIEW')
})

test('retrieval channel labels describe character vectors accurately', () => {
  assert.equal(RETRIEVAL_CHANNEL_LABELS.CHAR_VECTOR, 'Character vector')
  assert.equal(retrievalChannelLabel('CHAR_VECTOR'), 'Character vector')
  assert.equal(retrievalChannelLabel('CHAR_VECTOR_RECIPROCAL'), 'Character vector reciprocal')
  assert.doesNotMatch(retrievalChannelLabel('CHAR_VECTOR'), /semantic/i)
  assert.equal(Object.hasOwn(RETRIEVAL_CHANNEL_LABELS, 'EXACT_BLOCK'), false)
})

test('retrieval priority remains separate from deterministic and human status', () => {
  const candidate = {
    candidate_source: 'HYBRID_RETRIEVAL', retrieval_priority: 91.2,
    business_status: 'POSSIBLE_DUPLICATE_REVIEW', review_status: 'UNREVIEWED',
  }
  assert.equal(candidate.retrieval_priority, 91.2)
  assert.equal(candidate.business_status, 'POSSIBLE_DUPLICATE_REVIEW')
  assert.equal(candidate.review_status, 'UNREVIEWED')
})

test('hybrid retrieval metric labels distinguish selected, excluded, added, and budgeted stages', () => {
  assert.deepEqual(HYBRID_RETRIEVAL_METRIC_LABELS, {
    selected: 'Retrieval selected',
    tierA: 'Selected Tier A',
    tierB: 'Selected Tier B',
    tierC: 'Selected Tier C',
    postScoringExcluded: 'Excluded after deterministic checks',
    added: 'Hybrid candidates added',
    skippedByBudget: 'Skipped by candidate budget',
  })
  assert.notEqual(HYBRID_RETRIEVAL_METRIC_LABELS.selected, HYBRID_RETRIEVAL_METRIC_LABELS.added)
})

test('standard source filter excludes hybrid and recall candidates', () => {
  const rows = [
    { id: 1, candidate_source: 'DETERMINISTIC_STANDARD' },
    { id: 2, candidate_source: 'HYBRID_RETRIEVAL' },
    { id: 3, candidate_source: 'DETERMINISTIC_RECALL_EXPANSION' },
  ]
  assert.deepEqual(filterAndPrioritizeCandidates(rows, 'STANDARD').map(item => item.id), [1])
})

test('normalizes safe backend errors and rejects secret or raw payload text', () => {
  assert.deepEqual(
    normalizeLlmError(504, { detail: { category: 'timeout', message: 'LLM provider request timed out' } }),
    { status: 504, category: 'timeout', message: 'LLM provider request timed out' },
  )
  const unsafe = normalizeLlmError(502, {
    detail: { category: 'provider_failure', message: 'Authorization: Bearer secret raw response body' },
  })
  assert.equal(unsafe.message, 'LLM provider response was unavailable or invalid.')
  assert.doesNotMatch(unsafe.message, /secret|bearer|raw response/i)
})

test('derives truthful status labels', () => {
  assert.equal(deriveLlmStatus({ enabled: false }).label, 'Off')
  assert.equal(deriveLlmStatus({ enabled: true, provider_configured: true, provider: 'groq', model: 'demo' }).label, 'Ready')
  assert.equal(deriveLlmStatus({ enabled: true, provider_configured: false }).label, 'Unavailable')
  assert.equal(deriveLlmStatus(null, true).label, 'Unavailable')
})

test('cleans column samples and enforces the five-value bound', () => {
  assert.deepEqual(cleanColumnSamples(['one', '', '  ', 'two', 'three', 'four', 'five', 'six']), ['one', 'two', 'three', 'four', 'five'])
  assert.deepEqual(cleanColumnSamples(['', '  ', null]), [])
  assert.equal(cleanColumnSamples(['x'.repeat(600)])[0].length, 512)
})

test('validates difficult-value contexts and positive candidate IDs', () => {
  assert.equal(assertDifficultContext('PART_NO'), 'PART_NO')
  assert.equal(assertDifficultContext('DESCRIPTION'), 'DESCRIPTION')
  assert.throws(() => assertDifficultContext('UOM'), /Invalid/)
  assert.equal(assertPositiveCandidateId('7'), 7)
  assert.throws(() => assertPositiveCandidateId(0), /positive/)
})

test('candidate advisory request has a positive path ID and no body', () => {
  const request = candidateAdvisoryRequest(12)
  assert.deepEqual(request, {
    path: '/api/llm/candidates/12/advisory',
    options: { method: 'POST' },
  })
  assert.equal(Object.hasOwn(request.options, 'body'), false)
})

test('scan export targets preserve deterministic downloads and add DB-only LLM-aware downloads', () => {
  const targets = scanExportTargets(12)
  assert.deepEqual(targets, {
    candidates: { path: '/api/scans/12/export', filename: 'scan-12-candidates.csv' },
    exclusions: { path: '/api/scans/12/rejections/export', filename: 'scan-12-rule-exclusions.csv' },
    candidatesWithLlm: { path: '/api/scans/12/export-with-llm', filename: 'scan-12-candidates-with-llm.csv' },
    exclusionsWithLlm: { path: '/api/scans/12/rejections/export-with-llm', filename: 'scan-12-rule-exclusions-with-llm.csv' },
  })
  for (const target of Object.values(targets)) {
    assert.match(target.path, /^\/api\/scans\/12\//)
    assert.doesNotMatch(target.path, /\/api\/llm\/|advisory|interpret|suggest/i)
  }
})

test('scan export targets reject non-positive and invalid IDs', () => {
  for (const invalidId of [0, -1, 'invalid', 1.5, null]) {
    assert.throws(() => scanExportTargets(invalidId), /positive/)
  }
})

test('triage endpoint targets are scan-scoped, bodyless, and never point to manual advisory routes', () => {
  assert.deepEqual(scanTriageTargets(12), {
    status: { path: '/api/scans/12/llm-triage', options: {} },
    start: { path: '/api/scans/12/llm-triage', options: { method: 'POST' } },
    retryFailed: { path: '/api/scans/12/llm-triage/retry-failed', options: { method: 'POST' } },
  })
  for (const target of Object.values(scanTriageTargets(12))) {
    assert.equal(target.path.includes('/api/llm/'), false); assert.equal(target.path.includes('advisory'), false); assert.equal(target.path.includes('provider'), false)
    assert.equal(Object.hasOwn(target.options, 'body'), false)
  }
})

test('triage targets reject invalid scan IDs', () => {
  for (const invalid of [0, -1, 'bad', 1.5, null]) {
    assert.throws(() => scanTriageTargets(invalid), /positive/)
  }
})

test('normalizes safe triage counters and derives bounded progress', () => {
  const normalized = normalizeTriageStatus({
    state: 'RUNNING', total_eligible: 10, processed_count: 3, skipped_count: 2,
    likely_duplicate_count: 1, downgraded_count: 1, human_review_count: 1,
    failed_count: -2,
    failure_categories: { rate_limited: 3, provider_timeout: 1, private_detail: 99 },
  })
  assert.equal(normalized.progress_percent, 50)
  assert.equal(normalized.failed_count, 0)
  assert.deepEqual(normalized.failure_categories, { rate_limited: 3, provider_timeout: 1 })
  assert.throws(() => normalizeTriageStatus({ state: 'PRIVATE_PROVIDER_STATE' }), /Invalid/)
})

test('polling is limited to queued and running states', () => {
  assert.equal(shouldPollTriage('QUEUED'), true)
  assert.equal(shouldPollTriage('RUNNING'), true)
  for (const state of ['PAUSED', 'COMPLETED', 'COMPLETED_WITH_FAILURES', 'FAILED', null]) {
    assert.equal(shouldPollTriage(state), false)
  }
})

test('paused triage and safe failure categories have clear labels', () => {
  const paused = normalizeTriageStatus({
    state: 'PAUSED', total_eligible: 5, processed_count: 2, skipped_count: 0,
    failure_categories: { provider_5xx: 2, network_failure: 1 },
  })
  assert.equal(paused.state, 'PAUSED')
  assert.equal(shouldPollTriage(paused.state), false)
  assert.equal(triageFailureLabel('provider_5xx'), 'Provider unavailable')
  assert.equal(triageFailureLabel('network_failure'), 'Network failure')
  assert.equal(triageFailureLabel('unknown-private-value'), 'Provider failure')
})

test('effective status labels cover every filter option', () => {
  assert.deepEqual(EFFECTIVE_STATUS_OPTIONS.map(([value]) => value), [
    '', 'LLM_LIKELY_DUPLICATE', 'LLM_DOWNGRADED', 'HUMAN_REVIEW',
    'LLM_PENDING', 'LLM_FAILED', 'NOT_APPLICABLE',
  ])
  assert.equal(effectiveStatusLabel('LLM_LIKELY_DUPLICATE'), 'LLM likely duplicate')
  assert.equal(effectiveStatusLabel('unknown'), 'Unknown')
})

test('filters assisted statuses and surfaces likely duplicates first without changing scores', () => {
  const input = [
    { id: 1, effective_status: 'HUMAN_REVIEW', similarity_score: 90 },
    { id: 2, effective_status: 'LLM_LIKELY_DUPLICATE', similarity_score: 70 },
    { id: 3, effective_status: 'LLM_DOWNGRADED', similarity_score: 80 },
  ]
  const prioritized = filterAndPrioritizeCandidates(input)
  assert.deepEqual(prioritized.map(item => item.id), [2, 1, 3])
  assert.deepEqual(prioritized.map(item => item.similarity_score), [70, 90, 80])
  assert.deepEqual(
    filterAndPrioritizeCandidates(input, 'LLM_DOWNGRADED').map(item => item.id),
    [3],
  )
  assert.deepEqual(input.map(item => item.id), [1, 2, 3])
})

test('state keys are stable and context-specific', () => {
  assert.equal(columnSuggestionStateKey('Stock Ref'), 'column:Stock Ref')
  assert.equal(difficultValueStateKey(3, 'A', 'PART_NO'), 'candidate:3:A:PART_NO')
  assert.notEqual(
    difficultValueStateKey(3, 'A', 'PART_NO'),
    difficultValueStateKey(3, 'B', 'PART_NO'),
  )
})

test('late responses cannot pass a newer request identity', () => {
  assert.equal(isCurrentRequest(4, 4), true)
  assert.equal(isCurrentRequest(5, 4), false)
})

test('current validation request and file generation are accepted', () => {
  const token = nextValidationToken(4, 2)
  assert.deepEqual(token, { requestId: 5, fileGeneration: 2 })
  assert.equal(isCurrentValidationToken(token, 5, 2), true)
})

test('older validation request IDs are rejected', () => {
  const stale = { requestId: 4, fileGeneration: 2 }
  assert.equal(isCurrentValidationToken(stale, 5, 2), false)
})

test('previous file generations are rejected even when request IDs match', () => {
  const staleFile = { requestId: 5, fileGeneration: 1 }
  assert.equal(isCurrentValidationToken(staleFile, 5, 2), false)
})

test('stale validation error and finalizer tokens are rejected', () => {
  const staleError = { requestId: 3, fileGeneration: 2 }
  const staleFinalizer = { requestId: 4, fileGeneration: 1 }
  assert.equal(isCurrentValidationToken(staleError, 4, 2), false)
  assert.equal(isCurrentValidationToken(staleFinalizer, 4, 2), false)
})

test('validation retry creates a newer request identity', () => {
  const first = nextValidationToken(0, 7)
  const retry = nextValidationToken(first.requestId, 7)
  assert.equal(retry.requestId, first.requestId + 1)
  assert.equal(isCurrentValidationToken(first, retry.requestId, 7), false)
  assert.equal(isCurrentValidationToken(retry, retry.requestId, 7), true)
})

test('authority labels cannot be inverted', () => {
  assert.equal(DETERMINISTIC_AUTHORITY_LABEL, 'Deterministic result — authoritative')
  assert.equal(ADVISORY_AUTHORITY_LABEL, 'Advisory only — the deterministic result remains authoritative.')
  assert.notEqual(DETERMINISTIC_AUTHORITY_LABEL, ADVISORY_AUTHORITY_LABEL)
})

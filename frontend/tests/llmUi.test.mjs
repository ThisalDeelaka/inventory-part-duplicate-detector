import assert from 'node:assert/strict'
import test from 'node:test'

import {
  ADVISORY_AUTHORITY_LABEL,
  DETERMINISTIC_AUTHORITY_LABEL,
  assertDifficultContext,
  assertPositiveCandidateId,
  candidateAdvisoryRequest,
  cleanColumnSamples,
  columnSuggestionStateKey,
  deriveLlmStatus,
  difficultValueStateKey,
  isCurrentRequest,
  isCurrentValidationToken,
  nextValidationToken,
  normalizeLlmError,
} from '../src/utils/llmUi.js'

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

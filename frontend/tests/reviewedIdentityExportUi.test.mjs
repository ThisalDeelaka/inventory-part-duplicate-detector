import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  identityGroupExportTargets,
  reviewedIdentityExportTarget,
} from '../src/utils/identityGroupUi.js'
import { scanExportTargets } from '../src/utils/llmUi.js'


const resultsSource = readFileSync(
  new URL('../src/pages/ScanResults.jsx', import.meta.url), 'utf8'
)


test('reviewed decision export has a distinct route, label, and filename', () => {
  assert.deepEqual(reviewedIdentityExportTarget(21), {
    path: '/api/scans/21/identity-groups/reviewed-export.csv',
    filename: 'scan-21-reviewed-identity-decisions.csv',
  })
  assert.match(resultsSource, />Export reviewed decisions CSV</)
  assert.match(resultsSource, />Export grouped CSV</)
})

test('reviewed export targets an exact selected projection when available', () => {
  assert.equal(
    reviewedIdentityExportTarget(21, 44).path,
    '/api/scans/21/identity-groups/reviewed-export.csv?projection_run_id=44'
  )
})

test('reviewed export never invokes review mutation or LLM endpoints', () => {
  const target = reviewedIdentityExportTarget(21, 44)
  assert.doesNotMatch(target.path, /\/reviews(?:\/|\?|$)|llm|triage|advisory/i)
  assert.match(resultsSource, /api\.download\(target\.path, target\.filename\)/)
})

test('existing G5 export targets remain byte-for-byte utility compatible', () => {
  assert.deepEqual(identityGroupExportTargets(21), {
    groups: { path: '/api/scans/21/identity-groups/export.csv', filename: 'scan-21-identity-groups.csv' },
    diagnostics: { path: '/api/scans/21/identity-group-diagnostics/export.csv', filename: 'scan-21-identity-group-diagnostics.csv' },
  })
})

test('existing pair export controls remain independent', () => {
  const targets = scanExportTargets(21)
  assert.equal(targets.candidates.path, '/api/scans/21/export')
  assert.equal(targets.exclusions.path, '/api/scans/21/rejections/export')
  assert.doesNotMatch(JSON.stringify(targets), /reviewed-export/)
})

test('no-snapshot state conditionally withholds reviewed export action', () => {
  assert.match(
    resultsSource,
    /summary\?\.snapshot_available && <button[^>]*onClick=\{exportReviewedDecisions\}>Export reviewed decisions CSV/
  )
})

test('unknown export failures render through a safe alert', () => {
  assert.match(resultsSource, /setReviewedExportError\(requestError\.message/)
  assert.match(resultsSource, /role="alert">Reviewed decisions export failed:/)
})

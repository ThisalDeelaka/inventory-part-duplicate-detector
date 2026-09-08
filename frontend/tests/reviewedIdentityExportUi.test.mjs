import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  identityGroupExportTargets,
  identityReadExportTargets,
  reviewedIdentityExportTarget,
} from '../src/utils/identityGroupUi.js'
import { scanExportTargets } from '../src/utils/llmUi.js'


const resultsSource = readFileSync(
  new URL('../src/pages/ScanResults.jsx', import.meta.url), 'utf8'
)
const exportPanelSource = readFileSync(
  new URL('../src/components/ExportAuthorityPanel.jsx', import.meta.url), 'utf8'
)


test('canonical reviewed identity export has a distinct authority-selected route, label, and filename', () => {
  assert.deepEqual(identityReadExportTargets(21).reviewedIdentities, {
    path: '/api/scans/21/identity-read/reviewed-identities/export.csv',
    filename: 'scan-21-reviewed-identity-sets.csv',
  })
  assert.match(exportPanelSource, /Reviewed Identity Export/)
  assert.match(exportPanelSource, /Export confirmed duplicate sets \(CSV\)/)
  assert.match(exportPanelSource, /Export system suggestions as CSV/)
  assert.match(exportPanelSource, /Export system suggestions as Excel/)
})

test('reviewed export targets an exact selected projection when available', () => {
  assert.equal(
    reviewedIdentityExportTarget(21, 44).path,
    '/api/scans/21/identity-groups/reviewed-export.csv?projection_run_id=44'
  )
})

test('reviewed export never invokes review mutation or LLM endpoints', () => {
  const target = identityReadExportTargets(21).reviewedIdentities
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

test('reviewed export remains explicit while backend readiness fails closed', () => {
  assert.match(exportPanelSource, /reviewedDisabled/)
  assert.match(exportPanelSource, /Reload reviewed export availability/)
  assert.match(resultsSource, /identityReadErrorState/)
})

test('unknown export failures render through a safe alert', () => {
  assert.match(resultsSource, /exportFailureFeedback\(kind, error\.status\)/)
  assert.match(exportPanelSource, /role=\{feedback\.kind === 'error' \? 'alert' : 'status'\}/)
})

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  formatElapsed,
  orderScans,
  processingGuidance,
  scanRequestError,
  scanStatusLabel,
  validationContextKey,
} from '../src/utils/productJourneyUi.js'

const dashboard = readFileSync(new URL('../src/pages/Dashboard.jsx', import.meta.url), 'utf8')
const newScan = readFileSync(new URL('../src/pages/NewScan.jsx', import.meta.url), 'utf8')
const results = readFileSync(new URL('../src/pages/ScanResults.jsx', import.meta.url), 'utf8')
const layout = readFileSync(new URL('../src/components/Layout.jsx', import.meta.url), 'utf8')

test('N1 no scans has actionable latest and history empty states', () => {
  assert.match(dashboard, /No scans yet/)
  assert.match(dashboard, /History is empty/)
  assert.match(dashboard, /Start a new scan/)
})

test('N2 one completed scan is the clear latest result', () => {
  assert.equal(scanStatusLabel('COMPLETED'), 'Completed')
  assert.match(dashboard, /latest \? 'Latest scan'/)
  assert.match(dashboard, /Most recent activity/)
})

test('N3 multiple scans are deterministically newest-first', () => {
  const ordered = orderScans([
    { id: 1, started_at: '2026-01-01T00:00:00Z' },
    { id: 3, started_at: '2026-03-01T00:00:00Z' },
    { id: 2, started_at: '2026-02-01T00:00:00Z' },
  ])
  assert.deepEqual(ordered.map(scan => scan.id), [3, 2, 1])
  assert.match(dashboard, /Recent scans/)
})

test('N4 historical scans reopen through the existing result route', () => {
  assert.match(dashboard, /to=\{`\/scans\/\$\{scan\.id\}`\}>Open results/)
})

test('N5 invalid scan URLs fail explicitly without redirecting to another result', () => {
  assert.match(results, /Scan not available/)
  assert.match(results, /It was not replaced with another scan/)
  assert.match(results, /Return to Dashboard/)
  assert.match(results, /Start a new scan/)
})

test('N6 validation success enables only the matching current context', () => {
  const key = validationContextKey(1, ['CONTRACT'], { PART_NO: 'Part' }, true)
  assert.equal(key, validationContextKey(1, ['CONTRACT'], { PART_NO: 'Part' }, true))
  assert.match(newScan, /Validation passed/)
  assert.match(newScan, /validation\?\.valid && validationIsCurrent/)
})

test('N7 validation failure is blocked with actionable guidance', () => {
  assert.match(newScan, /Validation failed/)
  assert.match(newScan, /review the warnings and required field mapping/i)
  assert.match(scanRequestError(422, 'validation').message, /validate again/)
})

test('N8 edits after validation invalidate freshness', () => {
  const original = validationContextKey(2, ['CONTRACT'], { PART_NO: 'Part' }, true)
  const edited = validationContextKey(2, ['CONTRACT'], { PART_NO: 'Changed' }, true)
  assert.notEqual(original, edited)
  assert.match(newScan, /Validation is out of date/)
})

test('N9 active synchronous processing is announced without staged progress', () => {
  assert.match(newScan, /Request active/)
  assert.match(newScan, /Processing inventory/)
  assert.match(newScan, /The scan is still running/)
  assert.match(newScan, /aria-busy="true"/)
})

test('N10 duplicate submission is guarded before React rerenders', () => {
  assert.match(newScan, /scanRequestActive\.current\) return/)
  assert.match(newScan, /scanRequestActive\.current = true/)
  assert.match(newScan, /disabled=\{!canRun\}/)
})

test('N11 elapsed and long-running wording are truthful', () => {
  assert.equal(formatElapsed(134), '02:14')
  assert.match(processingGuidance(60), /request remains active/)
  assert.match(processingGuidance(60), /do not resubmit unless an error is shown/)
})

test('N12 completion routes exactly once to the returned scan id', () => {
  assert.match(newScan, /completionRouted\.current/)
  assert.match(newScan, /nav\(`\/scans\/\$\{r\.scan_id\}`\)/)
})

test('N13 422 recovery identifies CSV or mapping rejection', () => {
  const state = scanRequestError(422, 'scan')
  assert.equal(state.title, 'Scan could not start')
  assert.match(state.message, /CSV or field mapping was rejected/)
})

test('N14 server and network recovery avoid unsupported persistence claims', () => {
  assert.match(scanRequestError(500, 'scan').message, /completed result is not known/)
  assert.match(scanRequestError(undefined, 'scan').message, /Do not assume a result exists/)
  assert.match(scanRequestError('unexpected', 'scan').message, /could not be confirmed/)
})

test('N15 zero-group completed results remain a valid non-error state', () => {
  assert.match(results, /ready authoritative snapshot contains zero potential duplicate groups/)
  assert.doesNotMatch(results, /duplicate-free/i)
})

test('N16 reopened results retain PRM-1 System explanation', () => {
  assert.match(results, /SystemExplanation/)
})

test('N17 reopened results retain PRM-2 Human decision', () => {
  assert.match(results, /GroupReviewPanel/)
})

test('N18 reopened results retain PRM-3 export authority', () => {
  assert.match(results, /ExportAuthorityPanel/)
  assert.match(layout, />Dashboard</)
  assert.match(layout, />New Scan</)
})

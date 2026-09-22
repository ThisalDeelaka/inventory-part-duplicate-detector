import test from 'node:test'
import assert from 'node:assert/strict'

import {
  relationshipLabel,
  relationshipScoreLabel,
  visibleEvidenceSections,
} from './deterministicExplanationUi.js'

test('score and signed relationship remain separate presentation facts', () => {
  assert.equal(relationshipScoreLabel(97.5), '97.50 / 100')
  assert.equal(relationshipLabel('REVIEW_SUPPORT'), 'Review Support')
})

test('only evidence-backed nonempty sections are visible', () => {
  const sections = visibleEvidenceSections({
    supporting_items: [{ code: 'DETERMINISTIC_LIKELY_DUPLICATE' }],
    weakening_items: [],
    contradiction_items: [],
    safety_items: [{ code: 'CROSS_FIELD_IDENTITY_INCOHERENCE' }],
  })
  assert.deepEqual(sections.map(([name]) => name), [
    'Supporting evidence', 'Safety / classification controls',
  ])
})

test('unknown signed state stays visible verbatim', () => {
  assert.equal(relationshipLabel('FUTURE_STATE'), 'FUTURE_STATE')
})

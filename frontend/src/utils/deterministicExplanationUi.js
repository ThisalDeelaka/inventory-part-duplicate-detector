export const relationshipLabel = value => ({
  STRONG_SUPPORT: 'Strong Support',
  REVIEW_SUPPORT: 'Review Support',
  NON_GROUPABLE: 'Neutral / Non-groupable',
  CANNOT_LINK: 'Cannot Link',
}[value] || String(value || 'Relationship state not recorded'))

export const relationshipScoreLabel = value => (
  value == null ? 'Score not recorded' : `${Number(value).toFixed(2)} / 100`
)

export function visibleEvidenceSections(detail = {}) {
  return [
    ['Supporting evidence', detail.supporting_items],
    ['Review / limiting evidence', detail.weakening_items],
    ['Contradictory evidence', detail.contradiction_items],
    ['Safety / classification controls', detail.safety_items],
  ].filter(([, items]) => Array.isArray(items) && items.length)
}

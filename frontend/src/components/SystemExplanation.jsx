export default function SystemExplanation({ explanation, compact = false, heading = 'Why the system surfaced this' }) {
  if (!explanation) return null
  if (compact) {
    return <p className="system-explanation-preview"><b>Why it was surfaced:</b> {explanation.summary}</p>
  }
  return <section className="system-explanation" aria-label={heading}>
    <p className="eyebrow">{heading}</p>
    <h3>{explanation.headline}</h3>
    <p>{explanation.summary}</p>
    {!!explanation.supporting_points?.length && <div>
      <h4>Evidence to consider</h4>
      <ul>{explanation.supporting_points.map(point => <li key={point}>{point}</li>)}</ul>
    </div>}
    {!!explanation.caution_points?.length && <div className="explanation-cautions">
      <h4>What to check</h4>
      <ul>{explanation.caution_points.map(point => <li key={point}>{point}</li>)}</ul>
    </div>}
    <p className="review-guidance"><b>Human review:</b> {explanation.review_guidance}</p>
  </section>
}

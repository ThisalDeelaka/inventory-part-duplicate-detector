import { useCallback, useEffect, useMemo, useState } from 'react'

import { api } from '../api/client'
import {
  GROUP_REVIEW_DECISIONS,
  buildVersionedGroupReviewPayload,
  reviewDecisionOutcome,
  reviewDecisionPresentation,
  reviewSaveErrorState,
  versionedReviewPreview,
} from '../utils/identityGroupReviewUi'

const memberRef = member => member.stable_record_reference || member.record_ref_key
const ADVANCED_DECISIONS = new Set(['CONFIRM_SELECTED', 'SPLIT_PARTITIONS'])

function partitionSummary(review) {
  if (!review.partitions?.length) return 'No reviewed identity sets recorded'
  return review.partitions.map((block, index) => `Set ${index + 1}: ${block.length} records`).join(' / ')
}

function DecisionState({ review, memberCount, current = false }) {
  const outcome = reviewDecisionOutcome(review, memberCount)
  return <div className={current ? 'human-decision-current' : 'human-decision-previous'}>
    <span className="decision-state-label">{!review ? 'Review status' : current ? 'Current decision' : 'Previous decision'}</span>
    <h4>{outcome.title}</h4>
    <p>{outcome.effect}</p>
    {review && current
      ? <small>This current decision controls Reviewed Identity Export.</small>
      : review ? <small>This decision remains in history but is no longer operationally authoritative.</small> : null}
  </div>
}

export default function GroupReviewPanel({ scanId, detail, onSaved = () => {} }) {
  const [open, setOpen] = useState(false)
  const [history, setHistory] = useState(null)
  const [decisionType, setDecisionType] = useState('')
  const [reviewer, setReviewer] = useState('demo-reviewer')
  const [comment, setComment] = useState('')
  const [selected, setSelected] = useState({})
  const [setCount, setSetCount] = useState(2)
  const [assignments, setAssignments] = useState(() => Object.fromEntries(
    (detail.members || []).map(member => [memberRef(member), 0])
  ))
  const [acknowledged, setAcknowledged] = useState(false)
  const [busy, setBusy] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [feedback, setFeedback] = useState(null)

  const loadHistory = useCallback(async () => {
    setLoadError('')
    try {
      const value = await api.getVersionedGroupReviewHistory(scanId, detail.versioned_group_key)
      setHistory(value)
      return value
    } catch (error) {
      setLoadError('Review state could not be loaded. No decision can be saved until the latest state is available.')
      throw error
    }
  }, [scanId, detail.versioned_group_key])

  useEffect(() => { loadHistory().catch(() => {}) }, [loadHistory])

  const current = history?.items?.find(item => item.is_current) || null
  const memberCount = detail.members?.length || 0
  const action = reviewDecisionPresentation(decisionType, memberCount)
  const showAdvanced = memberCount > 2 || ADVANCED_DECISIONS.has(current?.decision_type)
  const selectedCount = Object.values(selected).filter(Boolean).length
  const input = useMemo(() => ({
    detail,
    decisionType,
    reviewer,
    comment,
    selectedRecordRefKeys: Object.keys(selected).filter(key => selected[key]),
    assignments,
    setCount,
    currentReviewEventId: current?.review_event_id || null,
  }), [detail, decisionType, reviewer, comment, selected, assignments, setCount, current])

  let preview = null
  let validationMessage = ''
  try { preview = versionedReviewPreview(input) } catch (error) { validationMessage = error.message }
  const requiresAcknowledgement = decisionType === 'KEEP_ALL_SEPARATE'
  const canSubmit = Boolean(preview) && (!requiresAcknowledgement || acknowledged) && !busy

  const toggleEditor = () => {
    setFeedback(null)
    if (!open && current) {
      setDecisionType(current.decision_type)
      setReviewer(current.reviewer)
      setComment(current.comment || '')
      setSelected({})
      if (current.decision_type === 'CONFIRM_SELECTED') {
        setSelected(Object.fromEntries((current.partitions[0] || []).map(ref => [ref, true])))
      } else if (current.decision_type === 'SPLIT_PARTITIONS') {
        setSetCount(current.partitions.length)
        setAssignments(Object.fromEntries(
          current.partitions.flatMap((block, index) => block.map(ref => [ref, index]))
        ))
      }
    } else if (!open) {
      setDecisionType('')
    }
    setAcknowledged(false)
    setOpen(value => !value)
  }

  const submit = async event => {
    event.preventDefault()
    if (!canSubmit) return
    setBusy(true)
    setFeedback(null)
    try {
      const saved = await api.createIdentityGroupReview(
        scanId, detail.versioned_group_key, buildVersionedGroupReviewPayload(input)
      )
      const localItems = [
        ...(history?.items || []).map(item => ({ ...item, is_current: false })),
        { ...saved, is_current: true },
      ]
      setHistory(previous => ({ ...previous, items: localItems, current_review_event_id: saved.review_event_id }))
      let savedCurrent = saved
      try {
        const updated = await loadHistory()
        savedCurrent = updated.items.find(item => item.is_current) || saved
      } catch {
        setLoadError('Decision saved, but the latest decision history could not be reloaded. Reload review state before making another change.')
      }
      const outcome = reviewDecisionOutcome(savedCurrent, memberCount)
      setOpen(false)
      setAcknowledged(false)
      setFeedback({ kind: 'success', message: `Decision saved. ${outcome.title}.` })
      onSaved(saved)
    } catch (error) {
      const state = reviewSaveErrorState(error.status)
      if (state.reload) {
        try { await loadHistory() } catch {}
      }
      setFeedback({ kind: 'error', message: state.message })
    } finally {
      setBusy(false)
    }
  }

  const changeSetCount = next => {
    const bounded = Math.max(2, Math.min(memberCount, next))
    setSetCount(bounded)
    setAssignments(previous => Object.fromEntries(
      detail.members.map(member => [
        memberRef(member),
        Math.min(Number(previous[memberRef(member)]) || 0, bounded - 1),
      ])
    ))
  }

  return (
    <section className="group-review" aria-labelledby="human-decision-heading" aria-busy={busy}>
      <div className="review-state-line">
        <div><p className="eyebrow">Authoritative review</p><h3 id="human-decision-heading">Human decision</h3></div>
        {current && <small>The System explanation remains unchanged.</small>}
      </div>

      {current
        ? <DecisionState review={current} memberCount={memberCount} current />
        : <DecisionState review={null} memberCount={memberCount} />}

      {loadError ? <div className="error" role="alert">
        <p>{loadError}</p>
        <button type="button" className="secondary" onClick={() => loadHistory().catch(() => {})}>Reload review state</button>
      </div> : <button type="button" className="secondary" disabled={!history || busy} onClick={toggleEditor} aria-expanded={open} aria-controls="human-review-form">
        {!history ? 'Loading review state…' : current ? 'Change decision' : 'Review this group'}
      </button>}
      {current && !open && <small>The previous decision remains in review history when you change it.</small>}
      {feedback && <p id="review-feedback" className={feedback.kind === 'success' ? 'banner' : 'error'} role={feedback.kind === 'success' ? 'status' : 'alert'}>{feedback.message}</p>}

      {open && (
        <form id="human-review-form" className="review-form" onSubmit={submit} aria-describedby={feedback ? 'review-feedback' : undefined}>
          <h4>{current ? 'Change decision' : 'Record human decision'}</h4>
          <p>Choose what the records mean after reviewing the System explanation and item details.</p>
          {current && <p className="warning">Saving creates a new current decision. The previous decision remains in review history.</p>}
          <label>Decision<select value={decisionType} required onChange={event => { setDecisionType(event.target.value); setAcknowledged(false) }}>
            <option value="" disabled>Choose Confirm, Reject, or Defer</option>
            <optgroup label="Primary decisions">
              <option value="CONFIRM_ALL_AS_ONE">{memberCount > 2 ? 'Confirm all as same item' : 'Confirm as same item'}</option>
              <option value="KEEP_ALL_SEPARATE">Reject duplicate hypothesis</option>
              <option value="UNSURE">Defer decision</option>
            </optgroup>
            {showAdvanced && <optgroup label="Advanced multi-member decisions">
              {GROUP_REVIEW_DECISIONS.filter(([value]) => ADVANCED_DECISIONS.has(value)).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
            </optgroup>}
          </select></label>

          {decisionType && <section className="decision-consequence" aria-live="polite">
            <h4>{action.label}</h4><p>{action.secondary}</p><b>{action.consequence}</b>
          </section>}
          <label>Reviewer<input value={reviewer} maxLength="100" required onChange={event => setReviewer(event.target.value)} /></label>
          <label>Comment (optional)<textarea value={comment} maxLength="2000" onChange={event => setComment(event.target.value)} /></label>

          {decisionType === 'CONFIRM_ALL_AS_ONE' && <p className="warning">You are confirming that these {memberCount} records represent the same underlying inventory item. No inventory merge occurs.</p>}
          {decisionType === 'CONFIRM_SELECTED' && <fieldset><legend>Select records to confirm as the same item</legend>
            <p>Only selected records form the reviewed identity set. Unselected records remain unresolved. Selected: {selectedCount} of {memberCount}.</p>
            {detail.members.map(member => <label className="review-member" key={memberRef(member)}>
              <input type="checkbox" checked={Boolean(selected[memberRef(member)])} onChange={event => setSelected(previous => ({ ...previous, [memberRef(member)]: event.target.checked }))} />
              <span><b>{member.part_no}</b> — {member.description}<small>{member.contract || 'No site'} / {member.uom || 'No UOM'}</small></span>
            </label>)}
          </fieldset>}
          {decisionType === 'SPLIT_PARTITIONS' && <fieldset><legend>Assign every record to one identity set</legend>
            <p>Records in the same set are confirmed together. Different sets are kept separate.</p>
            <div className="review-set-actions"><button type="button" className="secondary" onClick={() => changeSetCount(setCount + 1)} disabled={setCount >= memberCount}>Add set</button><button type="button" className="ghost" onClick={() => changeSetCount(setCount - 1)} disabled={setCount <= 2}>Remove set</button></div>
            {detail.members.map(member => <label className="review-member" key={memberRef(member)}>
              <span><b>{member.part_no}</b> — {member.description}<small>{member.contract || 'No site'} / {member.uom || 'No UOM'}</small></span>
              <select aria-label={`Identity set for ${member.part_no}`} value={assignments[memberRef(member)] ?? 0} onChange={event => setAssignments(previous => ({ ...previous, [memberRef(member)]: Number(event.target.value) }))}>
                {Array.from({ length: setCount }, (_, index) => <option key={index} value={index}>Set {index + 1}</option>)}
              </select>
            </label>)}
          </fieldset>}
          {decisionType === 'KEEP_ALL_SEPARATE' && <label className="inline-check"><input type="checkbox" checked={acknowledged} onChange={event => setAcknowledged(event.target.checked)} /><span><b>I understand these records will remain separate</b><small>You are deciding that these records should remain separate. No merge, delete, or writeback occurs.</small></span></label>}
          {decisionType === 'UNSURE' && <p className="warning">No identity decision will be made yet. The group remains unresolved and this deferred review stays in append-only history.</p>}

          <section className="review-summary" aria-live="polite"><h4>Decision preview</h4>
            {preview ? <><span>{preview.member_count} records reviewed</span>{preview.partition_sizes.map((size, index) => <span key={index}>Set {index + 1}: {size} records</span>)}<details><summary>Advanced relationship impact</summary><p>{preview.must_link_count} must-link / {preview.cannot_link_count} cannot-link relationships</p></details></> : <p className="error">{validationMessage}</p>}
          </section>
          <div className="actions"><button type="button" className="ghost" disabled={busy} onClick={() => setOpen(false)}>Cancel</button><button type="submit" disabled={!canSubmit}>{busy ? 'Saving decision…' : current ? 'Save new current decision' : 'Save decision'}</button></div>
          {!canSubmit && decisionType === 'KEEP_ALL_SEPARATE' && !acknowledged && <small>Accept the keep-separate acknowledgement before saving.</small>}
        </form>
      )}

      <details className="review-history"><summary>Decision history ({history?.items?.length || 0})</summary>
        {!history ? <p>Loading decision history…</p> : !history.items.length ? <p>There are no previous decisions for this group.</p> : history.items.map(item => <article key={item.review_event_id} className={item.is_current ? 'current-review' : 'previous-review'} aria-label={item.is_current ? 'Current human decision' : 'Previous superseded human decision'}>
          <DecisionState review={item} memberCount={memberCount} current={item.is_current} />
          <span>{item.reviewer} — {new Date(item.created_at).toLocaleString()}</span>
          <small>{partitionSummary(item)}</small>
          {item.comment && <p>{item.comment}</p>}
        </article>)}
      </details>
    </section>
  )
}

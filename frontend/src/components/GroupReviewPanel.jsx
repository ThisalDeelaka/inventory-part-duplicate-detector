import { useCallback, useEffect, useMemo, useState } from 'react'

import { api } from '../api/client'
import {
  GROUP_REVIEW_DECISIONS,
  buildGroupReviewPayload,
  groupReviewLabel,
  reviewPreview,
  staleReviewHandling,
} from '../utils/identityGroupReviewUi'


function partitionSummary(review) {
  if (!review.partitions?.length) return 'No identity sets recorded'
  return review.partitions.map((block, index) => `Set ${index + 1}: ${block.length}`).join(' / ')
}


export default function GroupReviewPanel({ scanId, detail, onSaved }) {
  const [open, setOpen] = useState(false)
  const [history, setHistory] = useState(null)
  const [decisionType, setDecisionType] = useState('UNSURE')
  const [reviewer, setReviewer] = useState('demo-reviewer')
  const [comment, setComment] = useState('')
  const [selected, setSelected] = useState({})
  const [setCount, setSetCount] = useState(2)
  const [assignments, setAssignments] = useState(() => Object.fromEntries(
    (detail.members || []).map(member => [member.record_ref_key, 0])
  ))
  const [acknowledged, setAcknowledged] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  const loadHistory = useCallback(async () => {
    const value = await api.getIdentityGroupReviewHistory(scanId, detail.group_snapshot_id)
    setHistory(value)
    return value
  }, [scanId, detail.group_snapshot_id])

  useEffect(() => { loadHistory().catch(error => setMessage(error.message)) }, [loadHistory])

  const current = history?.items?.find(item => item.is_current) || null
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
  try { preview = reviewPreview(input) } catch (error) { validationMessage = error.message }
  const requiresAcknowledgement = decisionType === 'KEEP_ALL_SEPARATE'
  const canSubmit = Boolean(preview) && (!requiresAcknowledgement || acknowledged) && !busy

  const toggleEditor = () => {
    if (!open && current) {
      setDecisionType(current.decision_type)
      setReviewer(current.reviewer)
      setComment(current.comment || '')
      if (current.decision_type === 'CONFIRM_SELECTED') {
        setSelected(Object.fromEntries(
          (current.partitions[0] || []).map(ref => [ref, true])
        ))
      } else if (current.decision_type === 'SPLIT_PARTITIONS') {
        setSetCount(current.partitions.length)
        setAssignments(Object.fromEntries(
          current.partitions.flatMap((block, index) => block.map(ref => [ref, index]))
        ))
      }
    }
    setOpen(value => !value)
  }

  const submit = async event => {
    event.preventDefault()
    if (!canSubmit) return
    setBusy(true); setMessage('')
    try {
      const saved = await api.createIdentityGroupReview(
        scanId, detail.group_snapshot_id, buildGroupReviewPayload(input)
      )
      await loadHistory()
      onSaved(saved)
      setOpen(false)
      setAcknowledged(false)
      setMessage('Review saved. It will affect the next explicit identity projection; this snapshot was not changed.')
    } catch (error) {
      const stale = staleReviewHandling(error.status)
      if (stale.reload) {
        try { await loadHistory() } catch {}
        setMessage(stale.message)
      } else setMessage(error.message)
    } finally { setBusy(false) }
  }

  const changeSetCount = next => {
    const bounded = Math.max(2, Math.min(detail.members.length, next))
    setSetCount(bounded)
    setAssignments(previous => Object.fromEntries(
      detail.members.map(member => [
        member.record_ref_key,
        Math.min(Number(previous[member.record_ref_key]) || 0, bounded - 1),
      ])
    ))
  }

  return (
    <section className="group-review" aria-label="Human group review">
      <div className="review-state-line">
        <b>Human review: {groupReviewLabel(detail.review_state)}</b>
        {detail.review_state?.reviewed && <small>System status remains {detail.group_status}.</small>}
      </div>
      <button type="button" className="secondary" disabled={!history} onClick={toggleEditor} aria-expanded={open}>
        {!history ? 'Loading review stateâ€¦' : current ? 'Edit review' : 'Review group'}
      </button>
      {message && <p className={message.startsWith('Review saved') ? 'banner' : 'error'} role="status">{message}</p>}
      {open && (
        <form className="review-form" onSubmit={submit}>
          <p>Human review is authoritative evidence, while deterministic terminal safety conflicts remain protected.</p>
          <label>Decision<select value={decisionType} onChange={event => { setDecisionType(event.target.value); setAcknowledged(false) }}>
            {GROUP_REVIEW_DECISIONS.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
          </select></label>
          <label>Reviewer<input value={reviewer} maxLength="100" required onChange={event => setReviewer(event.target.value)} /></label>
          <label>Comment (optional)<textarea value={comment} maxLength="2000" onChange={event => setComment(event.target.value)} /></label>

          {decisionType === 'CONFIRM_ALL_AS_ONE' && <p className="warning">All {detail.members.length} records will be recorded as one reviewed identity set. No inventory merge occurs.</p>}
          {decisionType === 'CONFIRM_SELECTED' && <fieldset><legend>Select members to confirm together</legend>
            <p>Unselected records will remain unresolved.</p>
            {detail.members.map(member => <label className="review-member" key={member.record_ref_key}>
              <input type="checkbox" checked={Boolean(selected[member.record_ref_key])} onChange={event => setSelected(previous => ({ ...previous, [member.record_ref_key]: event.target.checked }))} />
              <span><b>{member.part_no}</b> â€” {member.description}<small>{member.contract || 'No site'} / {member.uom || 'No UOM'}</small></span>
            </label>)}
          </fieldset>}
          {decisionType === 'SPLIT_PARTITIONS' && <fieldset><legend>Assign every member to an identity set</legend>
            <div className="review-set-actions"><button type="button" className="secondary" onClick={() => changeSetCount(setCount + 1)} disabled={setCount >= detail.members.length}>Add set</button><button type="button" className="ghost" onClick={() => changeSetCount(setCount - 1)} disabled={setCount <= 2}>Remove set</button></div>
            {detail.members.map(member => <label className="review-member" key={member.record_ref_key}>
              <span><b>{member.part_no}</b> â€” {member.description}<small>{member.contract || 'No site'} / {member.uom || 'No UOM'}</small></span>
              <select aria-label={`Identity set for ${member.part_no}`} value={assignments[member.record_ref_key] ?? 0} onChange={event => setAssignments(previous => ({ ...previous, [member.record_ref_key]: Number(event.target.value) }))}>
                {Array.from({ length: setCount }, (_, index) => <option key={index} value={index}>Set {index + 1}</option>)}
              </select>
            </label>)}
          </fieldset>}
          {decisionType === 'KEEP_ALL_SEPARATE' && <label className="inline-check"><input type="checkbox" checked={acknowledged} onChange={event => setAcknowledged(event.target.checked)} /><span><b>Confirm every member is separate</b><small>Every member will be recorded as distinct from every other member. No merge, delete, or writeback occurs.</small></span></label>}
          {decisionType === 'UNSURE' && <p className="warning">No identity constraints will be created. This decision remains in append-only history.</p>}

          <section className="review-summary" aria-live="polite"><h4>Review summary</h4>
            {preview ? <><span>{preview.member_count} members</span>{preview.partition_sizes.map((size, index) => <span key={index}>Set {index + 1}: {size} members</span>)}<b>{preview.must_link_count} must-link relationships</b><b>{preview.cannot_link_count} cannot-link relationships</b></> : <p className="error">{validationMessage}</p>}
          </section>
          <div className="actions"><button type="button" className="ghost" onClick={() => setOpen(false)}>Cancel</button><button type="submit" disabled={!canSubmit}>{busy ? 'Savingâ€¦' : current ? 'Save corrected review' : 'Save review'}</button></div>
        </form>
      )}

      <details className="review-history"><summary>Review history ({history?.items?.length || 0})</summary>
        {!history ? <p>Loading review historyâ€¦</p> : !history.items.length ? <p>There is no review history for this group.</p> : history.items.map(item => <article key={item.review_event_id} className={item.is_current ? 'current-review' : ''}>
          <b>{GROUP_REVIEW_DECISIONS.find(([value]) => value === item.decision_type)?.[1] || item.decision_type}</b>
          <span>{item.is_current ? 'Current' : 'Superseded'} â€” {item.reviewer} â€” {new Date(item.created_at).toLocaleString()}</span>
          <small>{partitionSummary(item)}</small>
          <small>{item.derived_constraint_counts.must_link_count} must-link / {item.derived_constraint_counts.cannot_link_count} cannot-link</small>
          {item.comment && <p>{item.comment}</p>}
        </article>)}
      </details>
    </section>
  )
}

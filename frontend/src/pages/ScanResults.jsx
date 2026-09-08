import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import Score from '../components/Score'
import CandidateLlmTools from '../components/CandidateLlmTools'
import LlmStatus from '../components/LlmStatus'
import {
  EFFECTIVE_STATUS_OPTIONS,
  effectiveStatusLabel,
  filterAndPrioritizeCandidates,
  scanExportTargets,
  shouldPollTriage,
  triageFailureLabel,
} from '../utils/llmUi'

function PairTable({ items, open, setOpen, comments, setComments, review }) {
  if (!items.length) {
    return <p className="empty">No candidates met this threshold. Lower the threshold for broader discovery.</p>
  }

  return (
    <table>
      <thead>
        <tr>
          <th>Part A</th>
          <th>Part B</th>
          <th>Score</th>
          <th>Business status</th>
          <th>Rule</th>
          <th>Explanation</th>
          <th>Review</th>
        </tr>
      </thead>
      <tbody>
        {items.map((candidate) => (
          <tr key={candidate.id}>
            <td><b>{candidate.part_no_a}</b><small>{candidate.description_a}</small></td>
            <td><b>{candidate.part_no_b}</b><small>{candidate.description_b}</small></td>
            <td><Score value={candidate.similarity_score} /></td>
            <td>
              <b className="effective-status">{effectiveStatusLabel(candidate.effective_status)}</b>
              <span className={`badge ${candidate.business_status}`}>{candidate.business_status}</span>
              <small>{candidate.confidence_level}</small>
            </td>
            <td>
              <span className="rule-pill">{candidate.rule_decision}</span>
              {candidate.rejection_reason && <small>{candidate.rejection_reason}</small>}
            </td>
            <td>
              <p>{candidate.explanation}</p>
              {!!candidate.critical_mismatches?.length && (
                <div className="mismatch-list">
                  {candidate.critical_mismatches.map((mismatch, index) => (
                    <span key={`${mismatch.group}-${index}`}>
                      {mismatch.label}: {(mismatch.values_a || []).join(', ')} vs {(mismatch.values_b || []).join(', ')}
                    </span>
                  ))}
                </div>
              )}
              {(candidate.generic_description_warning || candidate.application_context_warning) && (
                <div className="mismatch-list">
                  {candidate.generic_description_warning && <span>One description is too generic to confirm duplicate identity.</span>}
                  {candidate.application_context_warning && (
                    <span>
                      Application context appears different: {(candidate.application_context_a || []).join(', ') || 'none'} vs {(candidate.application_context_b || []).join(', ') || 'none'}.
                    </span>
                  )}
                </div>
              )}
              <button type="button" className="link" onClick={() => setOpen(open === candidate.id ? null : candidate.id)}>
                {open === candidate.id ? 'Hide details' : 'Show details'}
              </button>
              {open === candidate.id && (
                <div className="details">
                  <span>TF-IDF: {candidate.tfidf_score}</span>
                  <span>Fuzzy: {candidate.fuzzy_score}</span>
                  <span>Part no: {candidate.part_no_similarity}</span>
                  <span>Technical: {candidate.technical_token_score}</span>
                  <b>Matched: {candidate.matched_fields.join(', ') || 'None'}</b>
                  <b>Mismatched: {candidate.mismatched_fields.join(', ') || 'None'}</b>
                  <b>Scan mode: {candidate.scan_mode}</b>
                  <b>Normalized description A: {candidate.normalized_description_a || 'None'}</b>
                  <b>Normalized description B: {candidate.normalized_description_b || 'None'}</b>
                  <b>Normalized part no A: {candidate.normalized_part_no_a || 'None'}</b>
                  <b>Normalized part no B: {candidate.normalized_part_no_b || 'None'}</b>
                  <p>{candidate.recommended_action}</p>
                  <div className="triage-result-card">
                    <b>Effective assisted status: {candidate.effective_status}</b>
                    <span>Deterministic result: {candidate.business_status} / {candidate.confidence_level} / {candidate.similarity_score}</span>
                    <span>LLM triage result: {candidate.llm_triage_assessment || candidate.llm_triage_state}{candidate.llm_triage_confidence == null ? '' : ` / ${candidate.llm_triage_confidence}`}</span>
                    <small>The deterministic result remains authoritative.</small>
                  </div>
                  <CandidateLlmTools candidate={candidate} />
                </div>
              )}
            </td>
            <td>
              <span className="status">{candidate.review_status}</span>
              <textarea
                placeholder="Reviewer comment"
                value={comments[candidate.id] || ''}
                onChange={(event) => setComments({ ...comments, [candidate.id]: event.target.value })}
              />
              <div className="review">
                <button type="button" onClick={() => review(candidate, 'DUPLICATE')}>Duplicate</button>
                <button type="button" className="secondary" onClick={() => review(candidate, 'NOT_DUPLICATE')}>Not duplicate</button>
                <button type="button" className="ghost" onClick={() => review(candidate, 'UNSURE')}>Unsure</button>
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function TriagePanel({ value, error, busy, start, retry }) {
  return (
    <section className="panel triage-panel" aria-label="LLM triage progress">
      <div className="llm-heading">
        <div><p className="eyebrow">Automatic assistance</p><h2>LLM triage</h2></div>
        <div className="actions">
          <button type="button" className="secondary" onClick={start} disabled={busy}>Start/Resume LLM triage</button>
          <button type="button" onClick={retry} disabled={busy || !value?.failed_count}>Retry failed</button>
        </div>
      </div>
      {error && <p className="llm-error" role="alert">{error}</p>}
      {value ? (
        <>
          {value.state === 'PAUSED' && (
            <p className="warning">LLM triage paused after repeated provider failures. Resume when the provider is available.</p>
          )}
          <div className="triage-progress"><span style={{ width: `${value.progress_percent}%` }} /></div>
          <div className="metrics">
            <span>State: {value.state}</span>
            <span>Processed: {value.processed_count} / {value.total_eligible}</span>
            <span>Likely duplicate: {value.likely_duplicate_count}</span>
            <span>Downgraded: {value.downgraded_count}</span>
            <span>Human review: {value.human_review_count}</span>
            <span>Failed: {value.failed_count}</span>
            <span>Skipped: {value.skipped_count}</span>
          </div>
          {!!Object.keys(value.failure_categories || {}).length && (
            <div className="mismatch-list" aria-label="LLM failure categories">
              {Object.entries(value.failure_categories).map(([category, count]) => (
                <span key={category}>{triageFailureLabel(category)}: {count}</span>
              ))}
            </div>
          )}
        </>
      ) : <p>No automatic triage run is available yet.</p>}
    </section>
  )
}

function GroupView({ groups, openGroup, setOpenGroup }) {
  if (!groups.length) {
    return (
      <p className="empty">
        No medium/high confidence duplicate groups were built from this scan. Pair-level results are still available.
      </p>
    )
  }

  return (
    <div className="groups">
      {groups.map((group) => (
        <article className="group-card" key={group.group_id}>
          <div className="group-head">
            <div>
              <h2>{group.group_name}</h2>
              <small>{group.part_count} parts connected by {group.pair_count} candidate pair(s)</small>
            </div>
            <div className="group-score">
              <span className={`badge ${group.confidence_level}`}>{group.confidence_level}</span>
              <Score value={group.top_score} />
            </div>
          </div>
          <p>{group.summary}</p>
          <div className="details">
            <b>Matched: {group.matched_fields.join(', ') || 'None'}</b>
            <b>Mismatched: {group.mismatched_fields.join(', ') || 'None'}</b>
            <span>Average score: {group.average_score}</span>
          </div>
          <div className="table-wrap mini">
            <table>
              <thead>
                <tr><th>Site</th><th>Part No</th><th>Description</th></tr>
              </thead>
              <tbody>
                {group.parts.map((part) => (
                  <tr key={part.key}>
                    <td>{part.contract || '-'}</td>
                    <td><b>{part.part_no}</b></td>
                    <td>{part.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button type="button" className="link" onClick={() => setOpenGroup(openGroup === group.group_id ? null : group.group_id)}>
            {openGroup === group.group_id ? 'Hide pair evidence' : 'Show pair evidence'}
          </button>
          {openGroup === group.group_id && (
            <div className="pair-evidence">
              {group.pairs.map((pair) => (
                <div className="warning" key={pair.candidate_id}>
                  <b>{pair.part_no_a} vs {pair.part_no_b}</b>
                  <small>{pair.similarity_score} - {pair.confidence_level}</small>
                  <p>{pair.explanation}</p>
                </div>
              ))}
            </div>
          )}
        </article>
      ))}
    </div>
  )
}

export default function ScanResults() {
  const { id } = useParams()
  const exportTargets = scanExportTargets(id)
  const [scan, setScan] = useState(null)
  const [items, setItems] = useState([])
  const [groups, setGroups] = useState([])
  const [view, setView] = useState('groups')
  const [open, setOpen] = useState(null)
  const [openGroup, setOpenGroup] = useState(null)
  const [comments, setComments] = useState({})
  const [error, setError] = useState('')
  const [triage, setTriage] = useState(null)
  const [triageError, setTriageError] = useState('')
  const [triageBusy, setTriageBusy] = useState(false)
  const [assistedFilter, setAssistedFilter] = useState('')

  const load = () => Promise.all([
    api.get(`/api/scans/${id}`),
    api.get(`/api/scans/${id}/candidates`),
    api.get(`/api/scans/${id}/groups`),
  ])
    .then(([scanResponse, candidateResponse, groupResponse]) => {
      setScan(scanResponse)
      setItems(candidateResponse)
      setGroups(groupResponse)
    })
    .catch((err) => setError(err.message))

  useEffect(() => { load() }, [id])

  const loadTriage = async () => {
    try {
      const response = await api.getLlmTriageStatus(id)
      setTriage(response)
      setTriageError('')
      if (!shouldPollTriage(response.state)) {
        const candidates = await api.get(`/api/scans/${id}/candidates`)
        setItems(candidates)
      }
      return response
    } catch (requestError) {
      if (requestError.status === 404) setTriage(null)
      else setTriageError(requestError.message)
      return null
    }
  }

  useEffect(() => { loadTriage() }, [id])
  useEffect(() => {
    if (!shouldPollTriage(triage?.state)) return undefined
    const timer = window.setInterval(loadTriage, 3000)
    return () => window.clearInterval(timer)
  }, [id, triage?.state])

  const triageAction = async action => {
    setTriageBusy(true); setTriageError('')
    try {
      const response = await action(id)
      setTriage(response)
    } catch (requestError) {
      setTriageError(requestError.message)
    } finally {
      setTriageBusy(false)
    }
  }

  const visibleItems = filterAndPrioritizeCandidates(items, assistedFilter)

  const review = async (candidate, decision) => {
    try {
      await api.postJson(`/api/candidates/${candidate.id}/feedback`, {
        user_decision: decision,
        user_comment: comments[candidate.id] || '',
        created_by: 'demo-reviewer',
      })
      load()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <>
      <header>
        <div>
          <p className="eyebrow">Scan results</p>
          <h1>{scan?.scan_name || 'Loading scan...'}</h1>
          <p>{scan && `${scan.total_records} records · ${scan.total_candidates} candidates · threshold ${scan.threshold} · ${scan.scan_mode}`}</p>
        </div>
        <LlmStatus />
        <div className="actions">
          <Link className="button secondary" to={`/scans/${id}/warnings`}>Warnings ({scan?.warnings_count ?? 0})</Link>
          <button type="button" className="secondary" onClick={() => api.download(exportTargets.exclusions.path, exportTargets.exclusions.filename)}>Rule exclusions ({scan?.rejections_count ?? 0})</button>
          <button type="button" onClick={() => api.download(exportTargets.candidates.path, exportTargets.candidates.filename)}>Export CSV</button>
          <button type="button" className="secondary" title="Does not call Groq. Exports only saved advisory or deterministic bypass status." onClick={() => api.download(exportTargets.exclusionsWithLlm.path, exportTargets.exclusionsWithLlm.filename)}>Rule exclusions with LLM status</button>
          <button type="button" title="Does not call Groq. Exports only saved advisory or deterministic bypass status." onClick={() => api.download(exportTargets.candidatesWithLlm.path, exportTargets.candidatesWithLlm.filename)}>Export CSV with saved LLM advisories</button>
        </div>
        <small className="export-note">Does not call Groq. Exports only saved advisory or deterministic bypass status.</small>
      </header>

      {error && <div className="error">{error}</div>}

      <TriagePanel
        value={triage}
        error={triageError}
        busy={triageBusy}
        start={() => triageAction(api.startLlmTriage)}
        retry={() => triageAction(api.retryFailedLlmTriage)}
      />

      <div className="assisted-filter">
        <label>Assisted status
          <select value={assistedFilter} onChange={event => setAssistedFilter(event.target.value)}>
            {EFFECTIVE_STATUS_OPTIONS.map(([value, label]) => <option value={value} key={value || 'all'}>{label}</option>)}
          </select>
        </label>
      </div>

      <div className="view-toggle">
        <button type="button" className={view === 'groups' ? '' : 'secondary'} onClick={() => setView('groups')}>
          Group View ({groups.length})
        </button>
        <button type="button" className={view === 'pairs' ? '' : 'secondary'} onClick={() => setView('pairs')}>
          Pair View ({visibleItems.length})
        </button>
      </div>

      <section className="panel table-wrap">
        {view === 'groups' ? (
          <GroupView groups={groups} openGroup={openGroup} setOpenGroup={setOpenGroup} />
        ) : (
          <PairTable
            items={visibleItems}
            open={open}
            setOpen={setOpen}
            comments={comments}
            setComments={setComments}
            review={review}
          />
        )}
      </section>
    </>
  )
}

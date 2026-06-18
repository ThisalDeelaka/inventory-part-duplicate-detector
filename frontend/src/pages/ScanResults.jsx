import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import Score from '../components/Score'

const STATUS_LABELS = {
  DUPLICATE_CANDIDATE: 'Duplicate Candidate',
  POSSIBLE_DUPLICATE_REVIEW: 'Possible Duplicate',
  DATA_CONFLICT_REVIEW: 'Data Conflict',
  CROSS_SITE_STANDARDIZATION_CANDIDATE: 'Cross-Site Candidate',
  INSUFFICIENT_DATA: 'Insufficient Data',
  RELATED_BUT_NOT_DUPLICATE: 'Related, Not Duplicate',
  UNIQUE_NO_MATCH: 'Unique / No Match',
  LIKELY_DUPLICATE: 'Duplicate Candidate',
}

function firstPresent(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== '')
}

function safeNumber(...values) {
  const value = firstPresent(...values)
  const number = Number(value)
  return Number.isFinite(number) ? number : 0
}

function parseJsonValue(value) {
  if (typeof value !== 'string') return value
  const trimmed = value.trim()
  if (!trimmed) return ''
  if (!['[', '{'].includes(trimmed[0])) return value
  try {
    return JSON.parse(trimmed)
  } catch {
    return value
  }
}

function asArray(value) {
  const parsed = parseJsonValue(value)
  if (Array.isArray(parsed)) return parsed.filter((item) => item !== undefined && item !== null && item !== '')
  if (parsed === undefined || parsed === null || parsed === '') return []
  return [parsed]
}

function displayValue(value) {
  const parsed = parseJsonValue(value)
  if (parsed === undefined || parsed === null || parsed === '') return '-'
  if (Array.isArray(parsed)) return parsed.length ? parsed.map(displayValue).join('; ') : '-'
  if (typeof parsed === 'object') return Object.keys(parsed).length ? JSON.stringify(parsed) : '-'
  return String(parsed)
}

function statusValue(candidate) {
  return firstPresent(candidate.business_status, candidate.recommended_action, candidate.review_status, 'POSSIBLE_DUPLICATE_REVIEW')
}

function statusLabel(status) {
  return STATUS_LABELS[status] || String(status).replaceAll('_', ' ')
}

function EvidenceList({ title, value }) {
  const items = asArray(value)
  return (
    <div className="evidence-block">
      <b>{title}</b>
      {items.length ? (
        <ul>
          {items.map((item, index) => <li key={`${title}-${index}`}>{displayValue(item)}</li>)}
        </ul>
      ) : (
        <span>-</span>
      )}
    </div>
  )
}

function EvidenceValue({ label, value }) {
  return (
    <span>
      <b>{label}:</b> {displayValue(value)}
    </span>
  )
}

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
        {items.map((candidate) => {
          const status = statusValue(candidate)
          const score = safeNumber(candidate.confidence_score, candidate.similarity_score, candidate.final_score, candidate.score)
          const explanation = firstPresent(candidate.explanation, candidate.reason, '-')
          const confidenceLevel = firstPresent(candidate.confidence_level, '-')

          return (
            <tr key={candidate.id}>
              <td><b>{displayValue(candidate.part_no_a)}</b><small>{displayValue(candidate.description_a)}</small></td>
              <td><b>{displayValue(candidate.part_no_b)}</b><small>{displayValue(candidate.description_b)}</small></td>
              <td><Score value={score} /><small>{confidenceLevel}</small></td>
              <td>
                <span className={`badge ${String(status).replaceAll(' ', '_')}`}>{statusLabel(status)}</span>
                <small>{confidenceLevel}</small>
              </td>
              <td>
                <span className="rule-pill">{displayValue(candidate.rule_decision)}</span>
                {candidate.rejection_reason && <small>{displayValue(candidate.rejection_reason)}</small>}
              </td>
              <td>
                <p>{explanation}</p>
                {!!asArray(candidate.critical_mismatches).length && (
                  <div className="mismatch-list">
                    {asArray(candidate.critical_mismatches).map((mismatch, index) => (
                      <span key={`${displayValue(mismatch.group)}-${index}`}>
                        {displayValue(mismatch.label || mismatch.type)}: {displayValue(mismatch.values_a)} vs {displayValue(mismatch.values_b)}
                      </span>
                    ))}
                  </div>
                )}
                {(candidate.generic_description_warning || candidate.application_context_warning) && (
                  <div className="mismatch-list">
                    {candidate.generic_description_warning && <span>One description is too generic to confirm duplicate identity.</span>}
                    {candidate.application_context_warning && (
                      <span>
                        Application context appears different: {displayValue(candidate.application_context_a)} vs {displayValue(candidate.application_context_b)}.
                      </span>
                    )}
                  </div>
                )}
                <button className="link" onClick={() => setOpen(open === candidate.id ? null : candidate.id)}>
                  {open === candidate.id ? 'Hide details' : 'Show details'}
                </button>
                {open === candidate.id && (
                  <div className="details evidence-details">
                    <EvidenceValue label="TF-IDF" value={candidate.tfidf_score} />
                    <EvidenceValue label="Fuzzy" value={candidate.fuzzy_score} />
                    <EvidenceValue label="Part no score" value={candidate.part_no_similarity} />
                    <EvidenceValue label="Technical score" value={candidate.technical_token_score} />
                    <EvidenceValue label="Scan mode" value={candidate.scan_mode} />
                    <EvidenceValue label="Normalized part no A" value={candidate.normalized_part_no_a} />
                    <EvidenceValue label="Normalized part no B" value={candidate.normalized_part_no_b} />
                    <EvidenceValue label="Normalized description A" value={candidate.normalized_description_a} />
                    <EvidenceValue label="Normalized description B" value={candidate.normalized_description_b} />
                    <EvidenceList title="Matched evidence" value={firstPresent(candidate.matched_evidence, candidate.matched_fields)} />
                    <EvidenceList title="Differences" value={firstPresent(candidate.differences, candidate.mismatched_fields)} />
                    <EvidenceList title="Warnings" value={candidate.warnings} />
                    <EvidenceValue label="Extracted attributes A" value={candidate.extracted_attributes_a} />
                    <EvidenceValue label="Extracted attributes B" value={candidate.extracted_attributes_b} />
                    <p>{displayValue(candidate.recommended_action)}</p>
                  </div>
                )}
              </td>
              <td>
                <span className="status">{displayValue(candidate.review_status)}</span>
                <textarea
                  placeholder="Reviewer comment"
                  value={comments[candidate.id] || ''}
                  onChange={(event) => setComments({ ...comments, [candidate.id]: event.target.value })}
                />
                <div className="review">
                  <button onClick={() => review(candidate, 'DUPLICATE')}>Duplicate</button>
                  <button className="secondary" onClick={() => review(candidate, 'NOT_DUPLICATE')}>Not duplicate</button>
                  <button className="ghost" onClick={() => review(candidate, 'UNSURE')}>Unsure</button>
                </div>
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
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
          <button className="link" onClick={() => setOpenGroup(openGroup === group.group_id ? null : group.group_id)}>
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
  const [scan, setScan] = useState(null)
  const [items, setItems] = useState([])
  const [groups, setGroups] = useState([])
  const [view, setView] = useState('groups')
  const [open, setOpen] = useState(null)
  const [openGroup, setOpenGroup] = useState(null)
  const [comments, setComments] = useState({})
  const [error, setError] = useState('')

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
        <div className="actions">
          <Link className="button secondary" to={`/scans/${id}/warnings`}>Warnings ({scan?.warnings_count ?? 0})</Link>
          <button onClick={() => api.download(`/api/scans/${id}/export`, `scan-${id}-candidates.csv`)}>Export CSV</button>
        </div>
      </header>

      {error && <div className="error">{error}</div>}

      <div className="view-toggle">
        <button className={view === 'groups' ? '' : 'secondary'} onClick={() => setView('groups')}>
          Group View ({groups.length})
        </button>
        <button className={view === 'pairs' ? '' : 'secondary'} onClick={() => setView('pairs')}>
          Pair View ({items.length})
        </button>
      </div>

      <section className="panel table-wrap">
        {view === 'groups' ? (
          <GroupView groups={groups} openGroup={openGroup} setOpenGroup={setOpenGroup} />
        ) : (
          <PairTable
            items={items}
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

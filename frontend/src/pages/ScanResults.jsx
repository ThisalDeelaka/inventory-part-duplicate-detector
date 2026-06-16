import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import Score from '../components/Score'

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
              <button className="link" onClick={() => setOpen(open === candidate.id ? null : candidate.id)}>
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
                  <p>{candidate.recommended_action}</p>
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
                <button onClick={() => review(candidate, 'DUPLICATE')}>Duplicate</button>
                <button className="secondary" onClick={() => review(candidate, 'NOT_DUPLICATE')}>Not duplicate</button>
                <button className="ghost" onClick={() => review(candidate, 'UNSURE')}>Unsure</button>
              </div>
            </td>
          </tr>
        ))}
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

import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import Score from '../components/Score'
import CandidateLlmTools from '../components/CandidateLlmTools'
import LlmStatus from '../components/LlmStatus'
import {
  AI_ENHANCEMENT_FILTERS,
  HYBRID_RETRIEVAL_METRIC_LABELS,
  effectiveStatusLabel,
  filterAndPrioritizeCandidates,
  retrievalChannelLabel,
  scanExportTargets,
  shouldPollTriage,
  triageFailureLabel,
  uomRelationshipLabel,
} from '../utils/llmUi'
import {
  diagnosticStatusLabel,
  edgeClassLabel,
  evidenceSourceLabel,
  groupSizeDistributionLabel,
  groupStatusLabel,
  hasCannotLink,
  mappingWarnings,
  reasonLabel,
} from '../utils/identityGroupUi'

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
                    <span>Candidate source: {candidate.candidate_source}</span>
                    <span>Resolution source: {candidate.resolution_source || 'Pending'}</span>
                    <span>Deterministic result: {candidate.business_status} / {candidate.confidence_level} / {candidate.similarity_score}</span>
                    <span>Semantic comparison: {candidate.semantic_profile_result || 'Not used'}</span>
                    <span>Pairwise LLM result: {candidate.pairwise_llm_result || 'Not used'}</span>
                    <span>Human review decision: {candidate.human_review_decision}</span>
                    {candidate.candidate_source === 'HYBRID_RETRIEVAL' && (
                      <>
                        <span>Retrieval tier: {candidate.retrieval_tier || 'Unavailable'}</span>
                        <span>Found by: {(candidate.retrieval_sources || []).map(retrievalChannelLabel).join(' / ') || 'Hybrid retrieval'}</span>
                        <span>Retrieval rank: {candidate.retrieval_rank ?? 'Unavailable'}</span>
                        <span>Retrieval priority: {candidate.retrieval_priority ?? candidate.retrieval_score ?? 'Unavailable'} (candidate-budget priority, not duplicate confidence)</span>
                        <span>Description specificity: {candidate.description_specificity_score ?? 'Unavailable'}</span>
                        <span>Generic penalty: {candidate.generic_description_penalty ?? 0}</span>
                        <span>Lexical: {candidate.lexical_score ?? 0} / Character vector: {candidate.vector_score ?? 0}</span>
                        <span>Reciprocal evidence: {(candidate.reciprocal_sources || []).map(retrievalChannelLabel).join(' / ') || 'None'}</span>
                        <span>Generic/conflict signals: {(candidate.retrieval_conflict_signals || []).join(' / ') || 'None'}</span>
                        <span>UOM relationship: {uomRelationshipLabel(candidate.uom_relationship)}</span>
                        <span>Mapping quality: {candidate.mapping_quality || 'Unavailable'}</span>
                        <span>UOM retrieval penalty: {candidate.uom_penalty == null ? 'Unavailable' : `${candidate.uom_penalty}%`}</span>
                        {candidate.uom_relationship && candidate.uom_relationship !== 'SAME_UOM' && (
                          <span>Possible mapping/unit inconsistency — identity still requires review.</span>
                        )}
                      </>
                    )}
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
          <h3>AI enhancement</h3>
          <div className="metrics">
            <span>Profiles cached: {value.semantic_profiles_cached || 0}</span>
            <span>Profiles generated: {value.semantic_profiles_generated || 0}</span>
            <span>Profiles failed: {value.semantic_profiles_failed || 0}</span>
            <span>Provider requests: {value.provider_request_count || 0}</span>
            <span>Resolved by semantic comparison: {value.locally_resolved_count || 0}</span>
            <span>Pairwise fallback: {value.pairwise_fallback_count || 0}</span>
            <span>Recall-rescue pairs considered: {value.rescue_pool_considered_count || 0}</span>
            <span>Recall-rescue candidates added: {value.rescue_candidate_count || 0}</span>
            <span>Recall likely duplicate: {value.rescue_likely_duplicate_count || 0}</span>
            <span>Recall human review: {value.rescue_human_review_count || 0}</span>
            <span>Recall failed: {value.rescue_failed_count || 0}</span>
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

function RetrievalPanel({ value }) {
  if (!value) return null
  const exclusionReasons = value.hybrid_post_scoring_exclusion_reasons || {}
  const historicalUomMetrics = value.uom_convertible_pairs_considered == null
    || value.uom_different_basis_pairs_considered == null
  const uomDifferences = historicalUomMetrics
    ? 'Unavailable for historical scan'
    : value.uom_convertible_pairs_considered + value.uom_different_basis_pairs_considered
  const uomUnknown = value.uom_missing_or_wildcard_pairs_considered == null
    || value.uom_malformed_or_unknown_pairs_considered == null
    ? 'Unavailable for historical scan'
    : value.uom_missing_or_wildcard_pairs_considered + value.uom_malformed_or_unknown_pairs_considered
  return (
    <section className="panel triage-panel" aria-label="Candidate retrieval metrics">
      <div className="llm-heading"><div><p className="eyebrow">Deterministic-first recall</p><h2>Candidate retrieval</h2></div></div>
      <div className="metrics">
        <span>Records indexed: {value.records_indexed || 0}</span>
        <span>Standard deterministic: preserved</span>
        <span>{HYBRID_RETRIEVAL_METRIC_LABELS.selected}: {value.hybrid_retrieval_selected_count || 0}</span>
        <span>{HYBRID_RETRIEVAL_METRIC_LABELS.tierA}: {value.hybrid_retrieval_selected_tier_a ?? value.tier_a_candidates ?? 0}</span>
        <span>{HYBRID_RETRIEVAL_METRIC_LABELS.tierB}: {value.hybrid_retrieval_selected_tier_b ?? value.tier_b_candidates ?? 0}</span>
        <span>{HYBRID_RETRIEVAL_METRIC_LABELS.tierC}: {value.hybrid_retrieval_selected_tier_c ?? value.tier_c_candidates ?? 0}</span>
        <span>{HYBRID_RETRIEVAL_METRIC_LABELS.postScoringExcluded}: {value.hybrid_post_scoring_excluded_count ?? 'Unavailable for historical scan'}</span>
        <span>{HYBRID_RETRIEVAL_METRIC_LABELS.added}: {value.hybrid_candidates_added || 0}</span>
        <span>Exact-description candidates: {value.exact_description_candidates || 0}</span>
        <span>Part-family candidates: {value.part_family_candidates || 0}</span>
        <span>Lexical candidates: {value.lexical_candidates_generated || 0}</span>
        <span>Character-vector candidates: {value.char_vector_candidates_generated || value.vector_candidates_generated || 0}</span>
        <span>Technical-identity candidates: {value.technical_identity_candidates || 0}</span>
        <span>Reciprocal candidates: {value.reciprocal_candidates || 0}</span>
        <span>Generic-penalized: {value.generic_penalized_candidates || 0}</span>
        <span>Conflict-penalized: {value.conflict_penalized_candidates || 0}</span>
        <span>{HYBRID_RETRIEVAL_METRIC_LABELS.uomDifferences}: {uomDifferences}</span>
        <span>{HYBRID_RETRIEVAL_METRIC_LABELS.uomConvertible}: {value.uom_convertible_pairs_considered ?? 'Unavailable for historical scan'}</span>
        <span>{HYBRID_RETRIEVAL_METRIC_LABELS.uomDifferentBasis}: {value.uom_different_basis_pairs_considered ?? 'Unavailable for historical scan'}</span>
        <span>{HYBRID_RETRIEVAL_METRIC_LABELS.uomUnknown}: {uomUnknown}</span>
        <span>Hybrid candidates added with UOM difference: {value.hybrid_candidates_added_with_uom_difference ?? 'Unavailable for historical scan'}</span>
        <span>Hybrid candidates added with unknown UOM: {value.hybrid_candidates_added_with_uom_unknown ?? 'Unavailable for historical scan'}</span>
        <span>Multi-source candidates: {value.multi_source_candidates || 0}</span>
        <span>{HYBRID_RETRIEVAL_METRIC_LABELS.skippedByBudget}: {value.hybrid_candidates_skipped_by_budget ?? value.hybrid_candidates_skipped_by_cap ?? 0}</span>
        <span>Average candidates per record: {value.average_candidates_per_record || 0}</span>
        <span>Largest description-family candidates: {value.largest_description_family_candidates || 0}</span>
      </div>
      {!!Object.keys(exclusionReasons).length && (
        <div className="mismatch-list" aria-label="Post-retrieval exclusion reasons">
          {Object.entries(exclusionReasons).map(([reason, count]) => (
            <span key={reason}>{reason.toLowerCase().replaceAll('_', ' ')}: {count}</span>
          ))}
        </div>
      )}
      <small>Retrieval priority allocates comparison budget; it is not duplicate confidence.</small>
    </section>
  )
}

function UomSummary({ value }) {
  const warnings = mappingWarnings(value)
  return (
    <section className="mapping-summary" aria-label="Mapping and UOM observations">
      <h3>Mapping / UOM observations</h3>
      <div className="metrics">
        <span>Distinct UOMs: {(value?.distinct_uoms || []).join(', ') || 'None recorded'}</span>
        <span>Different basis: {value?.different_basis_pair_count || 0}</span>
        <span>Unknown / wildcard: {(value?.missing_or_wildcard_pair_count || 0) + (value?.malformed_or_unknown_pair_count || 0)}</span>
        <span>Possible mapping errors: {value?.possible_mapping_error_count || 0}</span>
      </div>
      {!!warnings.length && <p className="warning"><b>Mapping:</b> {warnings.join(' · ')}</p>}
      <small>Mapping observations do not replace or reinterpret the identity-group status.</small>
    </section>
  )
}

function MemberTable({ members }) {
  return (
    <div className="table-wrap mini group-members">
      <table>
        <thead><tr><th>#</th><th>Site / Contract</th><th>Part No.</th><th>Description</th><th>UOM</th><th>Product category</th><th>HSN/SAC</th></tr></thead>
        <tbody>{members.map(member => (
          <tr key={member.record_ref_key}>
            <td>{member.member_index + 1}</td><td>{member.contract || '—'}</td>
            <td><b>{member.part_no}</b></td><td>{member.description}</td><td>{member.uom || '—'}</td>
            <td>{member.product_category_id || '—'}</td><td>{member.hsn_sac_code || '—'}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  )
}

function EdgeEvidence({ edges, diagnostic = false }) {
  if (!edges.length) return <p className="empty">No bounded internal-edge evidence was persisted.</p>
  return (
    <div className="pair-evidence">
      {edges.map((edge, index) => (
        <article className={edge.edge_class === 'CANNOT_LINK' ? 'error' : 'evidence-row'} key={`${edge.left_record_ref_key}-${edge.right_record_ref_key}-${index}`}>
          <b>{edgeClassLabel(edge.edge_class)}</b>
          <span>{evidenceSourceLabel(edge.evidence_source)}</span>
          <small>{edge.left_record_ref_key.slice(0, 10)}… ↔ {edge.right_record_ref_key.slice(0, 10)}…</small>
          {!!edge.reason_codes?.length && <p>{edge.reason_codes.map(reasonLabel).join(' · ')}</p>}
          {diagnostic && edge.edge_class === 'CANNOT_LINK' && <small>This relationship prevents acceptance as a duplicate group.</small>}
        </article>
      ))}
    </div>
  )
}

function GroupDetail({ detail }) {
  if (hasCannotLink(detail)) return <div className="error" role="alert"><b>Snapshot inconsistency:</b> this accepted group contains cannot-link evidence and cannot be presented as safe.</div>
  return (
    <div className="group-detail">
      <section><h3>Identity evidence</h3><MemberTable members={detail.members || []} /></section>
      <UomSummary value={detail.uom_summary} />
      <section><h3>Internal pair evidence</h3><EdgeEvidence edges={detail.internal_edges || []} /></section>
    </div>
  )
}

function IdentityGroupView({ snapshotAvailable, result, detailById, detailLoading, detailError, toggleDetail }) {
  if (snapshotAvailable === false) return <div className="empty no-snapshot"><b>No identity-group snapshot is available for this scan.</b><span>Pair diagnostics are still available.</span></div>
  if (!result) return <p className="empty">Loading identity groups…</p>
  if (!result.items.length) return <p className="empty">This valid identity snapshot contains no accepted groups.</p>
  return <div className="groups">{result.items.map(group => {
    const detail = detailById[group.group_snapshot_id]
    const expanded = detailLoading === group.group_snapshot_id || Boolean(detail) || detailError?.id === group.group_snapshot_id
    const warnings = mappingWarnings(group.uom_summary)
    return <article className="group-card" key={group.group_snapshot_id}>
      <div className="group-head"><div><p className="eyebrow">Potential duplicate group</p><h2>{groupStatusLabel(group.group_status)}</h2><small>{group.group_size} records · {group.internal_pair_count} checked internal relationships</small></div><span className={`badge group-status ${group.group_status}`}>{groupStatusLabel(group.group_status)}</span></div>
      <div className="member-preview" aria-label={`${group.group_size}-record group preview`}><span>Whole group contains {group.group_size} records. Open to view every member together.</span></div>
      {!!group.reason_codes?.length && <p><b>Evidence:</b> {group.reason_codes.slice(0, 4).map(reasonLabel).join(' · ')}</p>}
      {!!warnings.length && <p className="warning"><b>Mapping:</b> {warnings.join(' · ')}</p>}
      <button type="button" className="link" aria-expanded={expanded} aria-controls={`group-${group.group_snapshot_id}`} onClick={() => toggleDetail(group.group_snapshot_id, expanded)}>{expanded ? 'Close group details' : `Open all ${group.group_size} members and evidence`}</button>
      {expanded && <div id={`group-${group.group_snapshot_id}`}>{detailLoading === group.group_snapshot_id && <p>Loading group detail…</p>}{detailError?.id === group.group_snapshot_id && <p className="error" role="alert">{detailError.message}</p>}{detail && <GroupDetail detail={detail} />}</div>}
    </article>
  })}</div>
}

function DiagnosticView({ result, detailById, detailLoading, detailError, toggleDetail }) {
  if (!result) return <p className="empty">Loading conflicting candidate families…</p>
  if (!result.items.length) return <p className="empty">No conflicting or deferred candidate families exist in this snapshot.</p>
  return <div className="groups">{result.items.map(item => {
    const detail = detailById[item.diagnostic_snapshot_id]
    const expanded = detailLoading === item.diagnostic_snapshot_id || Boolean(detail) || detailError?.id === item.diagnostic_snapshot_id
    return <article className="group-card diagnostic-card" key={item.diagnostic_snapshot_id}>
      <div className="group-head"><div><p className="eyebrow">Not an accepted duplicate group</p><h2>{diagnosticStatusLabel(item.diagnostic_status)}</h2><small>{item.member_count} records · {item.cannot_link_count} cannot-link conflict(s)</small></div></div>
      <p>{item.reason_codes.map(reasonLabel).join(' · ')}</p>
      <button type="button" className="link" aria-expanded={expanded} aria-controls={`diagnostic-${item.diagnostic_snapshot_id}`} onClick={() => toggleDetail(item.diagnostic_snapshot_id, expanded)}>{expanded ? 'Close family details' : `Open all ${item.member_count} members and conflicts`}</button>
      {expanded && <div id={`diagnostic-${item.diagnostic_snapshot_id}`}>{detailLoading === item.diagnostic_snapshot_id && <p>Loading family detail…</p>}{detailError?.id === item.diagnostic_snapshot_id && <p className="error">{detailError.message}</p>}{detail && <><MemberTable members={detail.members || []} /><h3>Cannot-link evidence</h3><EdgeEvidence edges={detail.conflict_edges || []} diagnostic /></>}</div>}
    </article>
  })}</div>
}

export default function ScanResults() {
  const { id } = useParams()
  const exportTargets = scanExportTargets(id)
  const [scan, setScan] = useState(null)
  const [items, setItems] = useState([])
  const [view, setView] = useState('groups')
  const [open, setOpen] = useState(null)
  const [comments, setComments] = useState({})
  const [error, setError] = useState('')
  const [summary, setSummary] = useState(null)
  const [summaryError, setSummaryError] = useState('')
  const [groupResult, setGroupResult] = useState(null)
  const [groupError, setGroupError] = useState('')
  const [groupDetails, setGroupDetails] = useState({})
  const [groupDetailLoading, setGroupDetailLoading] = useState(null)
  const [groupDetailError, setGroupDetailError] = useState(null)
  const [diagnosticResult, setDiagnosticResult] = useState(null)
  const [diagnosticDetails, setDiagnosticDetails] = useState({})
  const [diagnosticLoading, setDiagnosticLoading] = useState(null)
  const [diagnosticError, setDiagnosticError] = useState(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [minimumSize, setMinimumSize] = useState('')
  const [maximumSize, setMaximumSize] = useState('')
  const [groupPage, setGroupPage] = useState(0)
  const [pairLoaded, setPairLoaded] = useState(false)
  const [triage, setTriage] = useState(null)
  const [triageError, setTriageError] = useState('')
  const [triageBusy, setTriageBusy] = useState(false)
  const [assistedFilter, setAssistedFilter] = useState('')

  const pageLimit = 25
  const groupOptions = {
    status: statusFilter || undefined,
    minimumGroupSize: Number(minimumSize) || undefined,
    maximumGroupSize: Number(maximumSize) || undefined,
    limit: pageLimit,
    offset: groupPage * pageLimit,
  }

  useEffect(() => {
    setSummary(null); setGroupResult(null); setGroupDetails({}); setDiagnosticResult(null)
    setDiagnosticDetails({}); setItems([]); setPairLoaded(false); setView('groups'); setGroupPage(0)
    setError(''); setSummaryError(''); setGroupError(''); setDiagnosticError(null)
  }, [id])

  const load = () => {
    api.get(`/api/scans/${id}`).then(setScan).catch(requestError => setError(requestError.message))
    api.getIdentityGroupSummary(id).then(response => { setSummary(response); setSummaryError('') }).catch(requestError => setSummaryError(requestError.message))
  }

  useEffect(() => { load() }, [id])
  useEffect(() => {
    setGroupResult(null); setGroupError('')
    api.getIdentityGroups(id, groupOptions).then(setGroupResult).catch(requestError => setGroupError(requestError.message))
  }, [id, statusFilter, minimumSize, maximumSize, groupPage])

  useEffect(() => {
    if (view !== 'conflicts' || diagnosticResult) return
    api.getIdentityDiagnostics(id, { limit: 100 }).then(setDiagnosticResult).catch(requestError => setDiagnosticError({ id: null, message: requestError.message }))
  }, [id, view, diagnosticResult])

  useEffect(() => {
    if (view !== 'pairs' || pairLoaded) return
    api.get(`/api/scans/${id}/candidates`).then(response => { setItems(response); setPairLoaded(true) }).catch(requestError => setError(requestError.message))
  }, [id, view, pairLoaded])

  const loadTriage = async () => {
    try {
      const response = await api.getLlmTriageStatus(id)
      setTriage(response)
      setTriageError('')
      if (!shouldPollTriage(response.state)) {
        if (pairLoaded) {
          const candidates = await api.get(`/api/scans/${id}/candidates`)
          setItems(candidates)
        }
      }
      return response
    } catch (requestError) {
      if (requestError.status === 404) setTriage(null)
      else setTriageError(requestError.message)
      return null
    }
  }

  useEffect(() => { if (view === 'pairs') loadTriage() }, [id, view])
  useEffect(() => {
    if (view !== 'pairs' || !shouldPollTriage(triage?.state)) return undefined
    const timer = window.setInterval(loadTriage, 3000)
    return () => window.clearInterval(timer)
  }, [id, view, triage?.state, pairLoaded])

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
      const candidates = await api.get(`/api/scans/${id}/candidates`)
      setItems(candidates)
    } catch (err) {
      setError(err.message)
    }
  }

  const toggleGroupDetail = async (groupId, expanded) => {
    if (expanded) { setGroupDetails(previous => { const next = { ...previous }; delete next[groupId]; return next }); setGroupDetailError(null); return }
    setGroupDetailLoading(groupId); setGroupDetailError(null)
    try { const detail = await api.getIdentityGroupDetail(id, groupId); setGroupDetails(previous => ({ ...previous, [groupId]: detail })) }
    catch (requestError) { setGroupDetailError({ id: groupId, message: requestError.message }) }
    finally { setGroupDetailLoading(null) }
  }

  const toggleDiagnosticDetail = async (diagnosticId, expanded) => {
    if (expanded) { setDiagnosticDetails(previous => { const next = { ...previous }; delete next[diagnosticId]; return next }); setDiagnosticError(null); return }
    setDiagnosticLoading(diagnosticId); setDiagnosticError(null)
    try { const detail = await api.getIdentityDiagnosticDetail(id, diagnosticId); setDiagnosticDetails(previous => ({ ...previous, [diagnosticId]: detail })) }
    catch (requestError) { setDiagnosticError({ id: diagnosticId, message: requestError.message }) }
    finally { setDiagnosticLoading(null) }
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

      <RetrievalPanel value={scan?.hybrid_retrieval} />

      <section className="panel identity-summary" aria-labelledby="identity-summary-heading">
        <div className="group-head">
          <div><p className="eyebrow">Identity group summary</p><h2 id="identity-summary-heading">Potential duplicate groups</h2></div>
          {summary?.selected_projection && <div className="snapshot-meta"><b>Identity projection</b><span>Algorithm: {summary.selected_projection.algorithm_version}</span><span>Snapshot: {new Date(summary.selected_projection.created_at).toLocaleString()}</span></div>}
        </div>
        {summaryError ? <p className="error" role="alert">Identity-group summary could not be loaded: {summaryError}</p> : !summary ? <p>Loading identity-group summary…</p> : summary.snapshot_available ? <>
          <div className="cards compact-cards">
            <article><label>Accepted groups</label><strong>{summary.accepted_groups}</strong><small>Scan-time hypotheses, not confirmed duplicates</small></article>
            <article><label>Likely duplicate groups</label><strong>{summary.likely_groups}</strong></article>
            <article><label>Possible groups — review</label><strong>{summary.review_groups}</strong></article>
            <article><label>Conflicting candidate families</label><strong>{summary.conflicting_families}</strong></article>
            <article><label>Largest group</label><strong>{summary.largest_accepted_group}</strong></article>
          </div>
          <p className="distribution"><b>Group sizes:</b> {groupSizeDistributionLabel(summary.group_size_distribution)}</p>
        </> : <div className="no-snapshot"><b>No identity-group snapshot is available for this scan.</b><span>Pair diagnostics are still available.</span></div>}
      </section>

      <div className="view-toggle" role="tablist" aria-label="Scan result views">
        <button type="button" role="tab" aria-selected={view === 'groups'} className={view === 'groups' ? '' : 'secondary'} onClick={() => setView('groups')}>
          Groups ({summary?.accepted_groups ?? '…'})
        </button>
        <button type="button" role="tab" aria-selected={view === 'conflicts'} className={view === 'conflicts' ? '' : 'secondary'} onClick={() => setView('conflicts')}>
          Conflicting families ({summary?.diagnostic_families ?? '…'})
        </button>
        <button type="button" role="tab" aria-selected={view === 'pairs'} className={view === 'pairs' ? '' : 'secondary'} onClick={() => setView('pairs')}>
          Pair diagnostics {pairLoaded ? `(${visibleItems.length})` : ''}
        </button>
      </div>

      {view === 'groups' && <>
        <section className="panel group-filters" aria-label="Identity group filters">
          <label>Status<select value={statusFilter} onChange={event => { setStatusFilter(event.target.value); setGroupPage(0) }}><option value="">All accepted statuses</option><option value="LIKELY_DUPLICATE_GROUP">Likely duplicate group</option><option value="POSSIBLE_DUPLICATE_GROUP_REVIEW">Possible duplicate group — review</option></select></label>
          <label>Minimum group size<input type="number" min="2" value={minimumSize} onChange={event => { setMinimumSize(event.target.value); setGroupPage(0) }} /></label>
          <label>Maximum group size<input type="number" min="2" value={maximumSize} onChange={event => { setMaximumSize(event.target.value); setGroupPage(0) }} /></label>
        </section>
        {groupError && <p className="error" role="alert">Identity groups could not be loaded: {groupError}</p>}
        <section className="panel" role="tabpanel" aria-label="Accepted identity groups">
          {!groupError && <IdentityGroupView snapshotAvailable={summary?.snapshot_available} result={groupResult} detailById={groupDetails} detailLoading={groupDetailLoading} detailError={groupDetailError} toggleDetail={toggleGroupDetail} />}
          {groupResult?.total > pageLimit && <nav className="pagination" aria-label="Identity group pages"><button type="button" className="secondary" disabled={groupPage === 0} onClick={() => setGroupPage(page => page - 1)}>Previous</button><span>Page {groupPage + 1} of {Math.ceil(groupResult.total / pageLimit)}</span><button type="button" className="secondary" disabled={(groupPage + 1) * pageLimit >= groupResult.total} onClick={() => setGroupPage(page => page + 1)}>Next</button></nav>}
        </section>
      </>}

      {view === 'conflicts' && <section className="panel" role="tabpanel" aria-label="Conflicting candidate families">{diagnosticError?.id == null && diagnosticError ? <p className="error" role="alert">Diagnostics could not be loaded: {diagnosticError.message}</p> : <DiagnosticView result={diagnosticResult} detailById={diagnosticDetails} detailLoading={diagnosticLoading} detailError={diagnosticError} toggleDetail={toggleDiagnosticDetail} />}</section>}

      {view === 'pairs' && <>
        <TriagePanel value={triage} error={triageError} busy={triageBusy} start={() => triageAction(api.startLlmTriage)} retry={() => triageAction(api.retryFailedLlmTriage)} />
        <div className="assisted-filter"><label>AI enhancement<select value={assistedFilter} onChange={event => setAssistedFilter(event.target.value)}>{AI_ENHANCEMENT_FILTERS.map(([value, label]) => <option value={value} key={value || 'all'}>{label}</option>)}</select></label></div>
        <section className="panel table-wrap" role="tabpanel" aria-label="Pair diagnostics">
          {!pairLoaded ? <p className="empty">Loading pair diagnostics…</p> :
          <PairTable
            items={visibleItems}
            open={open}
            setOpen={setOpen}
            comments={comments}
            setComments={setComments}
            review={review}
          />}
        </section>
      </>}
    </>
  )
}

import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { api } from '../api/client'
import ExportAuthorityPanel from '../components/ExportAuthorityPanel'
import GroupReviewPanel from '../components/GroupReviewPanel'
import LlmStatus from '../components/LlmStatus'
import SystemExplanation from '../components/SystemExplanation'
import {
  groupStatusLabel,
  identityReadErrorState,
  identityReadExportTargets,
  validationCoverageLabel,
  validationModeLabel,
} from '../utils/identityGroupUi'
import { groupReviewLabel } from '../utils/identityGroupReviewUi'
import {
  exportFailureFeedback,
  exportSuccessFeedback,
  summarizeReviewedExportAvailability,
} from '../utils/identityExportUi'
import { scanStatusLabel } from '../utils/productJourneyUi'

const memberReference = member => member.stable_record_reference || member.record_ref_key

function MemberTable({ members }) {
  return <div className="table-wrap mini group-members"><table>
    <thead><tr><th>#</th><th>Site / Contract</th><th>Part No.</th><th>Description</th><th>UOM</th><th>Product category</th><th>HSN/SAC</th></tr></thead>
    <tbody>{members.map(member => <tr key={memberReference(member)}>
      <td>{(member.member_order ?? member.member_index) + 1}</td>
      <td>{member.contract || '—'}</td><td><b>{member.part_no}</b></td>
      <td>{member.description}</td><td>{member.uom || '—'}</td>
      <td>{member.product_category_id || '—'}</td><td>{member.hsn_sac_code || '—'}</td>
    </tr>)}</tbody>
  </table></div>
}

function EvidenceSummary({ detail }) {
  const coverage = detail.validation_coverage || {}
  const evidence = detail.internal_evidence || []
  return <section aria-label="Validation coverage and evidence">
    <h3>Validation coverage</h3>
    <p><b>{validationModeLabel(detail.validation_mode)}</b></p>
    <p>{validationCoverageLabel(coverage)}</p>
    <div className="metrics">
      <span>Strong support: {coverage.strong_support_count || 0}</span>
      <span>Review support: {coverage.review_support_count || 0}</span>
      <span>Neutral: {coverage.non_groupable_count || 0}</span>
      <span>Required evidence: {coverage.required_validation_evidence_count || 0}</span>
    </div>
    <details><summary>Advanced relationship evidence ({evidence.length} evaluated)</summary>
      {!evidence.length ? <p className="empty">No evaluated relationship evidence is present.</p> :
        <pre className="evidence-json">{JSON.stringify(evidence, null, 2)}</pre>}
    </details>
    {detail.validation_mode === 'PROGRESSIVE_TARGETED' &&
      <small>Only actual evaluated evidence is shown. Missing non-required relationships are not synthesized.</small>}
  </section>
}

function AdvisoryEligibility({ scanId, detail }) {
  const [state, setState] = useState({ loading: true })
  useEffect(() => {
    let active = true
    api.getVersionedGroupAdvisoryEligibility(scanId, detail.versioned_group_key)
      .then(value => active && setState({ value }))
      .catch(error => active && setState({ error: error.message }))
    return () => { active = false }
  }, [scanId, detail.versioned_group_key])
  if (state.loading) return <p>Checking advisory eligibility…</p>
  if (state.error) return <p className="error">Advisory eligibility could not be loaded: {state.error}</p>
  const eligibility = state.value
  const reason = eligibility.reason_code === 'INELIGIBLE_PROGRESSIVE_VALIDATION_NOT_SUPPORTED'
    ? 'progressive validation is not supported for advisory yet'
    : eligibility.details?.join(' · ') || eligibility.reason_code.toLowerCase().replaceAll('_', ' ')
  return <section aria-label="AI advisory eligibility"><h3>Optional AI advisory</h3>
    {eligibility.eligible
      ? <p className="banner">Eligible for a projection-scoped group advisory. No provider call is made from this page.</p>
      : <p className="warning">AI advisory unavailable: {reason}</p>}
  </section>
}

function GroupDetail({ scanId, detail, onReviewSaved }) {
  return <div className="group-detail">
    <section><h3>All identity-set members</h3>
      <p><b>Projection-safe identity:</b> <code>{detail.versioned_group_key}</code></p>
      <MemberTable members={detail.members || []} />
    </section>
    <SystemExplanation explanation={detail.system_explanation} />
    <EvidenceSummary detail={detail} />
    <GroupReviewPanel scanId={scanId} detail={detail} onSaved={onReviewSaved} />
    <AdvisoryEligibility scanId={scanId} detail={detail} />
  </div>
}

function IdentityGroups({ scanId, result, detailByKey, loadingKey, detailError, toggleDetail, onReviewSaved }) {
  if (!result) return <p className="empty">Loading authoritative identity groups…</p>
  if (!result.items.length) return <p className="empty">This ready authoritative snapshot contains zero potential duplicate groups.</p>
  return <div className="groups">{result.items.map(group => {
    const key = group.versioned_group_key
    const detail = detailByKey[key]
    const expanded = loadingKey === key || Boolean(detail) || detailError?.id === key
    return <article className="group-card" key={key}>
      <div className="group-head"><div><p className="eyebrow">Potential duplicate identity</p>
        <h2>{groupStatusLabel(group.group_status)}</h2>
        <small>{group.group_size} records · {validationCoverageLabel(group.validation_coverage)}</small>
      </div><span className={`badge group-status ${group.group_status}`}>{groupStatusLabel(group.group_status)}</span></div>
      <p><b>Validation:</b> {validationModeLabel(group.validation_mode)}</p>
      <SystemExplanation explanation={group.system_explanation} compact />
      <p><b>Human review:</b> {groupReviewLabel(group.review_state)}</p>
      <div className="member-preview" aria-label={`${group.group_size}-record identity-set preview`}>
        {(group.member_preview || []).map(member => <span key={member.stable_record_reference}><b>{member.part_no}</b> — {member.description}<small>{member.contract || 'No site / contract'} · {member.uom || 'No UOM'}</small></span>)}
        {group.group_size > (group.member_preview || []).length && <span>+ {group.group_size - group.member_preview.length} more member(s)</span>}
      </div>
      <p>This result is one 2..N member identity hypothesis, not a collection of A/B decisions.</p>
      <button type="button" className="link" aria-expanded={expanded} onClick={() => toggleDetail(key, expanded)}>
        {expanded ? 'Close identity-set details' : `Open all ${group.group_size} members`}
      </button>
      {expanded && <div>{loadingKey === key && <p>Loading identity-set detail…</p>}
        {detailError?.id === key && <p className="error" role="alert">{detailError.message}</p>}
        {detail && <GroupDetail scanId={scanId} detail={detail} onReviewSaved={onReviewSaved} />}
      </div>}
    </article>
  })}</div>
}

function OutcomeView({ outcomes }) {
  if (!outcomes) return <p className="empty">Loading identity outcomes…</p>
  const conflicts = outcomes.conflicts || []
  const deferred = outcomes.deferred_work_units || []
  const unassigned = outcomes.unassigned_records || []
  return <div className="outcome-sections">
    <section><h2>Identity conflicts ({conflicts.length})</h2>
      {!conflicts.length ? <p className="empty">No authoritative conflicts.</p> : conflicts.map(item =>
        <article className="group-card diagnostic-card" key={item.conflict_reference}><SystemExplanation explanation={item.system_explanation} heading="Why the system kept these records separate" /><small>{item.involved_record_references.length} affected records</small></article>)}
    </section>
    <section><h2>Deferred / unresolved work ({deferred.length})</h2>
      {!deferred.length ? <p className="empty">No deferred identity work.</p> : deferred.map(item =>
        <article className="group-card" key={item.deferred_reference}><SystemExplanation explanation={item.system_explanation} heading="Why this identity work is deferred" /><small>{item.record_references.length} records remain unresolved; this is not a unique, rejected, or conflicting classification.</small></article>)}
    </section>
    <section><h2>Not safely assigned ({unassigned.length})</h2><p>These records were not safely assigned to an accepted identity set. They are not confirmed unique.</p></section>
  </div>
}

function PairDiagnostics({ scanId, onClose }) {
  const [state, setState] = useState({ loading: true })
  useEffect(() => {
    let active = true
    api.get(`/api/scans/${scanId}/candidates`)
      .then(items => active && setState({ items }))
      .catch(error => active && setState({
        error: error.message,
        notApplicable: error.category === 'PAIR_DIAGNOSTICS_NOT_APPLICABLE',
      }))
    return () => { active = false }
  }, [scanId])
  return <>
    <section className="panel advanced-warning"><h2>Advanced legacy pair diagnostics</h2>
      <p>Pair evidence is retained for compatibility and audit. It is not the business result, review unit, or export unit.</p>
      <button type="button" className="secondary" onClick={onClose}>Return to identity groups</button>
    </section>
    <section className="panel table-wrap" aria-label="Advanced legacy pair diagnostics">
      {state.loading ? <p>Loading pair diagnostics…</p> : state.notApplicable ?
        <p className="empty">Legacy pair diagnostics were not generated because they are not applicable to this group-first scan.</p> :
        state.error ? <p className="error">{state.error}</p> :
        !state.items.length ? <p className="empty">No legacy pair diagnostics.</p> : <table>
          <thead><tr><th>Diagnostic pair</th><th>Status</th><th>Explanation</th></tr></thead>
          <tbody>{state.items.map(item => <tr key={item.id}><td>{item.part_no_a} / {item.part_no_b}</td><td>{item.business_status}</td><td>{item.explanation}</td></tr>)}</tbody>
        </table>}
    </section>
  </>
}

function ScanUnavailable() {
  return <section className="panel unavailable-result" role="alert">
    <p className="eyebrow">Result unavailable</p><h1>Scan not available</h1>
    <p>This scan ID does not identify a result that can be opened. It was not replaced with another scan.</p>
    <div className="actions">
      <Link className="button" to="/">Return to Dashboard</Link>
      <Link className="button secondary" to="/">View recent scans</Link>
      <Link className="button secondary" to="/new-scan">Start a new scan</Link>
    </div>
  </section>
}

export default function ScanResults() {
  const { id } = useParams()
  const parsedId = Number(id)
  if (!Number.isInteger(parsedId) || parsedId <= 0) return <ScanUnavailable />
  return <ValidScanResults id={String(parsedId)} />
}

function ValidScanResults({ id }) {
  const exports = useMemo(() => identityReadExportTargets(id), [id])
  const [scan, setScan] = useState(null)
  const [scanError, setScanError] = useState(false)
  const [summary, setSummary] = useState(null)
  const [summaryError, setSummaryError] = useState(null)
  const [groupResult, setGroupResult] = useState(null)
  const [groupError, setGroupError] = useState(null)
  const [outcomes, setOutcomes] = useState(null)
  const [view, setView] = useState('groups')
  const [details, setDetails] = useState({})
  const [detailLoading, setDetailLoading] = useState(null)
  const [detailError, setDetailError] = useState(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [minimumSize, setMinimumSize] = useState('')
  const [maximumSize, setMaximumSize] = useState('')
  const [page, setPage] = useState(0)
  const [reviewedExportState, setReviewedExportState] = useState({ status: 'loading' })
  const [exportBusyKind, setExportBusyKind] = useState('')
  const [exportFeedback, setExportFeedback] = useState(null)
  const pageLimit = 25

  const refreshReviewedExportState = useCallback(async () => {
    setReviewedExportState({ status: 'loading' })
    try {
      const items = []
      let offset = 0
      let total = 0
      do {
        const result = await api.getIdentityReadGroups(id, { limit: 100, offset })
        total = result.total
        items.push(...result.items)
        offset += result.items.length
        if (!result.items.length) break
      } while (offset < total)
      const state = summarizeReviewedExportAvailability(items, total)
      setReviewedExportState(state)
      return state
    } catch {
      const state = { status: 'error' }
      setReviewedExportState(state)
      return state
    }
  }, [id])

  useEffect(() => {
    setScan(null); setScanError(false); setSummary(null); setSummaryError(null); setGroupResult(null)
    setGroupError(null); setOutcomes(null); setDetails({}); setView('groups'); setPage(0)
    api.get(`/api/scans/${id}`).then(setScan).catch(() => setScanError(true))
    api.getIdentityReadSummary(id).then(setSummary).catch(error => setSummaryError(identityReadErrorState(error.status, error.message)))
  }, [id])

  useEffect(() => { refreshReviewedExportState() }, [refreshReviewedExportState])

  useEffect(() => {
    setGroupResult(null); setGroupError(null)
    api.getIdentityReadGroups(id, {
      status: statusFilter || undefined,
      minimumGroupSize: Number(minimumSize) || undefined,
      maximumGroupSize: Number(maximumSize) || undefined,
      limit: pageLimit,
      offset: page * pageLimit,
    }).then(setGroupResult).catch(error => setGroupError(identityReadErrorState(error.status, error.message)))
  }, [id, statusFilter, minimumSize, maximumSize, page])

  useEffect(() => {
    if (view !== 'outcomes' || outcomes) return
    api.getIdentityReadOutcomes(id).then(setOutcomes).catch(error => setGroupError(identityReadErrorState(error.status, error.message)))
  }, [id, view, outcomes])

  const toggleDetail = async (key, expanded) => {
    if (expanded) {
      setDetails(previous => { const next = { ...previous }; delete next[key]; return next })
      setDetailError(null)
      return
    }
    setDetailLoading(key); setDetailError(null)
    try {
      const detail = await api.getIdentityReadGroupDetail(id, key)
      setDetails(previous => ({ ...previous, [key]: detail }))
    } catch (error) {
      setDetailError({ id: key, message: error.message })
    } finally { setDetailLoading(null) }
  }

  const download = async (kind, target) => {
    setExportFeedback(null)
    if (kind === 'reviewed' && (
      reviewedExportState.status !== 'ready' || !reviewedExportState.has_confirmed_sets
    )) {
      setExportFeedback({
        kind: 'empty',
        message: 'No confirmed duplicate sets are available yet. Review and confirm groups before exporting operational results.',
      })
      return
    }
    setExportBusyKind(kind)
    try {
      await api.download(target.path, target.filename)
      setExportFeedback({ kind: 'success', message: exportSuccessFeedback(kind) })
    } catch (error) {
      setExportFeedback({ kind: 'error', message: exportFailureFeedback(kind, error.status) })
    } finally {
      setExportBusyKind('')
    }
  }

  if (scanError) return <ScanUnavailable />

  return <>
    <header><div><p className="eyebrow">Scan results</p><h1>{scan?.scan_name || 'Loading scan…'}</h1>
      <p>{scan && `Scan ${scan.id} · ${scanStatusLabel(scan.status)} · ${scan.total_records} records · review threshold ${scan.threshold}`}</p></div>
      <LlmStatus />
      <div className="actions"><Link className="button secondary" to="/">Dashboard</Link><Link className="button secondary" to="/new-scan">New Scan</Link><Link className="button secondary" to={`/scans/${id}/warnings`}>Warnings ({scan?.warnings_count ?? 0})</Link></div>
    </header>

    <ExportAuthorityPanel
      targets={exports}
      reviewedState={reviewedExportState}
      conflictCount={summary?.conflict_count || 0}
      deferredCount={summary?.deferred_count || 0}
      busyKind={exportBusyKind}
      feedback={exportFeedback}
      onDownload={download}
      onRefreshReviewedState={refreshReviewedExportState}
    />

    <section className="panel identity-summary" aria-labelledby="identity-summary-heading">
      <div className="group-head"><div><p className="eyebrow">Identity-set summary</p><h2 id="identity-summary-heading">Potential duplicate identities</h2></div>
        {summary?.projection && <div className="snapshot-meta"><b>Authoritative identity projection</b><span>{summary.projection.projection_contract}</span><span>Source run: {summary.projection.source_projection_run_id}</span></div>}
      </div>
      {summaryError ? <div className={`error identity-${summaryError.kind}`} role="alert"><b>{summaryError.title}</b><p>{summaryError.message}</p></div> :
        !summary ? <p>Loading authoritative identity summary…</p> : <div className="cards compact-cards">
          <article><label>Records scanned</label><strong>{summary.canonical_record_count}</strong></article>
          <article><label>Potential duplicate identities</label><strong>{summary.group_count}</strong><small>System hypotheses, not confirmed duplicates</small></article>
          <article><label>Likely duplicate groups</label><strong>{summary.likely_group_count}</strong></article>
          <article><label>Needs review</label><strong>{summary.review_group_count}</strong></article>
          <article><label>Conflicts</label><strong>{summary.conflict_count}</strong></article>
          <article><label>Deferred / unresolved</label><strong>{summary.deferred_count}</strong></article>
          <article><label>Not safely assigned</label><strong>{summary.unassigned_count}</strong><small>Not confirmed unique</small></article>
        </div>}
    </section>

    {view !== 'pairs' && <div className="view-toggle" role="tablist" aria-label="Identity result views">
      <button type="button" role="tab" aria-selected={view === 'groups'} className={view === 'groups' ? '' : 'secondary'} onClick={() => setView('groups')}>Identity groups ({summary?.group_count ?? '…'})</button>
      <button type="button" role="tab" aria-selected={view === 'outcomes'} className={view === 'outcomes' ? '' : 'secondary'} onClick={() => setView('outcomes')}>Conflicts &amp; deferred ({(summary?.conflict_count || 0) + (summary?.deferred_count || 0)})</button>
      <details className="advanced-diagnostics"><summary>Advanced diagnostics</summary><button type="button" className="secondary" onClick={() => setView('pairs')}>Open legacy pair diagnostics</button></details>
    </div>}

    {view === 'groups' && <><section className="panel group-filters" aria-label="Identity group filters">
      <label>Status<select value={statusFilter} onChange={event => { setStatusFilter(event.target.value); setPage(0) }}><option value="">All accepted statuses</option><option value="LIKELY_DUPLICATE_GROUP">Likely duplicate group</option><option value="POSSIBLE_DUPLICATE_GROUP_REVIEW">Possible duplicate group — review</option></select></label>
      <label>Minimum group size<input type="number" min="2" value={minimumSize} onChange={event => { setMinimumSize(event.target.value); setPage(0) }} /></label>
      <label>Maximum group size<input type="number" min="2" value={maximumSize} onChange={event => { setMaximumSize(event.target.value); setPage(0) }} /></label>
    </section>
      {groupError ? <div className="error" role="alert"><b>{groupError.title}</b><p>{groupError.message}</p></div> :
        <section className="panel" role="tabpanel" aria-label="Authoritative identity groups"><IdentityGroups scanId={id} result={groupResult} detailByKey={details} loadingKey={detailLoading} detailError={detailError} toggleDetail={toggleDetail} onReviewSaved={refreshReviewedExportState} />
          {groupResult?.total > pageLimit && <nav className="pagination" aria-label="Identity group pages"><button type="button" className="secondary" disabled={page === 0} onClick={() => setPage(value => value - 1)}>Previous</button><span>Page {page + 1} of {Math.ceil(groupResult.total / pageLimit)}</span><button type="button" className="secondary" disabled={(page + 1) * pageLimit >= groupResult.total} onClick={() => setPage(value => value + 1)}>Next</button></nav>}
        </section>}
    </>}
    {view === 'outcomes' && <section className="panel" role="tabpanel" aria-label="Identity conflicts and deferred work"><OutcomeView outcomes={outcomes} /></section>}
    {view === 'pairs' && <PairDiagnostics scanId={id} onClose={() => setView('groups')} />}
  </>
}

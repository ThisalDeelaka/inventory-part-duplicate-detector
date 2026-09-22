import { reviewedExportGuidance } from '../utils/identityExportUi'

export default function ExportAuthorityPanel({
  targets,
  reviewedState,
  conflictCount = 0,
  deferredCount = 0,
  busyKind = '',
  feedback = null,
  onDownload,
  onRefreshReviewedState,
}) {
  const reviewedDisabled = (
    reviewedState?.status !== 'ready'
    || !reviewedState.has_confirmed_sets
    || Boolean(busyKind)
  )
  return <section className="panel export-authority" aria-labelledby="export-authority-heading" aria-busy={Boolean(busyKind)}>
    <div><p className="eyebrow">Export authority</p><h2 id="export-authority-heading">Choose the result you need</h2></div>
    <div className="export-authority-grid">
      <article className="export-authority-card system-export-card" aria-labelledby="system-export-heading">
        <p className="authority-label">System suggestions</p>
        <h3 id="system-export-heading">System Group Export</h3>
        <p>Contains system-suggested same-identity candidates for analysis and review. Every suggestion requires human review.</p>
        <small>No records are automatically merged, deleted, or changed in IFS.</small>
        <div className="actions">
          <button type="button" disabled={Boolean(busyKind)} onClick={() => onDownload('system-csv', targets.systemGroups)}>
            {busyKind === 'system-csv' ? 'Preparing system CSV…' : 'Export system suggestions as CSV'}
          </button>
          <button type="button" disabled={Boolean(busyKind)} onClick={() => onDownload('system-xlsx', targets.systemGroupsExcel)}>
            {busyKind === 'system-xlsx' ? 'Preparing system Excel…' : 'Export system suggestions as Excel'}
          </button>
        </div>
      </article>

      <article className="export-authority-card reviewed-export-card" aria-labelledby="reviewed-export-heading">
        <p className="authority-label">Reviewed decisions</p>
        <h3 id="reviewed-export-heading">Reviewed Identity Export</h3>
        <p>Contains only current human-confirmed same-identity sets. Human decisions are operationally authoritative.</p>
        <small>{reviewedExportGuidance(reviewedState)}</small>
        <div className="actions">
          <button type="button" disabled={reviewedDisabled} onClick={() => onDownload('reviewed', targets.reviewedIdentities)}>
            {busyKind === 'reviewed' ? 'Preparing reviewed CSV…' : 'Export human-confirmed identity sets (CSV)'}
          </button>
          <button type="button" disabled={reviewedDisabled} onClick={() => onDownload('reviewed-xlsx', targets.reviewedIdentitiesExcel)}>
            {busyKind === 'reviewed-xlsx' ? 'Preparing reviewed Excel…' : 'Export human-confirmed identity sets (Excel)'}
          </button>
          {reviewedState?.status === 'error' && <button type="button" className="secondary" disabled={Boolean(busyKind)} onClick={onRefreshReviewedState}>
            Reload reviewed export availability
          </button>}
        </div>
      </article>
    </div>

    {(conflictCount > 0 || deferredCount > 0) && <details className="supporting-exports">
      <summary>Supporting conflict and deferred exports</summary>
      <div className="actions">
        {conflictCount > 0 && <button type="button" className="secondary" disabled={Boolean(busyKind)} onClick={() => onDownload('supporting', targets.conflicts)}>Export conflicts</button>}
        {deferredCount > 0 && <button type="button" className="secondary" disabled={Boolean(busyKind)} onClick={() => onDownload('supporting', targets.deferred)}>Export deferred work</button>}
      </div>
    </details>}

    {feedback && <p className={feedback.kind === 'error' ? 'error' : feedback.kind === 'empty' ? 'warning' : 'banner'} role={feedback.kind === 'error' ? 'alert' : 'status'}>{feedback.message}</p>}
  </section>
}

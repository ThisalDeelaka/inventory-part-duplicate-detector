import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'

export default function Dashboard() {
  const [data, setData] = useState(null); const [health, setHealth] = useState(null); const [error, setError] = useState('')
  useEffect(() => { Promise.all([api.get('/api/diagnostics/summary'), api.get('/health'), api.get('/ready')]).then(([d,h,r]) => {setData(d); setHealth({...h, readiness:r.status})}).catch(e=>setError(e.message)) }, [])
  return <><header><div><p className="eyebrow">Inventory data quality</p><h1>Part Master Duplication Identifier</h1><p>Explainable, local duplicate intelligence for ERP CSV exports.</p></div><Link className="button" to="/new-scan">Start new scan</Link></header>
    {error && <div className="error">{error}</div>}
    <section className="banner"><b>Candidate detection, not automatic merging.</b> Confidence scores support review decisions; they do not establish duplicate identity.</section>
    <div className="cards">
      <article><label>Service</label><strong>{health?.status || 'Checking...'}</strong><small>{health?.readiness || ''}</small></article>
      <article><label>Model</label><strong>{health?.model_version || '...'}</strong><small>Local hybrid NLP</small></article>
      <article><label>Total scans</label><strong>{data?.total_scans ?? '...'}</strong></article>
      <article><label>Candidates</label><strong>{data?.total_candidates ?? '...'}</strong></article>
      <article><label>Feedback</label><strong>{data?.total_feedback_records ?? '...'}</strong></article>
    </div>
    <section className="panel"><h2>Latest activity</h2>{data?.last_scan ? <div className="row"><div><b>{data.last_scan.scan_name}</b><small>{data.last_scan.status} · {data.last_scan.total_candidates} candidates</small></div><Link to={`/scans/${data.last_scan.id}`}>Open results</Link></div> : <p className="empty">No scans yet. Load the sample CSV or upload an export to begin.</p>}</section>
  </>
}

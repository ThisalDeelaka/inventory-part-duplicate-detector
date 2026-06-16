import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'

const FALLBACK_FIELDS = [
  { field: 'CONTRACT', display: 'Site' },
  { field: 'TYPE_CODE', display: 'Purchase Type' },
  { field: 'UNIT_MEAS', display: 'Inventory UOM' },
  { field: 'PRIME_COMMODITY', display: 'Com Group 01' },
  { field: 'SECOND_COMMODITY', display: 'Com Group 02' },
  { field: 'HAZARD_CODE', display: 'Safety Code' },
  { field: 'ACCOUNTING_GROUP', display: 'Accounting Group' },
  { field: 'PART_PRODUCT_CODE', display: 'Product Code' },
  { field: 'PART_PRODUCT_FAMILY', display: 'Product Family' },
  { field: 'PRODUCT_CATEGORY_ID', display: 'Product Category' },
  { field: 'HSN_SAC_CODE', display: 'HSN/SAC Code' },
]

export default function NewScan() {
  const [fields, setFields] = useState([])
  const [selected, setSelected] = useState(['CONTRACT', 'UNIT_MEAS'])
  const [file, setFile] = useState(null)
  const [name, setName] = useState('Inventory duplicate scan')
  const [threshold, setThreshold] = useState(75)
  const [scanMode, setScanMode] = useState('SAME_SITE_DUPLICATE')
  const [sensitiveMode, setSensitiveMode] = useState(true)
  const [validation, setValidation] = useState(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const nav = useNavigate()

  useEffect(() => {
    api.get('/api/config/fields')
      .then(x => setFields(x.filter(f => !f.required)))
      .catch(() => {
        setFields(FALLBACK_FIELDS)
        setError(`Backend is not reachable at ${api.baseUrl}. Start the FastAPI backend, then refresh this page.`)
      })
  }, [])

  const form = () => {
    const f = new FormData()
    f.append('file', file)
    f.append('scan_name', name)
    f.append('threshold', threshold)
    f.append('selected_fields', JSON.stringify(selected))
    f.append('sensitive_mode', sensitiveMode)
    f.append('scan_mode', scanMode)
    return f
  }

  const validate = async () => {
    if (!file) return setError('Choose a CSV file first.')
    setBusy('validate'); setError('')
    try { setValidation(await api.postForm('/api/scans/validate-only', form())) }
    catch (e) { setError(e.message) }
    finally { setBusy('') }
  }

  const run = async () => {
    if (!file) return setError('Choose a CSV file first.')
    setBusy('scan'); setError('')
    try {
      const r = await api.postForm('/api/scans/upload', form())
      nav(`/scans/${r.scan_id}`)
    } catch (e) { setError(e.message) }
    finally { setBusy('') }
  }

  return (
    <>
      <header><div><p className="eyebrow">New analysis</p><h1>Run duplicate scan</h1><p>Choose business conditions to narrow comparisons, then tune the review threshold.</p></div></header>
      {error && <div className="error">{error}</div>}
      <div className="two-col">
        <section className="panel form">
          <label>Scan name<input value={name} onChange={e => setName(e.target.value)} /></label>
          <label>Inventory CSV<input type="file" accept=".csv,text/csv" onChange={e => setFile(e.target.files[0])} /></label>
          <label>Scan mode
            <select value={scanMode} onChange={e => setScanMode(e.target.value)}>
              <option value="SAME_SITE_DUPLICATE">Same-site duplicate scan</option>
              <option value="CROSS_SITE_STANDARDIZATION">Cross-site standardization scan</option>
              <option value="DISCOVERY">Discovery scan</option>
            </select>
            <small>Same-site mode is strict. Cross-site mode is for standardizing equivalent parts across sites.</small>
          </label>
          <label className="inline-check"><input type="checkbox" checked={sensitiveMode} onChange={e => setSensitiveMode(e.target.checked)} /><span><b>Sensitive Data Mode</b><small>No raw CSV persistence, local-only NLP, file fingerprint, and sensitive-pattern warnings.</small></span></label>
          <div><label>Review strictness <b>{threshold}</b></label><input type="range" min="60" max="95" value={threshold} onChange={e => setThreshold(+e.target.value)} /><small>Move right to show only stronger matches. Move left to discover more possible matches.</small></div>
        </section>
        <section className="panel"><h2>Duplicate-checking conditions</h2><div className="checks">{fields.map(f => <label key={f.field}><input type="checkbox" checked={selected.includes(f.field)} onChange={() => setSelected(s => s.includes(f.field) ? s.filter(x => x !== f.field) : [...s, f.field])} /><span>{f.display}<small>{f.field}</small></span></label>)}</div></section>
      </div>
      <div className="actions"><button className="secondary" onClick={validate} disabled={!!busy}>{busy === 'validate' ? 'Validating...' : 'Validate only'}</button><button onClick={run} disabled={!!busy}>{busy === 'scan' ? 'Scanning...' : 'Run scan'}</button></div>
      {validation && <section className="panel"><h2>Validation result <span className={validation.valid ? 'badge HIGH' : 'badge LOW'}>{validation.valid ? 'VALID' : 'BLOCKED'}</span></h2><div className="metrics"><span>{validation.record_count} records</span><span>{validation.empty_descriptions_count} empty descriptions</span><span>{validation.duplicate_part_number_count} repeated part rows</span><span>{validation.warnings.length} warnings</span></div>{validation.privacy && <div className="security-summary"><b>Security transparency</b><span>Raw CSV stored: {validation.privacy.raw_csv_stored ? 'Yes' : 'No'}</span><span>External AI used: {validation.privacy.external_ai_used ? 'Yes' : 'No'}</span><span>Local processing: {validation.privacy.local_processing_only ? 'Yes' : 'No'}</span><small>SHA-256: {validation.privacy.file_sha256}</small></div>}{validation.warnings.map((w, i) => <p className="warning" key={i}>{w.message}</p>)}</section>}
    </>
  )
}

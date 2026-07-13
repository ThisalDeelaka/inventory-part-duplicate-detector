import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'

const FALLBACK_FIELDS = [
  { field: 'PART_NO', display: 'Part No', required: true },
  { field: 'DESCRIPTION', display: 'Item Description', required: true },
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
  const [allFields, setAllFields] = useState(FALLBACK_FIELDS)
  const [fields, setFields] = useState(FALLBACK_FIELDS.filter(f => !f.required))
  const [selected, setSelected] = useState(['CONTRACT', 'UNIT_MEAS'])
  const [file, setFile] = useState(null)
  const [name, setName] = useState('Inventory duplicate scan')
  const [threshold, setThreshold] = useState(75)
  const [scanMode, setScanMode] = useState('SAME_SITE_DUPLICATE')
  const [sensitiveMode, setSensitiveMode] = useState(true)
  const [validation, setValidation] = useState(null)
  const [mappingDraft, setMappingDraft] = useState([])
  const [profileName, setProfileName] = useState('CSV mapping profile')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const nav = useNavigate()

  useEffect(() => {
    api.get('/api/config/fields')
      .then(x => {
        setAllFields(x)
        setFields(x.filter(f => !f.required))
      })
      .catch(() => {
        setAllFields(FALLBACK_FIELDS)
        setFields(FALLBACK_FIELDS.filter(f => !f.required))
        setError(`Backend is not reachable at ${api.baseUrl}. Start the FastAPI backend, then refresh this page.`)
      })
  }, [])

  useEffect(() => {
    if (!validation) return
    setMappingDraft(validation.column_mapping || [])
    setProfileName(validation.profile?.profile_name || validation.header_signature || 'CSV mapping profile')
  }, [validation])

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

  const mappingOptions = [...allFields].sort((a, b) => {
    if (a.required !== b.required) return a.required ? -1 : 1
    return a.display.localeCompare(b.display)
  })

  const updateMapping = (sourceColumn, canonicalField) => {
    setMappingDraft(current => current.map(row => (
      row.source_column === sourceColumn
        ? { ...row, canonical_field: canonicalField || null, match_type: canonicalField ? 'manual' : 'unmapped' }
        : row
    )))
  }

  const validate = async () => {
    if (!file) return setError('Choose a CSV file first.')
    setBusy('validate'); setError('')
    try {
      const result = await api.postForm('/api/scans/validate-only', form())
      setValidation(result)
      setMappingDraft(result.column_mapping || [])
      setProfileName(result.profile?.profile_name || result.header_signature || 'CSV mapping profile')
    }
    catch (e) { setError(e.message) }
    finally { setBusy('') }
  }

  const saveMappingProfile = async () => {
    if (!validation) return
    setBusy('save'); setError('')
    try {
      const payload = {
        profile_name: profileName,
        header_signature: validation.header_signature,
        source_columns: validation.column_mapping.map(row => row.source_column),
        column_mapping: mappingDraft,
      }
      const saved = await api.postJson('/api/scans/mapping-profiles', payload)
      setValidation(current => current ? { ...current, profile: saved, profile_applied: true } : current)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy('')
    }
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
      {validation?.column_mapping?.length ? <section className="panel"><h2>Column mapping preview</h2><p>Edit the canonical field for each source column, then save the mapping profile before scanning.</p><div className="table-wrap"><table><thead><tr><th>Source column</th><th>Canonical field</th><th>Match</th></tr></thead><tbody>{mappingDraft.map(row => <tr key={row.source_column}><td>{row.source_column}</td><td><select value={row.canonical_field || ''} onChange={e => updateMapping(row.source_column, e.target.value)}><option value="">Unmapped</option>{mappingOptions.map(field => <option key={field.field} value={field.field}>{field.display} ({field.field}){field.required ? ' *' : ''}</option>)}</select></td><td><span className={`badge ${row.match_type === 'exact' ? 'HIGH' : row.match_type === 'alias' || row.match_type === 'profile' || row.match_type === 'manual' ? 'MEDIUM' : 'LOW'}`}>{row.match_type}</span></td></tr>)}</tbody></table></div>{validation.unmapped_source_columns?.length ? <p className="warning">Unmapped source columns: {validation.unmapped_source_columns.join(', ')}</p> : null}<div className="actions" style={{ marginTop: '1rem' }}><label style={{ flex: '1 1 320px' }}>Profile name<input value={profileName} onChange={e => setProfileName(e.target.value)} /></label><button className="secondary" onClick={saveMappingProfile} disabled={busy === 'save'}>{busy === 'save' ? 'Saving...' : 'Save mapping profile'}</button></div></section> : null}
      {validation?.profile ? <section className="panel"><h2>Mapping profile</h2><p><b>{validation.profile.profile_name}</b> {validation.profile_applied ? 'applied' : 'available'} for this header signature.</p><small>Used {validation.profile.usage_count} time(s)</small></section> : null}
    </>
  )
}

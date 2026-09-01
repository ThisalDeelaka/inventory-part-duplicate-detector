import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import LlmStatus from '../components/LlmStatus'
import {
  cleanColumnSamples,
  columnSuggestionStateKey,
  isCurrentRequest,
  isCurrentValidationToken,
  nextValidationToken,
} from '../utils/llmUi'
import {
  formatElapsed,
  processingGuidance,
  scanRequestError,
  validationContextKey,
} from '../utils/productJourneyUi'

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
  const [mappingFields, setMappingFields] = useState([
    { field: 'PART_NO', display: 'Part No', required: true },
    { field: 'DESCRIPTION', display: 'Item Description', required: true },
  ])
  const [selected, setSelected] = useState(['CONTRACT', 'UNIT_MEAS'])
  const [columnMapping, setColumnMapping] = useState({})
  const [file, setFile] = useState(null)
  const [name, setName] = useState('Inventory duplicate scan')
  const [threshold, setThreshold] = useState(75)
  const [scanMode, setScanMode] = useState('SAME_SITE_DUPLICATE')
  const [sensitiveMode, setSensitiveMode] = useState(true)
  const [validation, setValidation] = useState(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState(null)
  const [validatedContext, setValidatedContext] = useState('')
  const [elapsedSeconds, setElapsedSeconds] = useState(0)
  const [columnAssistance, setColumnAssistance] = useState({})
  const columnRequests = useRef({})
  const validationRequestId = useRef(0)
  const fileGeneration = useRef(0)
  const scanRequestActive = useRef(false)
  const completionRouted = useRef(false)
  const nav = useNavigate()

  useEffect(() => {
    api.get('/api/config/fields')
      .then(x => {
        setFields(x.filter(f => !f.required))
        setMappingFields(x)
      })
      .catch(() => {
        setFields(FALLBACK_FIELDS)
        setError({ title: 'Backend is not reachable', message: `Start the FastAPI backend at ${api.baseUrl}, then reload this page.` })
      })
  }, [])

  useEffect(() => {
    if (busy !== 'scan') { setElapsedSeconds(0); return undefined }
    const started = Date.now()
    const update = () => setElapsedSeconds(Math.floor((Date.now() - started) / 1000))
    update()
    const timer = window.setInterval(update, 1000)
    return () => window.clearInterval(timer)
  }, [busy])

  const form = (submittedFile = file) => {
    const f = new FormData()
    f.append('file', submittedFile)
    f.append('scan_name', name)
    f.append('threshold', threshold)
    f.append('selected_fields', JSON.stringify(selected))
    f.append('column_mapping', JSON.stringify(columnMapping))
    f.append('sensitive_mode', sensitiveMode)
    f.append('scan_mode', scanMode)
    f.append('product_authority', 'current_product')
    return f
  }

  const validate = async () => {
    if (!file) return setError({ title: 'Choose a CSV file', message: 'Select a supported CSV before validating.' })
    const submittedFile = file
    const token = nextValidationToken(validationRequestId.current, fileGeneration.current)
    validationRequestId.current = token.requestId
    const tokenIsCurrent = () => isCurrentValidationToken(
      token,
      validationRequestId.current,
      fileGeneration.current,
    )
    const submittedSelected = [...selected]
    const submittedMapping = { ...columnMapping }
    const submittedSensitiveMode = sensitiveMode
    setBusy('validate'); setError(null); setValidatedContext('')
    try {
      const result = await api.postForm('/api/scans/validate-only', form(submittedFile))
      if (!tokenIsCurrent()) return
      const resolvedMapping = { ...result.resolved_column_mapping, ...submittedMapping }
      setValidation(result)
      setColumnMapping(resolvedMapping)
      setValidatedContext(validationContextKey(
        token.fileGeneration, submittedSelected, resolvedMapping, submittedSensitiveMode,
      ))
      setColumnAssistance({})
    }
    catch (e) {
      if (tokenIsCurrent()) setError(scanRequestError(e.status, 'validation'))
    }
    finally {
      if (tokenIsCurrent()) setBusy('')
    }
  }

  const run = async () => {
    if (scanRequestActive.current) return
    if (!file) return setError({ title: 'Choose a CSV file', message: 'Select and validate a supported CSV before running a scan.' })
    if (!validation?.valid || validatedContext !== validationContextKey(
      fileGeneration.current, selected, columnMapping, sensitiveMode,
    )) return setError({ title: 'Current validation required', message: 'Validate the current file and mapping successfully before running the scan.' })
    scanRequestActive.current = true
    completionRouted.current = false
    setBusy('scan'); setError(null)
    try {
      const r = await api.postForm('/api/scans/upload', form())
      if (!Number.isInteger(Number(r?.scan_id)) || Number(r.scan_id) <= 0) {
        setError(scanRequestError('unexpected', 'scan'))
        return
      }
      if (!completionRouted.current) {
        completionRouted.current = true
        nav(`/scans/${r.scan_id}`)
      }
    } catch (e) { setError(scanRequestError(e.status, 'scan')) }
    finally { scanRequestActive.current = false; setBusy('') }
  }

  const updateMapping = (canonicalField, sourceColumn) => {
    setColumnMapping(current => ({ ...current, [canonicalField]: sourceColumn }))
    setColumnAssistance({})
  }

  const requestSuggestion = async sourceColumn => {
    const key = columnSuggestionStateKey(sourceColumn)
    if (columnAssistance[key]?.phase === 'loading') return
    const samples = cleanColumnSamples(validation?.column_samples?.[sourceColumn])
    const requestId = (columnRequests.current[key] || 0) + 1
    columnRequests.current[key] = requestId
    setColumnAssistance(current => ({
      ...current,
      [key]: { phase: 'loading', result: null, error: '', requestId },
    }))
    try {
      const result = await api.requestColumnSuggestion(sourceColumn, samples)
      setColumnAssistance(current => (
        isCurrentRequest(current[key]?.requestId, requestId)
          ? { ...current, [key]: { phase: 'success', result, error: '', requestId } }
          : current
      ))
    } catch (requestError) {
      setColumnAssistance(current => (
        isCurrentRequest(current[key]?.requestId, requestId)
          ? { ...current, [key]: { phase: 'error', result: null, error: requestError.message, requestId } }
          : current
      ))
    }
  }

  const resolvedSources = new Set([
    ...Object.values(validation?.resolved_column_mapping || {}),
    ...Object.values(columnMapping).filter(Boolean),
  ])
  const unresolvedColumns = (validation?.available_columns || [])
    .filter(column => !resolvedSources.has(column))

  const selectFile = selectedFile => {
    fileGeneration.current += 1
    setFile(selectedFile)
    setValidation(null)
    setColumnMapping({})
    setColumnAssistance({})
    setError(null)
    setValidatedContext('')
    setBusy(current => current === 'validate' ? '' : current)
  }

  const currentValidationContext = validationContextKey(
    fileGeneration.current, selected, columnMapping, sensitiveMode,
  )
  const validationIsCurrent = Boolean(validation && validatedContext === currentValidationContext)
  const canRun = Boolean(file && validation?.valid && validationIsCurrent && !busy)

  return (
    <>
      <header><div><p className="eyebrow">New scan</p><h1>Run duplicate scan</h1><p>Select a CSV, confirm its field mapping, validate it, then run the scan.</p></div><div className="actions"><Link className="button secondary" to="/">Dashboard</Link></div><LlmStatus /></header>
      {error && <div className="error" role="alert"><b>{error.title}</b><p>{error.message}</p><Link to="/">View recent scans</Link></div>}
      <div className="two-col">
        <section className="panel form">
          <label>Scan name<input value={name} disabled={!!busy} onChange={e => setName(e.target.value)} /></label>
          <label>Inventory CSV<input type="file" accept=".csv,text/csv" disabled={!!busy} onChange={event => selectFile(event.target.files[0] || null)} /></label>
          <label>Scan mode
            <select value={scanMode} disabled={!!busy} onChange={e => setScanMode(e.target.value)}>
              <option value="SAME_SITE_DUPLICATE">Same-site duplicate scan</option>
              <option value="CROSS_SITE_STANDARDIZATION">Cross-site standardization scan</option>
              <option value="DISCOVERY">Discovery scan</option>
            </select>
            <small>Same-site mode is strict. Cross-site mode is for standardizing equivalent parts across sites.</small>
          </label>
          <label className="inline-check"><input type="checkbox" checked={sensitiveMode} disabled={!!busy} onChange={e => setSensitiveMode(e.target.checked)} /><span><b>Sensitive Data Mode</b><small>No raw CSV persistence, local-only NLP, file fingerprint, and sensitive-pattern warnings.</small></span></label>
          <div><label>Review strictness <b>{threshold}</b></label><input type="range" min="60" max="95" value={threshold} disabled={!!busy} onChange={e => setThreshold(+e.target.value)} /><small>Move right to show only stronger matches. Move left to discover more possible matches.</small></div>
        </section>
        <section className="panel"><h2>Duplicate-checking conditions</h2><div className="checks">{fields.map(f => <label key={f.field}><input type="checkbox" checked={selected.includes(f.field)} disabled={!!busy} onChange={() => setSelected(s => s.includes(f.field) ? s.filter(x => x !== f.field) : [...s, f.field])} /><span>{f.display}<small>{f.field}</small></span></label>)}</div></section>
      </div>
      <div className="actions"><button type="button" className="secondary" onClick={validate} disabled={!!busy}>{busy === 'validate' ? 'Validating…' : validationIsCurrent ? 'Validate again' : 'Validate CSV'}</button><button type="button" onClick={run} disabled={!canRun}>{busy === 'scan' ? 'Processing inventory…' : 'Run scan'}</button></div>
      {!validation && <p className="validation-guidance">Run Scan becomes available after the current CSV and mapping pass validation.</p>}
      {validation && !validationIsCurrent && <p className="warning" role="status"><b>Validation is out of date.</b> The file, selected conditions, mapping, or privacy setting changed. Validate again before running the scan.</p>}
      {busy === 'scan' && <section className="panel processing-state" role="status" aria-live="polite" aria-busy="true">
        <p className="eyebrow">Request active</p><h2>Processing inventory…</h2>
        <p>The scan is still running.</p><p><b>Elapsed time: {formatElapsed(elapsedSeconds)}</b></p>
        <p>{processingGuidance(elapsedSeconds)}</p>
      </section>}
      {validation && <section className="panel" aria-live="polite"><h2>{validation.valid ? 'Validation passed' : 'Validation failed'} <span className={validation.valid ? 'badge HIGH' : 'badge LOW'}>{validation.valid ? 'Ready' : 'Blocked'}</span></h2>{validation.valid ? <p>The current CSV and mapping are supported. Run Scan is available while this validation remains current.</p> : <p>Review the warnings and required field mapping below, then validate again.</p>}<div className="metrics"><span>{validation.record_count} records</span><span>{validation.empty_descriptions_count} empty descriptions</span><span>{validation.duplicate_part_number_count} repeated part rows</span><span>{validation.warnings.length} warnings</span></div>{validation.privacy && <div className="security-summary"><b>Security transparency</b><span>Raw CSV stored: {validation.privacy.raw_csv_stored ? 'Yes' : 'No'}</span><span>External AI used: {validation.privacy.external_ai_used ? 'Yes' : 'No'}</span><span>Local processing: {validation.privacy.local_processing_only ? 'Yes' : 'No'}</span><small>SHA-256: {validation.privacy.file_sha256}</small></div>}{validation.warnings.map((w, i) => <p className="warning" key={i}>{w.message}</p>)}</section>}
      {validation?.available_columns && (
        <section className="panel">
          <h2>CSV column mapping</h2>
          <p>Common IFS labels are detected automatically. Choose an uploaded column below only when this environment uses a custom label, then validate again.</p>
          <div className="checks">
            {mappingFields.map(field => (
              <label key={field.field}>
                <span>{field.display}{field.required ? ' *' : ''}<small>{field.field}</small></span>
                <select value={columnMapping[field.field] || ''} disabled={!!busy} onChange={event => updateMapping(field.field, event.target.value)}>
                  <option value="">Automatic / not available</option>
                  {validation.available_columns.map(column => <option value={column} key={column}>{column}</option>)}
                </select>
              </label>
            ))}
          </div>
        </section>
      )}
      {!!unresolvedColumns.length && (
        <section className="panel" aria-label="Unresolved column assistance">
          <p className="eyebrow">Explicit optional assistance</p>
          <h2>Unresolved source columns</h2>
          <p>Request a bounded suggestion for one source header. Nothing is mapped until you choose “Use suggestion,” and you must validate again before scanning.</p>
          <div className="llm-column-list">
            {unresolvedColumns.map(column => {
              const key = columnSuggestionStateKey(column)
              const state = columnAssistance[key] || { phase: 'idle' }
              const samples = cleanColumnSamples(validation.column_samples?.[column])
              const suggestion = state.result?.suggestion
              return (
                <article key={column}>
                  <div>
                    <b>{column}</b>
                    <small>{samples.length ? 'Samples: ' + samples.join(' · ') : 'No nonblank bounded samples available'}</small>
                  </div>
                  <button type="button" onClick={() => requestSuggestion(column)} disabled={!!busy || !samples.length || state.phase === 'loading'} aria-busy={state.phase === 'loading'}>
                    {state.phase === 'loading' ? 'Requesting…' : state.phase === 'error' ? 'Retry suggestion' : 'Suggest mapping'}
                  </button>
                  {state.phase === 'error' && <p className="llm-error" role="alert">{state.error}</p>}
                  {state.phase === 'success' && (
                    <div className="llm-result" aria-live="polite">
                      {state.result.deterministic_bypass ? (
                        <>
                          <b>Deterministic bypass — no LLM suggestion used</b>
                          <span>{state.result.bypass_reason}</span>
                          <small>{state.result.metadata.cache_hit ? 'Cache hit' : 'Not cached'} · Provider not used</small>
                        </>
                      ) : suggestion?.suggested_canonical_field ? (
                        <>
                          <b>Suggested: {suggestion.suggested_canonical_field}</b>
                          <span>Confidence {Math.round(suggestion.confidence * 100)}%</span>
                          <p>{suggestion.reason}</p>
                          <small>Confirmation required: {suggestion.requires_confirmation ? 'Yes' : 'No'} · {state.result.metadata.cache_hit ? 'Cache hit' : 'Provider result'}</small>
                          <button type="button" className="secondary" disabled={!!busy} onClick={() => updateMapping(suggestion.suggested_canonical_field, column)}>Use suggestion</button>
                        </>
                      ) : (
                        <>
                          <b>No suggestion — advisory abstained</b>
                          <span>Confidence {Math.round((suggestion?.confidence || 0) * 100)}%</span>
                          <p>{suggestion?.reason || 'Evidence was insufficient for a bounded suggestion.'}</p>
                          <small>Confirmation required: {suggestion?.requires_confirmation ? 'Yes' : 'No'} · {state.result.metadata.cache_hit ? 'Cache hit' : 'Provider result'}</small>
                        </>
                      )}
                    </div>
                  )}
                </article>
              )
            })}
          </div>
        </section>
      )}
    </>
  )
}

import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import LlmStatus from '../components/LlmStatus'
import {
  cleanColumnSamples,
  columnSuggestionStateKey,
  isCurrentRequest,
  isCurrentValidationToken,
  nextValidationToken,
} from '../utils/llmUi'
import { customFieldCreatePayload, customFieldModeLabel, mergeCustomFields } from '../utils/customFieldUi'
import { DEFAULT_PART_TYPE, PART_TYPE_OPTIONS, filterFieldsForPartType } from '../utils/partTypeUi'

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

const SCAN_MODE = 'SAME_SITE_DUPLICATE'
const SENSITIVE_MODE = true
const MAX_THRESHOLD = 90

export default function NewScan() {
  const [builtInFields, setBuiltInFields] = useState([
    { field: 'PART_NO', display: 'Part No', required: true },
    { field: 'DESCRIPTION', display: 'Item Description', required: true },
  ])
  const [customFields, setCustomFields] = useState([])
  const [customFieldDrafts, setCustomFieldDrafts] = useState({})
  const [customFieldState, setCustomFieldState] = useState({})
  const [partType, setPartType] = useState(DEFAULT_PART_TYPE)
  const [selected, setSelected] = useState(['CONTRACT', 'UNIT_MEAS'])
  const [columnMapping, setColumnMapping] = useState({})
  const [file, setFile] = useState(null)
  const [name, setName] = useState('Inventory duplicate scan')
  const [threshold, setThreshold] = useState(75)
  const [validation, setValidation] = useState(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [columnAssistance, setColumnAssistance] = useState({})
  const columnRequests = useRef({})
  const validationRequestId = useRef(0)
  const fileGeneration = useRef(0)
  const nav = useNavigate()

  const refreshCustomFields = () => api.listCustomFields().then(setCustomFields).catch(() => {})

  useEffect(() => {
    api.get('/api/config/fields')
      .then(setBuiltInFields)
      .catch(() => {
        setBuiltInFields(current => [...current, ...FALLBACK_FIELDS])
        setError(`Backend is not reachable at ${api.baseUrl}. Start the FastAPI backend, then refresh this page.`)
      })
    refreshCustomFields()
  }, [])

  const { mappingFields, checklistFields } = mergeCustomFields(filterFieldsForPartType(builtInFields, partType), customFields)

  const changePartType = nextPartType => {
    setPartType(nextPartType)
    const stillRelevant = new Set(filterFieldsForPartType(builtInFields, nextPartType).map(f => f.field))
    setSelected(current => current.filter(field => stillRelevant.has(field) || customFields.some(c => c.field_key === field)))
  }

  const form = (submittedFile = file) => {
    const f = new FormData()
    f.append('file', submittedFile)
    f.append('scan_name', name)
    f.append('threshold', Math.min(threshold, MAX_THRESHOLD))
    f.append('selected_fields', JSON.stringify(selected))
    f.append('column_mapping', JSON.stringify(columnMapping))
    f.append('sensitive_mode', SENSITIVE_MODE)
    f.append('scan_mode', SCAN_MODE)
    f.append('part_type', partType)
    return f
  }

  const validate = async () => {
    if (!file) return setError('Choose a CSV or XLSX file first.')
    const submittedFile = file
    const token = nextValidationToken(validationRequestId.current, fileGeneration.current)
    validationRequestId.current = token.requestId
    const tokenIsCurrent = () => isCurrentValidationToken(
      token,
      validationRequestId.current,
      fileGeneration.current,
    )
    setBusy('validate'); setError('')
    try {
      const result = await api.postForm('/api/scans/validate-only', form(submittedFile))
      if (!tokenIsCurrent()) return
      setValidation(result)
      setColumnMapping(current => ({ ...result.resolved_column_mapping, ...current }))
      setColumnAssistance({})
    }
    catch (e) {
      if (tokenIsCurrent()) setError(e.message)
    }
    finally {
      if (tokenIsCurrent()) setBusy('')
    }
  }

  const run = async () => {
    if (!file) return setError('Choose a CSV or XLSX file first.')
    setBusy('scan'); setError('')
    try {
      const r = await api.postForm('/api/scans/upload', form())
      nav(`/scans/${r.scan_id}`)
    } catch (e) { setError(e.message) }
    finally { setBusy('') }
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

  const customFieldDraft = column => customFieldDrafts[column] || { label: column, mode: 'SUPPORTING' }

  const updateCustomFieldDraft = (column, patch) => {
    setCustomFieldDrafts(current => ({ ...current, [column]: { ...customFieldDraft(column), ...patch } }))
  }

  const saveCustomField = async column => {
    const draft = customFieldDraft(column)
    setCustomFieldState(current => ({ ...current, [column]: { phase: 'saving', error: '' } }))
    try {
      const payload = customFieldCreatePayload(draft.label, draft.mode, column)
      const created = await api.createCustomField(payload)
      setCustomFields(current => [...current, created])
      updateMapping(created.field_key, column)
      setCustomFieldState(current => ({ ...current, [column]: { phase: 'idle', error: '' } }))
    } catch (e) {
      setCustomFieldState(current => ({ ...current, [column]: { phase: 'error', error: e.message } }))
    }
  }

  const removeCustomField = async id => {
    try {
      await api.deleteCustomField(id)
      setCustomFields(current => current.filter(field => field.id !== id))
    } catch (e) { setError(e.message) }
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
    setCustomFieldDrafts({})
    setCustomFieldState({})
    setError('')
    setBusy(current => current === 'validate' ? '' : current)
  }

  return (
    <>
      <header><div><p className="eyebrow">New analysis</p><h1>Run duplicate scan</h1><p>Choose business conditions to narrow comparisons, then tune the review threshold.</p></div><LlmStatus /></header>
      {error && <div className="error">{error}</div>}
      <div className="two-col">
        <section className="panel form">
          <label>Scan name<input value={name} onChange={e => setName(e.target.value)} /></label>
          <label>Part type
            <select value={partType} onChange={event => changePartType(event.target.value)}>
              {PART_TYPE_OPTIONS.map(([value, label]) => <option value={value} key={value}>{label}</option>)}
            </select>
          </label>
          <label>Parts export (CSV or XLSX)<input type="file" accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={event => selectFile(event.target.files[0] || null)} /></label>
          <div><label>Review strictness <b>{threshold}</b></label><input type="range" min="60" max={MAX_THRESHOLD} value={threshold} onChange={e => setThreshold(+e.target.value)} /><small>Move right to show only stronger matches. Move left to discover more possible matches.</small></div>
        </section>
        <section className="panel"><h2>Duplicate-checking conditions</h2><div className="checks">{checklistFields.map(f => <label key={f.field}><input type="checkbox" checked={selected.includes(f.field)} onChange={() => setSelected(s => s.includes(f.field) ? s.filter(x => x !== f.field) : [...s, f.field])} /><span>{f.display}<small>{f.field}</small></span></label>)}</div></section>
      </div>
      <div className="actions"><button type="button" className="secondary" onClick={validate} disabled={!!busy}>{busy === 'validate' ? 'Validating...' : 'Validate only'}</button><button type="button" onClick={run} disabled={!!busy}>{busy === 'scan' ? 'Scanning...' : 'Run scan'}</button></div>
      {validation && <section className="panel"><h2>Validation result <span className={validation.valid ? 'badge HIGH' : 'badge LOW'}>{validation.valid ? 'VALID' : 'BLOCKED'}</span></h2><div className="metrics"><span>{validation.record_count} records</span><span>{validation.empty_descriptions_count} empty descriptions</span><span>{validation.duplicate_part_number_count} repeated part rows</span><span>{validation.warnings.length} warnings</span></div>{validation.privacy && <div className="security-summary"><b>Security transparency</b><span>Raw CSV stored: {validation.privacy.raw_csv_stored ? 'Yes' : 'No'}</span><span>External AI used: {validation.privacy.external_ai_used ? 'Yes' : 'No'}</span><span>Local processing: {validation.privacy.local_processing_only ? 'Yes' : 'No'}</span><small>SHA-256: {validation.privacy.file_sha256}</small></div>}{validation.warnings.map((w, i) => <p className="warning" key={i}>{w.message}</p>)}</section>}
      {validation?.available_columns && (
        <section className="panel">
          <h2>CSV column mapping</h2>
          <p>Common IFS labels are detected automatically. Choose an uploaded column below only when this environment uses a custom label, then validate again.</p>
          <div className="checks">
            {mappingFields.map(field => (
              <label key={field.field}>
                <span>{field.display}{field.required ? ' *' : ''}<small>{field.field}</small></span>
                <select value={columnMapping[field.field] || ''} onChange={event => updateMapping(field.field, event.target.value)}>
                  <option value="">Automatic / not available</option>
                  {validation.available_columns.map(column => <option value={column} key={column}>{column}</option>)}
                </select>
              </label>
            ))}
          </div>
        </section>
      )}
      {!!customFields.length && (
        <section className="panel" aria-label="Custom business fields">
          <h2>Custom business fields</h2>
          <p>Saved for this environment and auto-applied on future uploads when a matching header is seen again.</p>
          <div className="checks">
            {customFields.map(field => (
              <label key={field.id}>
                <span>{field.display_label}<small>{field.field_key} · {customFieldModeLabel(field.mode)}</small></span>
                <button type="button" className="secondary" onClick={() => removeCustomField(field.id)}>Remove</button>
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
                  <button type="button" onClick={() => requestSuggestion(column)} disabled={!samples.length || state.phase === 'loading'} aria-busy={state.phase === 'loading'}>
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
                          <button type="button" className="secondary" onClick={() => updateMapping(suggestion.suggested_canonical_field, column)}>Use suggestion</button>
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
                  <div className="custom-field-form">
                    <input
                      type="text"
                      value={customFieldDraft(column).label}
                      onChange={event => updateCustomFieldDraft(column, { label: event.target.value })}
                      placeholder="Custom field label"
                    />
                    <select
                      value={customFieldDraft(column).mode}
                      onChange={event => updateCustomFieldDraft(column, { mode: event.target.value })}
                    >
                      <option value="SUPPORTING">Supporting</option>
                      <option value="STRICT">Strict</option>
                    </select>
                    <button
                      type="button"
                      className="secondary"
                      onClick={() => saveCustomField(column)}
                      disabled={customFieldState[column]?.phase === 'saving'}
                    >
                      {customFieldState[column]?.phase === 'saving' ? 'Saving…' : 'Save as custom field'}
                    </button>
                    {customFieldState[column]?.phase === 'error' && (
                      <p className="llm-error" role="alert">{customFieldState[column].error}</p>
                    )}
                  </div>
                </article>
              )
            })}
          </div>
        </section>
      )}
    </>
  )
}
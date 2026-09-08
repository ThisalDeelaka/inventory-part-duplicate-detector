import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import {
  ADVISORY_AUTHORITY_LABEL,
  DETERMINISTIC_AUTHORITY_LABEL,
  difficultValueStateKey,
  isCurrentRequest,
} from '../utils/llmUi'

const EMPTY = { phase: 'idle', result: null, error: '' }

function Metadata({ value }) {
  if (!value) return null
  return (
    <div className="llm-meta">
      <span>{value.provider} · {value.model}</span>
      <span>{value.prompt_version}</span>
      <span>{value.cache_hit ? 'Cache hit' : value.llm_used ? 'Provider used' : 'Provider not used'}</span>
      <span>{Math.round(value.latency_ms)} ms</span>
    </div>
  )
}

function Interpretation({ state, rawValue }) {
  if (state.phase === 'error') return <p className="llm-error" role="alert">{state.error}</p>
  if (state.phase !== 'success') return null
  const value = state.result.interpretation
  return (
    <div className="llm-result" aria-live="polite">
      <b>Advisory interpretation</b>
      <span><strong>Raw:</strong> {rawValue}</span>
      <span><strong>Interpretation:</strong> {value.normalized_interpretation || 'Abstained — insufficient evidence'}</span>
      <span><strong>Confidence:</strong> {Math.round(value.confidence * 100)}%</span>
      {!!Object.keys(value.attributes || {}).length && (
        <dl>{Object.entries(value.attributes).map(([key, item]) => <div key={key}><dt>{key}</dt><dd>{item}</dd></div>)}</dl>
      )}
      {!!value.warnings?.length && <ul>{value.warnings.map(item => <li key={item}>{item}</li>)}</ul>}
      <small>Confirmation required: {value.requires_confirmation ? 'Yes' : 'No'}</small>
      <Metadata value={state.result.metadata} />
    </div>
  )
}

export default function CandidateLlmTools({ candidate }) {
  const [advisory, setAdvisory] = useState(EMPTY)
  const [interpretations, setInterpretations] = useState({})
  const requestIds = useRef({})
  const generation = useRef(0)
  const active = useRef(true)
  const signature = [
    candidate.id,
    candidate.part_no_a,
    candidate.description_a,
    candidate.part_no_b,
    candidate.description_b,
  ].join('|')

  useEffect(() => {
    active.current = true
    generation.current += 1
    setAdvisory(EMPTY)
    setInterpretations({})
    requestIds.current = {}
    return () => {
      active.current = false
      generation.current += 1
    }
  }, [signature])

  const start = key => {
    const id = (requestIds.current[key] || 0) + 1
    requestIds.current[key] = id
    return { id, generation: generation.current }
  }

  const current = (key, token) => (
    active.current
    && generation.current === token.generation
    && isCurrentRequest(requestIds.current[key], token.id)
  )

  const requestAdvisory = async () => {
    if (advisory.phase === 'loading') return
    const key = 'advisory:' + candidate.id
    const token = start(key)
    setAdvisory({ phase: 'loading', result: null, error: '' })
    try {
      const result = await api.requestCandidateAdvisory(candidate.id)
      if (current(key, token)) {
        setAdvisory({ phase: result.eligibility.eligible ? 'success' : 'bypass', result, error: '' })
      }
    } catch (error) {
      if (current(key, token)) setAdvisory({ phase: 'error', result: null, error: error.message })
    }
  }

  const interpret = async (side, context, rawValue) => {
    if (!rawValue?.trim()) return
    const key = difficultValueStateKey(candidate.id, side, context)
    if (interpretations[key]?.phase === 'loading') return
    const token = start(key)
    setInterpretations(currentState => ({
      ...currentState,
      [key]: { phase: 'loading', result: null, error: '' },
    }))
    try {
      const result = await api.interpretDifficultValue(rawValue, context)
      if (current(key, token)) {
        setInterpretations(currentState => ({
          ...currentState,
          [key]: { phase: 'success', result, error: '' },
        }))
      }
    } catch (error) {
      if (current(key, token)) {
        setInterpretations(currentState => ({
          ...currentState,
          [key]: { phase: 'error', result: null, error: error.message },
        }))
      }
    }
  }

  const fields = [
    ['A', 'Part number A', 'PART_NO', candidate.part_no_a],
    ['A', 'Description A', 'DESCRIPTION', candidate.description_a],
    ['B', 'Part number B', 'PART_NO', candidate.part_no_b],
    ['B', 'Description B', 'DESCRIPTION', candidate.description_b],
  ]

  return (
    <section className="llm-tools" aria-label="Optional LLM assistance">
      <div className="llm-heading">
        <div><p className="eyebrow">Optional assistance</p><h3>LLM advisory</h3></div>
        <button type="button" onClick={requestAdvisory} disabled={advisory.phase === 'loading'} aria-busy={advisory.phase === 'loading'}>
          {advisory.phase === 'loading' ? 'Requesting…' : advisory.phase === 'error' ? 'Retry advisory' : candidate.llm_triage_state === 'AVAILABLE' ? 'Re-evaluate candidate' : 'Request candidate advisory'}
        </button>
      </div>
      <p className="llm-authority">{ADVISORY_AUTHORITY_LABEL}</p>
      {advisory.phase === 'error' && <p className="llm-error" role="alert">{advisory.error}</p>}
      {advisory.phase === 'bypass' && (
        <div className="llm-bypass" aria-live="polite">
          <b>No LLM advisory used</b>
          <span>{advisory.result.eligibility.reason}</span>
          <p>{advisory.result.eligibility.explanation}</p>
          <Metadata value={advisory.result.metadata} />
        </div>
      )}
      {advisory.phase === 'success' && (
        <div className="evidence-split" aria-live="polite">
          <article>
            <h4>{DETERMINISTIC_AUTHORITY_LABEL}</h4>
            <b>{candidate.business_status} · {candidate.confidence_level}</b>
            <span>Score {candidate.similarity_score}</span>
            <span>Rule {candidate.rule_decision}</span>
            {candidate.rejection_reason && <span>{candidate.rejection_reason}</span>}
            <p>{candidate.explanation}</p>
          </article>
          <article className="advisory-card">
            <h4>LLM advisory — non-authoritative</h4>
            <b>{advisory.result.advisory.assessment}</b>
            <span>Confidence {Math.round(advisory.result.advisory.confidence * 100)}%</span>
            <span>Recommended: {advisory.result.advisory.recommended_action}</span>
            <h5>Supporting evidence</h5>
            <ul>{advisory.result.advisory.supporting_evidence.map(item => <li key={item}>{item}</li>)}</ul>
            <h5>Conflicting evidence</h5>
            <ul>{advisory.result.advisory.conflicting_evidence.map(item => <li key={item}>{item}</li>)}</ul>
            <small>Deterministic authority confirmed: {advisory.result.advisory.deterministic_result_authoritative ? 'Yes' : 'No'}</small>
            <Metadata value={advisory.result.metadata} />
          </article>
        </div>
      )}

      <h4>Interpret a difficult visible value</h4>
      <div className="interpret-grid">
        {fields.map(([side, label, context, rawValue]) => {
          const key = difficultValueStateKey(candidate.id, side, context)
          const state = interpretations[key] || EMPTY
          return (
            <article key={key}>
              <b>{label}</b>
              <span className="raw-value">{rawValue || 'Not available'}</span>
              <button type="button" className="secondary" onClick={() => interpret(side, context, rawValue)} disabled={!rawValue?.trim() || state.phase === 'loading'} aria-busy={state.phase === 'loading'}>
                {state.phase === 'loading' ? 'Interpreting…' : state.phase === 'error' ? 'Retry interpretation' : 'Interpret value'}
              </button>
              <Interpretation state={state} rawValue={rawValue} />
            </article>
          )
        })}
      </div>
    </section>
  )
}

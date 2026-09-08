import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { deriveLlmStatus } from '../utils/llmUi'

export default function LlmStatus() {
  const [state, setState] = useState({ loading: true, status: null, failed: false })
  const requestId = useRef(0)

  useEffect(() => {
    const current = ++requestId.current
    api.getLlmStatus()
      .then(status => {
        if (requestId.current === current) setState({ loading: false, status, failed: false })
      })
      .catch(() => {
        if (requestId.current === current) setState({ loading: false, status: null, failed: true })
      })
    return () => { requestId.current += 1 }
  }, [])

  const display = state.loading
    ? { label: 'Checking', tone: 'off', detail: 'Loading optional LLM status.' }
    : deriveLlmStatus(state.status, state.failed)

  return (
    <aside className="llm-status" aria-live="polite" aria-busy={state.loading}>
      <span className={'llm-status-dot ' + display.tone} aria-hidden="true" />
      <div>
        <b>LLM assistance: {display.label}</b>
        <small>{display.detail}</small>
        {state.status && (
          <small>
            Cache {state.status.cache_enabled ? 'on' : 'off'} · Audit {state.status.audit_enabled ? 'on' : 'off'}
          </small>
        )}
      </div>
    </aside>
  )
}

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, options)
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try { const body = await response.json(); message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail || body) } catch {}
    throw new Error(message)
  }
  return response
}

export const api = {
  json: async (path, options) => (await request(path, options)).json(),
  get: (path) => api.json(path),
  postJson: (path, body) => api.json(path, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body) }),
  postForm: (path, body) => api.json(path, { method: 'POST', body }),
  download: async (path, filename, options) => {
    const blob = await (await request(path, options)).blob()
    const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url)
  },
  baseUrl: API,
}

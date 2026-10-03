const BASE = import.meta.env.VITE_API_BASE || ''

async function call(path, opts = {}) {
  const t0 = performance.now()
  const res = await fetch(`${BASE}${path}`, { headers: { 'Content-Type': 'application/json' }, ...opts })
  const seconds = (performance.now() - t0) / 1000
  if (!res.ok) {
    let detail = res.statusText
    try { detail = (await res.json()).detail || detail } catch (e) { /* ignore */ }
    throw new Error(`${res.status}: ${detail}`)
  }
  const data = await res.json()
  return { data, seconds }
}

export const api = {
  health: () => call('/api/health'),
  config: () => call('/api/config'),
  days: () => call('/api/days'),
  state: () => call('/api/demo/state'),
  current: () => call('/api/demo/current'),
  reset: (day) => call('/api/demo/reset', { method: 'POST', body: JSON.stringify({ day }) }),
  baseline: () => call('/api/plan/baseline', { method: 'POST' }),
  certify: () => call('/api/plan/certify', { method: 'POST' }),
  scenario: (kind, params = {}, intraday = false, now = '11:00') =>
    call(`/api/scenario/${kind}`, { method: 'POST', body: JSON.stringify({ params, intraday, now }) }),
  requestSlot: (feeder, start) => call('/api/request-slot', { method: 'POST', body: JSON.stringify({ feeder, start }) }),
  explain: () => call('/api/explain/last'),
  forecast: (day) => call(`/api/forecast${day ? `?day=${day}` : ''}`),
  impact: () => call('/api/impact/summary'),
}

// Where the planning API lives.
// - Served by the backend itself (local run, Docker, the Render service): same origin, so '' (relative /api paths).
// - Hosted on Vercel (yuva-frntend.vercel.app, preview URLs, or any Vercel build): the Render service below.
// - VITE_API_BASE set at build time overrides both (e.g. a custom domain or another backend).
export const RENDER_API = 'https://yuva-backend-2i5n.onrender.com'

/* global __VERCEL_BUILD__ */
const onVercel = (typeof __VERCEL_BUILD__ !== 'undefined' && __VERCEL_BUILD__) ||
  (typeof window !== 'undefined' && window.location.hostname.endsWith('.vercel.app'))

export const BASE = import.meta.env.VITE_API_BASE ?? (onVercel ? RENDER_API : '')
export const REMOTE = BASE !== ''

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

/** Wait until the API answers. A sleeping free-tier instance holds the first request for up to about a minute;
 *  network errors and 5xx during start-up are retried. Resolves to the health payload or throws after `maxWaitMs`. */
export async function waitForApi(maxWaitMs = 150000) {
  const t0 = Date.now()
  let lastErr = null
  while (Date.now() - t0 < maxWaitMs) {
    try {
      const { data } = await api.health()
      if (data?.ok) return data
    } catch (e) { lastErr = e }
    await new Promise((r) => setTimeout(r, 3000))
  }
  throw lastErr || new Error('the planning server did not answer')
}

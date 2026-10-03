import React from 'react'

export const STATUS = {
  CERTIFIED: { word: 'CERTIFIED', cls: 'ok' },
  CERTIFIED_AFTER_TIGHTENING: { word: 'CERTIFIED · TIGHTENED', cls: 'ok' },
  CERTIFIED_WITH_RELAXATION: { word: 'CERTIFIED · RELAXED', cls: 'warn' },
  FALLBACK_BASELINE: { word: 'TIMETABLE ISSUED', cls: 'warn' },
  INFEASIBLE: { word: 'INFEASIBLE', cls: 'bad' },
}

export function statusOf(current) {
  const s = current?.certified?.status
  return STATUS[s] || { word: s || '—', cls: 'grey' }
}

function niceDay(iso) {
  if (!iso) return ''
  const d = new Date(`${iso}T00:00:00`)
  return d.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
}

export default function Rail({ current, config, busy, view, onView, onDay }) {
  const st = statusOf(current)
  const c = current?.certified
  const sub = c ? (c.rung === 'baseline_guard'
    ? `timetable kept · verifier ${c.verify?.ok ? 'no violations' : `${c.verify?.n_violations} violation(s)`}`
    : `${c.rung} · ${c.solve?.solve_time_s ?? '—'} s · verifier ${c.verify?.ok ? 'no violations' : `${c.verify?.n_violations ?? '—'} violation(s)`}`) : ''
  return (
    <header className="rail">
      <div className="rail__in">
        <div className="wordmark">
          <span className="wordmark__name">SUNFLOW</span>
          <span className="wordmark__tag">Same eight hours. Better eight hours.</span>
        </div>
        <div className="rail__mid">
          <div className="rail__site">
            <b>{config?.site?.name || 'Lamjana 33/11 kV substation'}</b>
            <span>{config?.site?.district || 'Latur'}, {config?.site?.state || 'Maharashtra'} · 5 MW solar · 4 agricultural feeders · {niceDay(current?.day)}</span>
          </div>
          <label className="rail__date">Operating day
            <input type="date" min="2025-01-01" max="2026-09-30" value={current?.day || '2025-10-20'} onChange={(e) => e.target.value && onDay(e.target.value)} aria-label="Operating day" />
          </label>
          <div className="tabs" role="tablist" aria-label="Views">
            <button className="tab" role="tab" aria-selected={view === 'plan'} onClick={() => onView('plan')}>Plan</button>
            <button className="tab" role="tab" aria-selected={view === 'evidence'} onClick={() => onView('evidence')}>Evidence</button>
          </div>
        </div>
        <div className="rail__status">
          {busy && <span className="busy"><span className="busy__dot" />{busy}…</span>}
          {current && (
            <div className="status" aria-live="polite">
              <div key={st.word} className={`status__word status__word--${st.cls}`}>{st.word}</div>
              <div className="status__sub">{sub}</div>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}

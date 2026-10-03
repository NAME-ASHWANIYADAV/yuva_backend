import React from 'react'

function spells(u) {
  const out = []; let s = null
  u.forEach((v, i) => { if (v === 1 && s === null) s = i; if (v === 0 && s !== null) { out.push([s, i]); s = null } })
  if (s !== null) out.push([s, u.length])
  return out
}
const pct = (b) => `${(b / 96) * 100}%`
const label = (b) => `${String(Math.floor((b * 15) / 60)).padStart(2, '0')}:${String((b * 15) % 60).padStart(2, '0')}`

export default function FeederGantt({ current, config }) {
  const feeders = config?.feeders || []
  const plan = current.plan.plan
  const base = current.baseline.plan
  const outages = current.scenario.feeder_outages || {}
  const failed = current.scenario.failed_dts || []
  return (
    <div className="gantt">
      {feeders.map((f) => {
        const p = plan[f.name] || []; const b = base[f.name] || []
        const pS = spells(p); const bS = spells(b)
        const fdFailed = failed.filter((d) => d.startsWith(f.name.replace(' ', '')))
        return (
          <div className="row" key={f.name}>
            <div className="lab"><b>{f.name}</b> <span className="pill">{f.pt}</span><small>{f.n_dts} DTs · {Math.round(f.installed_kva)} kVA{fdFailed.length ? ` · ${fdFailed[0]} FAILED` : ''}</small></div>
            <div>
              <div className="track" title="published slot (grey) and SUNFLOW plan (green)">
                {(outages[f.name] || []).map(([a, c], i) => <div key={`o${i}`} className="seg out" style={{ left: pct(a), width: pct(c - a) }} title={`unavailable ${label(a)}-${label(c)}`} />)}
                {bS.map(([a, c], i) => <div key={`b${i}`} className="seg base" style={{ left: pct(a), width: pct(c - a), height: '45%', top: 0 }} title={`published ${label(a)}-${label(c)}`} />)}
                {pS.map(([a, c], i) => <div key={`p${i}`} className="seg plan" style={{ left: pct(a), width: pct(c - a), height: '50%', top: '50%' }} title={`SUNFLOW ${label(a)}-${label(c)}`} />)}
              </div>
              <div className="kv">published {bS.map(([a, c]) => `${label(a)}-${label(c)}`).join(', ') || '—'} → plan {pS.map(([a, c]) => `${label(a)}-${label(c)}`).join(', ') || '— (no daytime supply)'} · {(p.reduce((x, y) => x + y, 0) * 0.25).toFixed(1)} h</div>
            </div>
          </div>
        )
      })}
      <div className="axis"><div /><div className="ticks">{[24, 32, 40, 48, 56, 64, 72].map((b) => <span key={b} style={{ left: pct(b) }}>{label(b)}</span>)}</div></div>
      <div className="legend"><span><i style={{ background: 'var(--base-soft)', border: '1px dashed var(--base)' }} />published Annexure-A slot</span><span><i style={{ background: 'var(--sun)' }} />SUNFLOW plan</span><span><i style={{ background: 'var(--heat-soft)' }} />feeder unavailable</span><span>window 07:30–17:30 · 8 h per feeder · starts ≥30 min apart</span></div>
    </div>
  )
}

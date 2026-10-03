import React from 'react'

const STATUS_CLASS = {
  CERTIFIED: 'ok', CERTIFIED_AFTER_TIGHTENING: 'ok', CERTIFIED_WITH_RELAXATION: 'warn',
  FALLBACK_BASELINE: 'warn', INFEASIBLE: 'bad',
}

export default function Header({ current, config, busy, onDay }) {
  const status = current?.certified?.status
  const site = config?.site?.name || 'Lamjana 33/11 kV substation'
  return (
    <div>
      <div className="header">
        <div>
          <h2>{site} <span className="pill">{config?.site?.district}, {config?.site?.state}</span></h2>
          <div className="meta">
            {current ? <>Operating day <b>{current.day}</b> · solar band: {current.forecast_source} · weather: {current.weather_source}</> : 'Loading…'}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <label className="meta">Day&nbsp;
            <input type="date" min="2025-01-01" max="2026-09-30" defaultValue={current?.day || '2025-10-20'} onChange={(e) => e.target.value && onDay(e.target.value)} />
          </label>
          {status && <span className={`badge ${STATUS_CLASS[status] || 'grey'}`}>{status.replaceAll('_', ' ')}</span>}
          {busy && <span className="spinner">⏳ {busy}…</span>}
        </div>
      </div>
      {current?.certified?.alert && <div className="alert">{current.certified.alert}</div>}
      {current?.scenario_kind && current.scenario_kind !== 'base' && (
        <div className="alert" style={{ background: '#eef4ff', borderColor: '#c9d8f5', color: '#163a7a' }}>
          Scenario: <b>{current.scenario_kind}</b> {Object.keys(current.scenario_params || {}).length ? JSON.stringify(current.scenario_params) : ''}
          {current.replan && <> · intra-day re-plan from block {current.replan.now_block}: {current.replan.changes_blocks} announced block(s) changed ({current.replan.changed_feeders.join(', ') || 'none'})</>}
        </div>
      )}
    </div>
  )
}

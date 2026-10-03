import React from 'react'

export default function IrrigationPanel({ current }) {
  const sc = current.scenario
  const pf = current.plan.per_feeder
  return (
    <div className="irr">
      {Object.entries(pf).map(([f, v]) => {
        const req = sc.irrigation_required_blocks?.[f] ?? 0
        const urg = sc.irrigation_urgency?.[f] ?? 0
        const on = v.blocks_on
        const share = Math.min(100, (on / 32) * 100)
        return (
          <div className="r" key={f}>
            <div><b>{f}</b><div className="u">urgency {(urg * 100).toFixed(0)}%</div></div>
            <div className="bar" title={`${on} blocks delivered, ${req} required today`}>
              <div style={{ width: `${share}%` }} />
              {req > 0 && <div className="req" style={{ left: `${Math.min(100, (req / 32) * 100)}%` }} />}
            </div>
            <div className="u">{(on * 0.25).toFixed(1)} h / {(req * 0.25).toFixed(1)} h need {v.shortfall_blocks > 0 ? <b style={{ color: 'var(--heat)' }}> short</b> : ''}</div>
          </div>
        )
      })}
      <div className="u">Bars: blocks of supply delivered (blue) vs today's FAO-56 requirement (tick). Supply hours are fixed at 8 h by rule; urgency orders feeders when limits force staggering. No claim that staggering saves water.</div>
    </div>
  )
}

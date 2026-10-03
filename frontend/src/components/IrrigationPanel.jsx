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
        return (
          <div className="irr__r" key={f}>
            <div><b>{f}</b><div className="irr__u">urgency {(urg * 100).toFixed(0)} %</div></div>
            <div className="irr__bar" title={`${on} blocks supplied, ${req} needed today`}>
              <i style={{ width: `${Math.min(100, (on / 32) * 100)}%` }} />
              {req > 0 && <b style={{ left: `${Math.min(100, (req / 32) * 100)}%` }} />}
            </div>
            <div className="irr__u">{(on * 0.25).toFixed(1)} h supplied · {(req * 0.25).toFixed(1)} h needed{v.shortfall_blocks > 0 ? <b className="bad"> · short</b> : ''}</div>
          </div>
        )
      })}
      <div className="irr__note">Blue bar: supply hours tomorrow. Black tick: water the crop needs today by FAO-56. Supply is fixed at 8 h by rule; urgency only orders feeders when limits force staggering. No claim that staggering saves water.</div>
    </div>
  )
}

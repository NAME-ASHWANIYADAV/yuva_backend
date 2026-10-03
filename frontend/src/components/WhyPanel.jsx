import React from 'react'

export default function WhyPanel({ current, decision }) {
  const lines = current.explanations || []
  const c = current.certified
  return (
    <div>
      {decision && (
        <div className={`decision${decision.accepted ? '' : ' decision--refused'}`} aria-live="polite">
          <div className="decision__head">
            <span className="decision__verdict">{decision.accepted ? 'GRANTED' : 'REFUSED'} · {decision.feeder} at {decision.requested}</span>
            {decision.alternative && !decision.accepted && <span className="num" style={{ fontSize: 12 }}>nearest feasible start {decision.alternative}</span>}
          </div>
          <div style={{ marginTop: 6 }}>{decision.reason}</div>
          {decision.blocking_families?.length > 0 && <div className="decision__kv">blocking rule{decision.blocking_families.length > 1 ? 's' : ''}: {decision.blocking_families.map((f) => f.replaceAll('_', ' ')).join(' · ')}</div>}
          {decision.facts?.pt_context && (
            <div className="decision__kv">{decision.facts.pt_context.pt} rating {decision.facts.pt_context.rating_kva} kVA · {decision.feeder} switching surge {decision.facts.pt_context.feeder_surge_kva} kVA · other feeders on {decision.facts.pt_context.pt} at P90 participation {decision.facts.pt_context.other_feeders_kva_at_p90} kVA</div>
          )}
          {decision.cost_delta_inr != null && <div className="decision__kv">daily cost changes by ₹{Math.round(decision.cost_delta_inr).toLocaleString('en-IN')}</div>}
          <div className="decision__mr">{decision.marathi}</div>
        </div>
      )}
      {lines.length ? (
        <ul className="facts">
          {lines.map((l, i) => <li key={i} className={l.startsWith('Optimiser alternative') ? 'alt' : ''}>{l}</li>)}
        </ul>
      ) : <div className="note">No explanation lines for this plan.</div>}
      {c.conflicts?.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <span className="eyebrow">Conflict attribution</span>
          <table className="t" style={{ marginTop: 6 }}>
            <thead><tr><th>rule family relaxed on its own</th><th>plan exists?</th></tr></thead>
            <tbody>{c.conflicts.map((x) => <tr key={x.family}><td>{x.family.replaceAll('_', ' ')}</td><td className={x.feasible_when_relaxed ? 'ok' : 'bad'}>{x.feasible_when_relaxed ? 'yes' : 'no'}</td></tr>)}</tbody>
          </table>
        </div>
      )}
    </div>
  )
}

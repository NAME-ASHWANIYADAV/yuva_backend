import React from 'react'

function Ladder({ ladder }) {
  if (!ladder?.length) return null
  return (
    <table className="ladder">
      <thead><tr><th>rung</th><th>tightening</th><th>solve</th><th>time (s)</th><th>margin °C</th><th>spells</th><th>verifier</th></tr></thead>
      <tbody>
        {ladder.map((r, i) => (
          <tr key={i}><td>{r.rung}</td><td>{r.tightening}</td><td>{r.solve_status}</td><td>{r.solve_time_s}</td><td>{r.thermal_margin_c}</td><td>{r.max_spells ?? 1}</td>
            <td>{r.verify ? (r.verify.ok ? 'OK' : Object.entries(r.verify.kinds).map(([k, v]) => `${k}×${v}`).join(', ')) : '—'}</td></tr>
        ))}
      </tbody>
    </table>
  )
}

export default function ExplainPanel({ current, decision, compact }) {
  const c = current.certified
  const bv = current.baseline_verify
  return (
    <div className="expl">
      {decision && (
        <div className={`decision ${decision.accepted ? '' : 'refused'}`}>
          <b>{decision.accepted ? 'GRANTED' : 'REFUSED'}</b> · {decision.feeder} requested {decision.requested}
          <div>{decision.reason}</div>
          {decision.facts?.pt_context && (
            <div className="kv">{decision.facts.pt_context.pt} rating {decision.facts.pt_context.rating_kva} kVA · {decision.feeder} switching surge {decision.facts.pt_context.feeder_surge_kva} kVA · other feeders on {decision.facts.pt_context.pt} at P90 participation {decision.facts.pt_context.other_feeders_kva_at_p90} kVA</div>
          )}
          {decision.blocking_families?.length > 0 && <div className="kv">blocking rules: {decision.blocking_families.join(', ')}</div>}
          {decision.alternative && <div>Nearest feasible start: <b>{decision.alternative}</b></div>}
          <div className="mr">{decision.marathi}</div>
        </div>
      )}
      <ul>{(current.explanations || []).map((e, i) => <li key={i}>{e}</li>)}</ul>
      {!compact && (
        <>
          <h4 style={{ marginTop: 12 }}>Certification ladder</h4>
          <Ladder ladder={c.ladder} />
          {c.conflicts?.length > 0 && (
            <div className="alert">Conflict attribution (which single rule family, when relaxed, restores feasibility): {c.conflicts.map((x) => `${x.family}: ${x.feasible_when_relaxed ? 'yes' : 'no'}`).join(' · ')}</div>
          )}
          <h4 style={{ marginTop: 12 }}>Independent verifier (pessimistic: ambient +{c.verify?.settings?.ambient_offset_c} °C, thermal ×{c.verify?.settings?.thermal_factor}, participation {c.verify?.settings?.participation}, solar {c.verify?.settings?.solar_quantile})</h4>
          <div className="kv">SUNFLOW plan: {c.verify?.ok ? 'no violations' : `${c.verify?.n_violations} violation(s): ${JSON.stringify(c.verify?.kinds)}`} · max hot-spot {c.verify?.summary?.max_hot_spot_c?.toFixed?.(1)} °C · PT-2 peak {(c.verify?.summary?.pt2_max_loading_frac * 100)?.toFixed?.(0)}%</div>
          <div className="kv">Published timetable under the same pessimistic check: {bv?.ok ? 'no violations' : `${bv?.n_violations} violation(s): ${JSON.stringify(bv?.kinds)}`} · max hot-spot {bv?.summary?.max_hot_spot_c?.toFixed?.(1)} °C · PT-2 peak {(bv?.summary?.pt2_max_loading_frac * 100)?.toFixed?.(0)}%</div>
          {c.solve?.binding && (
            <>
              <h4 style={{ marginTop: 12 }}>Binding constraints (solver facts)</h4>
              <div className="kv">PT at rating: {c.solve.binding.pt?.length || 0} block(s) · switching cap binding: {c.solve.binding.cap?.length || 0} block(s)</div>
              <table className="ladder"><thead><tr><th>thermal class</th><th>DTs</th><th>max hot-spot (planning band)</th><th>at</th><th>limit incl. margin</th><th>binding</th></tr></thead>
                <tbody>{(c.solve.binding.thermal || []).map((x, i) => <tr key={i}><td>{x.feeder} {x.rating_kva} kVA</td><td>{x.n_dts}</td><td>{x.max_hot_spot_c}</td><td>{String(Math.floor((x.block * 15) / 60)).padStart(2, '0')}:{String((x.block * 15) % 60).padStart(2, '0')}</td><td>{x.limit_c}</td><td>{x.binding ? 'yes' : 'no'}</td></tr>)}</tbody></table>
              <div className="kv">Model size: {c.solve.model_size?.binaries} binaries, {c.solve.model_size?.constraints} constraints · objective ₹{c.solve.objective?.toFixed?.(0)}</div>
            </>
          )}
          <h4 style={{ marginTop: 12 }}>Operator table</h4>
          <table className="ladder"><thead><tr><th>feeder</th><th>PT</th><th>published</th><th>plan</th><th>hours</th></tr></thead>
            <tbody>{current.operator.map((r) => <tr key={r.feeder}><td>{r.feeder}</td><td>{r.pt}</td><td>{r.published.join('–')}</td><td>{r.spells.map((s) => s.join('–')).join(', ') || '—'}</td><td>{r.hours}</td></tr>)}</tbody></table>
          <h4 style={{ marginTop: 12 }}>Farmer messages (generated, not sent)</h4>
          {Object.entries(current.messages).map(([f, m]) => <div key={f} className="decision"><b>{f}</b><div className="mr">{m.mr}</div><div className="kv">{m.en}</div></div>)}
        </>
      )}
    </div>
  )
}

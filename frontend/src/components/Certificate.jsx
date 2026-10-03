import React from 'react'

const hhmm = (b) => `${String(Math.floor((b * 15) / 60)).padStart(2, '0')}:${String((b * 15) % 60).padStart(2, '0')}`
const inr = (v) => `₹${Math.round(v || 0).toLocaleString('en-IN')}`

export default function Certificate({ current }) {
  const c = current.certified
  const bv = current.baseline_verify
  const v = c.verify
  const binding = c.solve?.binding
  const thermal = (binding?.thermal || []).filter((x) => x.rating_kva === 100 || x.binding)
  return (
    <div className="cert">
      <div className="cert__row"><span className="k">pessimistic check</span><span>ambient +{v?.settings?.ambient_offset_c} °C · thermal constants ×{v?.settings?.thermal_factor} · participation {v?.settings?.participation} · solar {String(v?.settings?.solar_quantile).toUpperCase()}</span></div>
      <div className="cert__row"><span className="k">SUNFLOW plan</span><span>{v?.ok ? <b className="ok">no violations</b> : <b className="bad">{v?.n_violations} violation(s): {Object.entries(v?.kinds || {}).map(([k, n]) => `${k} ×${n}`).join(', ')}</b>} · max hot-spot <span className="num">{v?.summary?.max_hot_spot_c?.toFixed?.(1)} °C</span> · PT-2 peak <span className="num">{Math.round((v?.summary?.pt2_max_loading_frac || 0) * 100)} %</span></span></div>
      <div className="cert__row"><span className="k">published timetable</span><span>{bv?.ok ? <b className="ok">no violations</b> : <b className="bad">{bv?.n_violations} violation(s): {Object.entries(bv?.kinds || {}).map(([k, n]) => `${k} ×${n}`).join(', ')}</b>} · max hot-spot <span className="num">{bv?.summary?.max_hot_spot_c?.toFixed?.(1)} °C</span> · PT-2 peak <span className="num">{Math.round((bv?.summary?.pt2_max_loading_frac || 0) * 100)} %</span></span></div>

      <div>
        <span className="eyebrow">Certification ladder</span>
        <table className="t" style={{ marginTop: 6 }}>
          <thead><tr><th>rung</th><th>solve</th><th className="num">time s</th><th className="num">spells</th><th>verifier</th></tr></thead>
          <tbody>
            {(c.ladder || []).map((r, i) => r.rung === 'baseline_guard' ? (
              <tr key={i}><td>baseline guard</td><td colSpan={4}>timetable verified: {inr(r.baseline_cost_inr)}/day vs best certified plan {inr(r.plan_cost_inr)}/day → {r.baseline_cost_inr <= r.plan_cost_inr ? 'timetable issued unchanged' : 'plan issued'}</td></tr>
            ) : (
              <tr key={i}><td>{r.rung.replaceAll('_', ' ')}{r.tightening ? ` · margin +${4 * r.tightening} °C` : ''}</td><td>{r.solve_status}</td><td className="num">{r.solve_time_s}</td><td className="num">{r.max_spells ?? 1}</td><td>{r.verify ? (r.verify.ok ? <span className="ok">OK</span> : <span className="bad">{Object.entries(r.verify.kinds).map(([k, n]) => `${k} ×${n}`).join(', ')}</span>) : '—'}</td></tr>
            ))}
          </tbody>
        </table>
      </div>

      {c.solve && (
        <div>
          <span className="eyebrow">Solver facts</span>
          <div className="cert__row" style={{ marginTop: 6 }}><span className="k">model</span><span className="num" style={{ fontSize: 12 }}>{c.solve.model_size?.binaries} admissible daily patterns · {c.solve.model_size?.constraints} coupling constraints · objective ₹{Math.round(c.solve.objective || 0).toLocaleString('en-IN')}{c.solve.gap != null ? ` · gap ${(c.solve.gap * 100).toFixed(1)} %` : ''}{c.solve.model_size?.warm_start_objective != null ? ` · heuristic start ₹${Math.round(c.solve.model_size.warm_start_objective).toLocaleString('en-IN')}` : ''}</span></div>
          <div className="cert__row"><span className="k">binding</span><span>PT at rating in <span className="num">{binding?.pt?.length || 0}</span> block(s) · switching cap binding in <span className="num">{binding?.cap?.length || 0}</span> block(s)</span></div>
          {thermal.length > 0 && (
            <table className="t" style={{ marginTop: 8 }}>
              <thead><tr><th>transformers</th><th className="num">peak °C</th><th>at</th><th className="num">limit</th><th className="num">schedules excluded by heat</th></tr></thead>
              <tbody>{thermal.map((x, i) => <tr key={i}><td>{x.feeder} · {x.n_dts} × {x.rating_kva} kVA</td><td className={`num ${x.binding ? 'warn' : ''}`}>{x.max_hot_spot_c}</td><td className="num">{hhmm(x.block)}</td><td className="num">{x.limit_c}</td><td className="num">{x.thermal_dropped ?? 0} / {x.candidates ?? 0}</td></tr>)}</tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}

import React from 'react'

const f1 = (v, d = 1) => (v == null ? '—' : Number(v).toLocaleString('en-IN', { maximumFractionDigits: d }))
const isFrac = (name) => /frac/.test(name)
const cell = (name, q) => {
  if (!q || q.median == null) return '—'
  if (isFrac(name)) return `${f1(100 * q.median, 1)} % (${f1(100 * q.p10, 1)}–${f1(100 * q.p90, 1)})`
  return `${f1(q.median)} (${f1(q.p10)}–${f1(q.p90)})`
}
const LABELS = {
  import_kwh: 'grid import, kWh/day', import_nonsolar_kwh: 'import outside solar hours, kWh/day', surplus_kwh: 'solar not used on feeder, kWh/day',
  solar_used_frac_of_pv: 'solar used on feeder, % of PV', pt_overload_blocks: 'PT blocks over rating', pt2_max_loading_frac: 'PT-2 peak, % of rating',
  dt_max_hot_spot_c: 'hottest DT, °C', dt_exceedance_blocks: 'DT blocks over 120 °C', dt_ageing_hours_total: 'DT ageing, h/day',
  irrigation_shortfall_blocks: 'irrigation shortfall, blocks', switchings: 'switchings/day', import_kwh_per_ha: 'import per irrigated hectare, kWh/ha', import_cost_inr: 'import cost, ₹/day',
}

export default function ImpactPanel({ impact }) {
  if (!impact) return <section className="card"><div className="empty">Loading evidence…</div></section>
  const sweep = impact.sweep
  const certified = sweep ? (sweep.status_counts?.CERTIFIED || 0) + (sweep.status_counts?.CERTIFIED_WITH_RELAXATION || 0) + (sweep.status_counts?.CERTIFIED_AFTER_TIGHTENING || 0) : null
  return (
    <div className="evidence">
      <section className="card">
        <div className="card__head"><span className="eyebrow">Safety sweep</span><span className="src">results/safety/sweep.json · seeded, reproducible · <span className="tagchip tagchip--modelled">MODELLED</span></span></div>
        <div className="card__body">
          {sweep ? (
            <>
              <div className="stats">
                <div className="stat"><div className="stat__v">{sweep.n.toLocaleString('en-IN')}</div><div className="stat__l">random stress scenarios (participation 0.5–1.0, thermal ±30 %, ambient −2 to +6 °C, DT failures, outages)</div></div>
                <div className="stat"><div className="stat__v">{certified}</div><div className="stat__l">plans certified</div></div>
                <div className="stat"><div className="stat__v" style={{ color: sweep.certified_plans_with_violations === 0 ? 'var(--sun)' : 'var(--heat)' }}>{sweep.certified_plans_with_violations}</div><div className="stat__l">certified plans with a verifier violation</div></div>
                <div className="stat"><div className="stat__v">{sweep.status_counts?.INFEASIBLE || 0}</div><div className="stat__l">reported INFEASIBLE with conflict attribution, no plan fabricated</div></div>
                <div className="stat"><div className="stat__v">{sweep.status_counts?.FALLBACK_BASELINE || 0}</div><div className="stat__l">fell back to the published timetable within the time budget</div></div>
                <div className="stat"><div className="stat__v">{f1(sweep.median_solve_s, 1)}<small style={{ fontSize: 13, fontWeight: 500, color: 'var(--ink-3)' }}> s</small></div><div className="stat__l">median certification time (P90 {f1(sweep.p90_solve_s, 0)} s)</div></div>
              </div>
            </>
          ) : <div className="note">Run <span className="num">scripts/safety_sweep.py</span> to generate the sweep.</div>}
        </div>
      </section>

      <section className="card">
        <div className="card__head"><span className="eyebrow">Published timetable vs SUNFLOW over real weather</span><span className="src">results/experiments · median (P10–P90) per day · <span className="tagchip tagchip--modelled">MODELLED</span></span></div>
        <div className="card__body">
          {!impact.available ? <div className="note">{impact.note}</div> : (
            <>
              <div className="note" style={{ marginTop: 0 }}>{impact.description} Years {JSON.stringify(impact.years)}, {impact.n_days} real weather days, {impact.n_scenarios} scenarios. Each column adds one component to the previous one; the last is the full system. Import includes night-compensation energy.</div>
              <div className="tablewrap">
                <table className="t">
                  <thead><tr><th>metric</th>{impact.variants.map((v) => <th key={v} className="num">{v.replaceAll('_', ' ')}</th>)}</tr></thead>
                  <tbody>
                    {Object.entries(impact.metrics || {}).map(([name, row]) => (
                      <tr key={name}><td>{LABELS[name] || name}</td>{impact.variants.map((v) => <td key={v} className="num">{cell(name, row[v])}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {impact.ablation && (
                <div className="tablewrap">
                  <table className="t">
                    <thead><tr><th>variant</th>{Object.keys(impact.ablation[Object.keys(impact.ablation)[0]] || {}).map((k) => <th key={k} className="num">{k.replaceAll('_', ' ')}</th>)}</tr></thead>
                    <tbody>{Object.entries(impact.ablation).map(([v, row]) => <tr key={v}><td>{v.replaceAll('_', ' ')}</td>{Object.values(row).map((x, i) => <td key={i} className="num">{f1(x, 2)}</td>)}</tr>)}</tbody>
                  </table>
                </div>
              )}
              <div className="note">Status counts for the full system: {JSON.stringify(impact.status_counts)}. Paired per-scenario import delta (SUNFLOW − timetable): median {f1(impact.paired_delta_import_kwh?.median, 0)} kWh/day, P10 {f1(impact.paired_delta_import_kwh?.p10, 0)}, P90 {f1(impact.paired_delta_import_kwh?.p90, 0)}. The robust variants import more than the non-robust ones because they plan for P90 participation and buy compliance; that cost is shown, not hidden. Everything here is modelled on a synthetic feeder calibrated to MSEDCL norms; weather, forecasts and forecast errors are real.</div>
            </>
          )}
        </div>
      </section>
    </div>
  )
}

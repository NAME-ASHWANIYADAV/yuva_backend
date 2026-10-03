import React from 'react'

const fmt = (v, d = 0) => (v == null || Number.isNaN(v) ? '—' : Number(v).toLocaleString('en-IN', { maximumFractionDigits: d }))
const N = ({ children }) => <span className="num">{children}</span>

function sentence(current, config) {
  const b = current.baseline.metrics
  const p = current.plan.metrics
  const c = current.certified
  const site = (config?.site?.name || 'Lamjana').split(' ')[0]
  const delta = ((p.import_kwh - b.import_kwh) / Math.max(b.import_kwh, 1)) * 100
  const deltaTxt = Math.abs(delta) < 0.5 ? 'about the same' : `${delta < 0 ? '−' : '+'}${Math.abs(delta).toFixed(0)} %`
  const fams = (c.conflicts || []).filter((x) => x.feasible_when_relaxed).map((x) => x.family.replaceAll('_', ' '))
  if (c.status === 'INFEASIBLE') {
    return <>No plan satisfies every hard rule for {site} tomorrow under the declared assumptions, so the published timetable is issued with an alert. {fams.length ? <>Relaxing <b>{fams.join(' or ')}</b> alone would restore feasibility.</> : 'No single rule family restores feasibility on its own.'}</>
  }
  if (c.status === 'FALLBACK_BASELINE') {
    return <>The optimiser could not certify a plan for {site} tomorrow, so the published timetable is issued with an alert. Import stays at <N>{fmt(b.import_kwh)} kWh</N>; the verifier {current.baseline_verify?.ok ? 'passes' : 'flags'} the timetable itself.</>
  }
  if (c.rung === 'baseline_guard') {
    const g = (c.ladder || []).find((e) => e.rung === 'baseline_guard') || {}
    return <>Tomorrow the published timetable already passes the independent check and costs <N>₹{fmt(g.baseline_cost_inr)}</N> against <N>₹{fmt(g.plan_cost_inr)}</N> for the best certified alternative, so {site} keeps its timetable unchanged. Nothing is changed when a change buys no safety and costs money.</>
  }
  const nightH = Object.values(c.night_comp || {}).reduce((a, x) => a + x, 0) / 4
  return <>Tomorrow {site} imports <N>{fmt(p.import_kwh)} kWh</N> against <N>{fmt(b.import_kwh)}</N> on the published timetable ({deltaTxt}), uses <N>{fmt(p.solar_used_frac_of_pv * 100)} %</N> of its solar, peaks PT-2 at <N>{fmt(p.pt2_max_loading_frac * 100)} %</N> of rating and keeps every transformer under <N>{fmt(p.dt_max_hot_spot_c)} °C</N>.{nightH > 0 ? <> It uses <N>{nightH.toFixed(2)} h</N> of night compensation, counted as import.</> : ''} Certified at the <b>{c.rung.replaceAll('_', ' ')}</b> rung in <N>{c.solve?.solve_time_s ?? '—'} s</N>; the independent verifier found {c.verify?.ok ? 'no violations' : `${c.verify?.n_violations} violation(s)`}.</>
}

export default function Verdict({ current, config, showBaseline, actions, busy }) {
  const b = current.baseline.metrics
  const p = current.plan.metrics
  const c = current.certified
  const dis = !!busy
  const nightH = Object.values(c.night_comp || {}).reduce((a, x) => a + x, 0) / 4
  const kpi = (l, v, unit, base, better, dtxt) => ({ l, v, unit, base, better, dtxt })
  const kpis = [
    kpi('Grid import', fmt(p.import_kwh), 'kWh', fmt(b.import_kwh), p.import_kwh < b.import_kwh - 1, `${p.import_kwh - b.import_kwh < 0 ? '−' : '+'}${fmt(Math.abs(p.import_kwh - b.import_kwh))}`),
    kpi('Outside solar hours', fmt(p.import_nonsolar_kwh), 'kWh', fmt(b.import_nonsolar_kwh), p.import_nonsolar_kwh < b.import_nonsolar_kwh - 1, `${p.import_nonsolar_kwh - b.import_nonsolar_kwh < 0 ? '−' : '+'}${fmt(Math.abs(p.import_nonsolar_kwh - b.import_nonsolar_kwh))}`),
    kpi('Solar used on feeder', fmt(p.solar_used_frac_of_pv * 100), '%', `${fmt(b.solar_used_frac_of_pv * 100)} %`, p.solar_used_frac_of_pv > b.solar_used_frac_of_pv + 0.001, `${((p.solar_used_frac_of_pv - b.solar_used_frac_of_pv) * 100).toFixed(1)} pt`),
    kpi('PT-2 peak', fmt(p.pt2_max_loading_frac * 100), '% of 5 MVA', `${fmt(b.pt2_max_loading_frac * 100)} %`, p.pt2_max_loading_frac <= b.pt2_max_loading_frac, `${((p.pt2_max_loading_frac - b.pt2_max_loading_frac) * 100).toFixed(0)} pt`),
    kpi('Hottest transformer', fmt(p.dt_max_hot_spot_c, 1), '°C', `${fmt(b.dt_max_hot_spot_c, 1)} °C`, p.dt_max_hot_spot_c <= b.dt_max_hot_spot_c, `${(p.dt_max_hot_spot_c - b.dt_max_hot_spot_c).toFixed(1)} °C`),
    kpi('Transformer ageing', fmt(p.dt_ageing_hours_total, 1), 'h', `${fmt(b.dt_ageing_hours_total, 1)} h`, p.dt_ageing_hours_total <= b.dt_ageing_hours_total, `${(((p.dt_ageing_hours_total - b.dt_ageing_hours_total) / Math.max(b.dt_ageing_hours_total, 1e-6)) * 100).toFixed(0)} %`),
    kpi('Switchings', `${p.switchings}`, nightH > 0 ? `· ${nightH.toFixed(1)} h night` : '', `${b.switchings}`, p.switchings <= b.switchings, ''),
  ]
  const kind = current.scenario_kind && current.scenario_kind !== 'base' ? current.scenario_kind.replaceAll('_', ' ') : null
  return (
    <div>
      <div className="verdict">
        <p className="verdict__text">{sentence(current, config)}</p>
        <div className="verdict__actions">
          <button className="btn" disabled={dis} onClick={actions.baseline} aria-pressed={showBaseline}>{showBaseline ? 'Hide today’s timetable' : 'Show today’s timetable'}</button>
          <button className="btn btn--primary" disabled={dis} onClick={actions.certify}>Plan tomorrow</button>
        </div>
      </div>
      {kind && (
        <div className="verdict__alert verdict__alert--info">
          What-if <b>{kind}</b>{current.scenario_params && Object.keys(current.scenario_params).length ? ` · ${Object.entries(current.scenario_params).map(([k, v]) => `${k.replaceAll('_', ' ')} ${v}`).join(', ')}` : ''}{current.weather_source && current.weather_source !== 'era5 (reanalysis, PUBLIC)' ? ` · ${current.weather_source}` : ''}
          {current.replan && <> · intra-day re-plan from block {current.replan.now_block}: {current.replan.changes_blocks} announced block(s) changed ({current.replan.changed_feeders.join(', ') || 'none'})</>}
        </div>
      )}
      {c.alert && <div className={`verdict__alert ${c.status === 'INFEASIBLE' ? 'verdict__alert--bad' : ''}`}>{c.alert}</div>}
      <div className="kpis">
        {kpis.map((k) => (
          <div className="kpi" key={k.l}>
            <div className="kpi__l">{k.l}</div>
            <div className="kpi__v">{k.v}<small>{k.unit}</small></div>
            <div className="kpi__b">timetable {k.base} {k.dtxt && <span className={`kpi__d ${Math.abs(parseFloat(k.dtxt.replace('−', '-').replace(/,/g, ''))) < 0.05 ? 'kpi__d--flat' : k.better ? 'kpi__d--good' : 'kpi__d--bad'}`}>{Math.abs(parseFloat(k.dtxt.replace('−', '-').replace(/,/g, ''))) < 0.05 ? 'same' : k.dtxt}</span>}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

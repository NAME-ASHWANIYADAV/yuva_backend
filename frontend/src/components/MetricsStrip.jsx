import React from 'react'

const fmt = (v, d = 0) => (v == null || Number.isNaN(v) ? '—' : Number(v).toLocaleString('en-IN', { maximumFractionDigits: d }))

export default function MetricsStrip({ current }) {
  const b = current.baseline.metrics
  const p = current.plan.metrics
  const items = [
    { l: 'Grid import (kWh)', v: fmt(p.import_kwh), base: fmt(b.import_kwh), better: p.import_kwh < b.import_kwh, d: `${(((p.import_kwh - b.import_kwh) / Math.max(b.import_kwh, 1)) * 100).toFixed(0)}%` },
    { l: 'Import outside solar hours (kWh)', v: fmt(p.import_nonsolar_kwh), base: fmt(b.import_nonsolar_kwh), better: p.import_nonsolar_kwh < b.import_nonsolar_kwh, d: `${fmt(p.import_nonsolar_kwh - b.import_nonsolar_kwh)}` },
    { l: 'Solar used on feeder', v: `${fmt(p.solar_used_frac_of_pv * 100)}%`, base: `${fmt(b.solar_used_frac_of_pv * 100)}%`, better: p.solar_used_frac_of_pv > b.solar_used_frac_of_pv, d: `${((p.solar_used_frac_of_pv - b.solar_used_frac_of_pv) * 100).toFixed(1)} pt` },
    { l: 'PT-2 peak loading', v: `${fmt(p.pt2_max_loading_frac * 100)}%`, base: `${fmt(b.pt2_max_loading_frac * 100)}%`, better: p.pt2_max_loading_frac <= b.pt2_max_loading_frac, d: `${((p.pt2_max_loading_frac - b.pt2_max_loading_frac) * 100).toFixed(0)} pt` },
    { l: 'Max DT hot-spot (°C)', v: fmt(p.dt_max_hot_spot_c, 1), base: fmt(b.dt_max_hot_spot_c, 1), better: p.dt_max_hot_spot_c <= b.dt_max_hot_spot_c, d: `${(p.dt_max_hot_spot_c - b.dt_max_hot_spot_c).toFixed(1)} °C` },
    { l: 'DT ageing (hours)', v: fmt(p.dt_ageing_hours_total, 1), base: fmt(b.dt_ageing_hours_total, 1), better: p.dt_ageing_hours_total <= b.dt_ageing_hours_total, d: `${(((p.dt_ageing_hours_total - b.dt_ageing_hours_total) / Math.max(b.dt_ageing_hours_total, 1e-6)) * 100).toFixed(0)}%` },
    { l: 'Import per hectare (kWh/ha)', v: fmt(p.import_kwh_per_ha, 2), base: fmt(b.import_kwh_per_ha, 2), better: p.import_kwh_per_ha < b.import_kwh_per_ha, d: `${(p.import_kwh_per_ha - b.import_kwh_per_ha).toFixed(2)}` },
    { l: 'Switchings · changes vs announced', v: `${p.switchings} · ${p.changes_vs_announced_blocks}`, base: `${b.switchings}`, better: true, d: '' },
  ]
  return (
    <div className="metrics">
      {items.map((it) => (
        <div className="metric" key={it.l}>
          <div className="l">{it.l}</div>
          <div className="v">{it.v}</div>
          <div className="b">published: {it.base} <span className={`d ${it.d === '' ? 'neutral' : it.better ? 'good' : 'badd'}`}>{it.d}</span></div>
        </div>
      ))}
      <div className="metric" style={{ background: '#fff8e1' }}>
        <div className="l">Status</div>
        <div className="v" style={{ fontSize: 14 }}>{current.certified.status.replaceAll('_', ' ')}</div>
        <div className="b">rung: {current.certified.rung} · solve {current.certified.solve?.solve_time_s ?? '—'} s · verify {current.certified.verify?.ok ? 'OK' : `${current.certified.verify?.n_violations ?? '—'} violation(s)`}</div>
      </div>
    </div>
  )
}

import React from 'react'

const f1 = (v, d = 1) => (v == null ? '—' : Number(v).toLocaleString('en-IN', { maximumFractionDigits: d }))
const isFrac = (name) => /frac/.test(name)
const cell = (name, q) => {
  if (!q || q.median == null) return '—'
  if (isFrac(name)) return `${f1(100 * q.median, 1)}% (${f1(100 * q.p10, 1)}–${f1(100 * q.p90, 1)})`
  return `${f1(q.median)} (${f1(q.p10)}–${f1(q.p90)})`
}
const label = (name) => (isFrac(name) ? name.replace('_frac', ' %').replace('_of_pv', ' of PV').replace('_', ' ') : name)

export default function ImpactPanel({ impact }) {
  if (!impact) return <div className="kv">Loading…</div>
  if (!impact.available) return <div className="alert">{impact.note}</div>
  const metrics = impact.metrics || {}
  const variants = impact.variants || []
  return (
    <div>
      <div className="kv" style={{ marginBottom: 8 }}>{impact.description}</div>
      <table>
        <thead><tr><th>metric (per day)</th>{variants.map((v) => <th key={v}>{v}</th>)}</tr></thead>
        <tbody>
          {Object.entries(metrics).map(([name, row]) => (
            <tr key={name}><td>{label(name)}</td>{variants.map((v) => <td key={v}>{cell(name, row[v])}</td>)}</tr>
          ))}
        </tbody>
      </table>
      <div className="kv" style={{ marginTop: 8 }}>Median (P10–P90) over {impact.n_scenarios} seeded scenarios on {impact.n_days} real weather days of {impact.years}. Status counts: {JSON.stringify(impact.status_counts)}. Every number is MODELLED on a synthetic feeder calibrated to MSEDCL norms; weather and forecast errors are real.</div>
      {impact.ablation && (
        <>
          <h4 style={{ marginTop: 12 }}>Ablation: what each component contributes (median over scenarios)</h4>
          <table><thead><tr><th>variant</th>{Object.keys(impact.ablation[Object.keys(impact.ablation)[0]] || {}).map((k) => <th key={k}>{k}</th>)}</tr></thead>
            <tbody>{Object.entries(impact.ablation).map(([v, row]) => <tr key={v}><td>{v}</td>{Object.values(row).map((x, i) => <td key={i}>{f1(x, 2)}</td>)}</tr>)}</tbody></table>
        </>
      )}
    </div>
  )
}

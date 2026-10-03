import React, { useMemo } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid, ReferenceLine } from 'recharts'

function heatColor(t, limit) {
  if (t == null) return '#bdbdbd'
  if (t >= limit) return '#b71c1c'
  if (t >= limit - 10) return '#e65100'
  if (t >= limit - 25) return '#f9a825'
  return '#2e7d32'
}

export default function TransformerPanel({ current, showBaseline }) {
  const limit = 120
  const plan = current.plan
  const base = current.baseline
  const feeders = Object.keys(plan.feeder_kva)
  const { ptData, hotData, dtMax } = useMemo(() => {
    const ptData = plan.blocks.map((b, i) => ({
      t: b,
      pt1: (plan.pt_kva['PT-1'][i] / plan.pt_rating_kva['PT-1']) * 100,
      pt2: (plan.pt_kva['PT-2'][i] / plan.pt_rating_kva['PT-2']) * 100,
      bpt2: (base.pt_kva['PT-2'][i] / base.pt_rating_kva['PT-2']) * 100,
    }))
    const perFeeder = {}
    feeders.forEach((f) => { perFeeder[f] = new Array(96).fill(null) })
    const dtMax = {}
    Object.entries(plan.dt_hot_spot_c).forEach(([dt, series]) => {
      const f = plan.dt_feeder[dt]
      let m = null
      series.forEach((v, i) => { if (v != null) { m = m == null ? v : Math.max(m, v); perFeeder[f][i] = perFeeder[f][i] == null ? v : Math.max(perFeeder[f][i], v) } })
      dtMax[dt] = m
    })
    const hotData = plan.blocks.map((b, i) => { const row = { t: b }; feeders.forEach((f) => { row[f] = perFeeder[f][i] }); return row })
    return { ptData, hotData, dtMax }
  }, [current])
  const colors = ['#1b5e20', '#00897b', '#6a1b9a', '#ef6c00']
  const m = plan.metrics
  return (
    <div className="grid" style={{ gap: 10 }}>
      <div className="span6">
        <div className="kv">Power transformers (% of 5 MVA rating) · PT-2 peak {Math.round(m.pt2_max_loading_frac * 100)}% · overload blocks {m.pt_overload_blocks}</div>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={ptData} margin={{ top: 8, right: 12, left: -10, bottom: 0 }}>
            <CartesianGrid stroke="#eee" vertical={false} /><XAxis dataKey="t" interval={7} tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} unit="%" domain={[0, 120]} />
            <Tooltip formatter={(v) => `${Number(v).toFixed(0)}%`} /><Legend wrapperStyle={{ fontSize: 11 }} />
            <ReferenceLine y={100} stroke="var(--heat)" strokeDasharray="4 3" label={{ value: 'rating', fontSize: 10, fill: 'var(--heat)' }} />
            {showBaseline && <Line type="stepAfter" dataKey="bpt2" name="PT-2 · published" stroke="var(--base)" strokeDasharray="5 4" dot={false} isAnimationActive={false} />}
            <Line type="stepAfter" dataKey="pt2" name="PT-2 (Jawali, Lamjana II, Chalburga)" stroke="var(--heat)" dot={false} strokeWidth={2} isAnimationActive={false} />
            <Line type="stepAfter" dataKey="pt1" name="PT-1 (Kharosa)" stroke="#8e24aa" dot={false} strokeWidth={1.5} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="span6">
        <div className="kv">Hottest DT hot-spot per feeder (°C) · max {m.dt_max_hot_spot_c?.toFixed(1)} °C · blocks over 120 °C: {m.dt_exceedance_blocks} · ageing {m.dt_ageing_hours_total?.toFixed(1)} h</div>
        <ResponsiveContainer width="100%" height={200}>
          <LineChart data={hotData} margin={{ top: 8, right: 12, left: -10, bottom: 0 }}>
            <CartesianGrid stroke="#eee" vertical={false} /><XAxis dataKey="t" interval={7} tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} unit="°C" domain={[20, 130]} />
            <Tooltip formatter={(v) => `${Number(v).toFixed(1)} °C`} /><Legend wrapperStyle={{ fontSize: 11 }} />
            <ReferenceLine y={limit} stroke="var(--heat)" strokeDasharray="4 3" label={{ value: 'IEC 120 °C', fontSize: 10, fill: 'var(--heat)' }} />
            {feeders.map((f, i) => <Line key={f} type="monotone" dataKey={f} stroke={colors[i % colors.length]} dot={false} strokeWidth={1.6} isAnimationActive={false} connectNulls />)}
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div className="span12">
        <div className="kv" style={{ marginBottom: 4 }}>Every distribution transformer: peak hot-spot today (green &lt;95 °C · amber &lt;110 · orange &lt;120 · red ≥120 · grey = failed)</div>
        <div className="dtgrid">
          {Object.entries(dtMax).map(([dt, v]) => <div key={dt} className="dt" title={`${dt} · ${plan.dt_rating_kva[dt]} kVA · ${v == null ? 'failed' : v.toFixed(1) + ' °C'}`} style={{ background: heatColor(v, limit) }}>{plan.dt_rating_kva[dt]}</div>)}
        </div>
      </div>
    </div>
  )
}

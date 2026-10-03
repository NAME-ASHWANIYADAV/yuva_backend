import React, { useMemo } from 'react'
import { ComposedChart, LineChart, Area, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine, ReferenceArea } from 'recharts'
import { X0, X1, TICKS, WINDOW, label, pct, width, series, spells } from '../timeaxis.js'

const tick = { fontSize: 10.5, fontFamily: 'var(--mono)', fill: '#8a98a4' }
const tipStyle = { fontFamily: 'var(--mono)', fontSize: 11, borderRadius: 8, border: '1px solid #d8dfe5', boxShadow: '0 8px 24px -12px rgba(14,27,38,.3)' }
const FEEDER_COLORS = ['#0e1b26', '#4a6fa5', '#1d8a8a', '#7a3b8f']

function XAx({ show }) {
  return <XAxis type="number" dataKey="b" domain={[X0, X1]} ticks={TICKS} tickFormatter={label} tick={tick} axisLine={false} tickLine={false} height={show ? 20 : 0} hide={!show} allowDataOverflow minTickGap={28} />
}
const Window = () => <ReferenceArea x1={WINDOW[0]} x2={WINDOW[1]} fill="rgba(14,27,38,0.045)" strokeOpacity={0} />
const NowLine = ({ b }) => (b > 0 ? <ReferenceLine x={b} stroke="#2273b6" strokeWidth={2} /> : null)

function Row({ eyebrow, metrics, children }) {
  return (
    <>
      <div className="score__lab"><span className="eyebrow">{eyebrow}</span><div className="score__m">{metrics}</div></div>
      <div className="score__plot">{children}</div>
    </>
  )
}

export default function DayScore({ current, config, showBaseline }) {
  const sc = current.scenario
  const plan = current.plan
  const base = current.baseline
  const m = plan.metrics
  const now = current.replan ? current.replan.now_block : (sc.now_block || 0)
  const feeders = config?.feeders || Object.keys(plan.plan).map((name) => ({ name }))

  const solar = useMemo(() => series(96, (i) => ({
    band: sc.pv_p10_mw && sc.pv_p90_mw ? [sc.pv_p10_mw[i], sc.pv_p90_mw[i]] : null,
    p50: sc.pv_p50_mw[i],
    load: plan.load_kw[i] / 1000,
    baseLoad: base.load_kw[i] / 1000,
    imp: plan.import_kw[i] / 1000,
  })), [current])

  const pt = useMemo(() => series(96, (i) => ({
    pt1: (plan.pt_kva['PT-1'][i] / plan.pt_rating_kva['PT-1']) * 100,
    pt2: (plan.pt_kva['PT-2'][i] / plan.pt_rating_kva['PT-2']) * 100,
    bpt2: (base.pt_kva['PT-2'][i] / base.pt_rating_kva['PT-2']) * 100,
  })), [current])

  const { heat, dtMax, names } = useMemo(() => {
    const names = Object.keys(plan.feeder_kva)
    const per = {}
    names.forEach((f) => { per[f] = new Array(96).fill(null) })
    const dtMax = {}
    Object.entries(plan.dt_hot_spot_c).forEach(([dt, s]) => {
      const f = plan.dt_feeder[dt]
      let mx = null
      s.forEach((v, i) => { if (v != null) { mx = mx == null ? v : Math.max(mx, v); per[f][i] = per[f][i] == null ? v : Math.max(per[f][i], v) } })
      dtMax[dt] = mx
    })
    const heat = series(96, (i) => { const row = {}; names.forEach((f) => { row[f] = per[f][i] }); return row })
    return { heat, dtMax, names }
  }, [current])

  const night = current.certified?.night_comp || {}
  const outages = sc.feeder_outages || {}
  const failed = sc.failed_dts || []
  const sum = (a) => a.reduce((x, y) => x + y, 0)
  const pvKwh = m.pv_kwh

  return (
    <div className="score">
      <Row eyebrow="Solar & load" metrics={<><b>{Math.round(pvKwh).toLocaleString('en-IN')}</b> kWh solar<br /><b>{Math.round(m.import_kwh).toLocaleString('en-IN')}</b> kWh import<br />{Math.round(m.solar_used_frac_of_pv * 100)} % used on feeder</>}>
        <ResponsiveContainer width="100%" height={200}>
          <ComposedChart data={solar} margin={{ top: 6, right: 0, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="#eef2f5" vertical={false} />
            <Window /><NowLine b={now} />
            <XAx show={false} />
            <YAxis width={44} tick={tick} axisLine={false} tickLine={false} unit=" MW" />
            <Tooltip contentStyle={tipStyle} labelFormatter={label} formatter={(v, n) => [Array.isArray(v) ? `${v[0].toFixed(2)}–${v[1].toFixed(2)} MW` : `${Number(v).toFixed(2)} MW`, n]} />
            <Area type="monotone" dataKey="band" name="solar P10–P90" stroke="none" fill="var(--solar-soft)" isAnimationActive={false} />
            <Line type="monotone" dataKey="p50" name="solar P50" stroke="var(--solar)" dot={false} strokeWidth={2} isAnimationActive={false} />
            {showBaseline && <Line type="stepAfter" dataKey="baseLoad" name="load · published timetable" stroke="var(--base)" strokeDasharray="5 4" dot={false} strokeWidth={2} isAnimationActive={false} />}
            <Line type="stepAfter" dataKey="load" name="load · SUNFLOW plan" stroke="var(--sun)" dot={false} strokeWidth={2.2} isAnimationActive={false} />
            <Area type="stepAfter" dataKey="imp" name="grid import" stroke="var(--heat)" fill="var(--heat-soft)" strokeWidth={1.2} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
        <div className="score__legend"><span><i style={{ background: 'var(--solar-soft)' }} />solar P10–P90</span><span><i className="line" style={{ background: 'var(--solar)' }} />solar P50</span><span><i className="line" style={{ background: 'var(--sun)' }} />load, SUNFLOW plan</span>{showBaseline && <span><i className="dash" />load, published timetable</span>}<span><i style={{ background: 'var(--heat-soft)', border: '1px solid var(--heat)' }} />grid import</span><span><i style={{ background: 'var(--window)' }} />operating window 07:30–17:30</span></div>
      </Row>

      <Row eyebrow="Feeder spells" metrics={<>{feeders.length} feeders · 8 h each<br /><b>{m.switchings}</b> switchings<br />{sum(Object.values(night)) > 0 ? <><b>{(sum(Object.values(night)) / 4).toFixed(1)} h</b> night compensation</> : 'no night supply'}</>}>
        <div className="gantt">
          <div className="gantt__window" style={{ left: pct(WINDOW[0]), width: width(WINDOW[0], WINDOW[1]) }} />
          {now > 0 && <div className="gantt__now" style={{ left: pct(now) }} />}
          {feeders.map((f) => {
            const p = plan.plan[f.name] || []; const b = base.plan[f.name] || []
            const pS = spells(p); const bS = spells(b)
            const fdFailed = failed.filter((d) => d.startsWith(f.name.replace(' ', '')))
            const hrs = (sum(p) * 0.25).toFixed(1)
            return (
              <div className="gantt__row" key={f.name} title={`published ${bS.map(([a, c]) => `${label(a)}-${label(c)}`).join(', ') || '—'} → plan ${pS.map(([a, c]) => `${label(a)}-${label(c)}`).join(', ') || '—'}`}>
                <div className="gantt__name">{f.name}<small>{f.pt || ''}{f.n_dts ? ` · ${f.n_dts} DT` : ''} · {hrs} h{fdFailed.length ? ` · ${fdFailed[0]} failed` : ''}{night[f.name] > 0 ? ` · +${(night[f.name] / 4).toFixed(1)} h night` : ''}{pS.length ? '' : ' · no daytime supply'}</small></div>
                <div className="gantt__track">
                  {(outages[f.name] || []).map(([a, c], i) => <div key={`o${i}`} className="seg seg--out" style={{ left: pct(a), width: width(a, c) }} title={`unavailable ${label(a)}–${label(c)}`} />)}
                  {bS.map(([a, c], i) => <div key={`b${i}`} className="seg seg--base" style={{ left: pct(a), width: width(a, c) }} />)}
                  {pS.map(([a, c], i) => <div key={`p${i}`} className="seg seg--plan" style={{ left: pct(a), width: width(a, c) }} />)}
                </div>
              </div>
            )
          })}
          <div className="gantt__axis">{TICKS.map((b) => <span key={b} style={{ left: pct(b) }}>{label(b)}</span>)}</div>
        </div>
        <div className="score__legend"><span><i style={{ background: 'var(--base-soft)', border: '1px dashed var(--base)' }} />published Annexure-A slot <span className="tagchip tagchip--public">PUBLIC</span></span><span><i style={{ background: 'var(--sun)' }} />SUNFLOW plan</span><span><i style={{ background: 'var(--heat-soft)' }} />feeder unavailable</span><span>starts ≥ 30 min apart · PT rating · hot-spot limit</span></div>
      </Row>

      <Row eyebrow="Power transformers" metrics={<>PT-2 peak <b>{Math.round(m.pt2_max_loading_frac * 100)} %</b><br />PT-1 peak {Math.round((Math.max(...plan.pt_kva['PT-1']) / plan.pt_rating_kva['PT-1']) * 100)} %<br />{m.pt_overload_blocks} blocks over rating</>}>
        <ResponsiveContainer width="100%" height={150}>
          <LineChart data={pt} margin={{ top: 6, right: 0, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="#eef2f5" vertical={false} />
            <Window /><NowLine b={now} />
            <XAx show={false} />
            <YAxis width={44} tick={tick} axisLine={false} tickLine={false} unit="%" domain={[0, 120]} ticks={[0, 50, 100]} />
            <Tooltip contentStyle={tipStyle} labelFormatter={label} formatter={(v) => `${Number(v).toFixed(0)} %`} />
            <ReferenceLine y={100} stroke="var(--heat)" strokeDasharray="4 3" label={{ value: '5 MVA rating', fontSize: 10, fill: 'var(--heat)', position: 'insideTopLeft', fontFamily: 'var(--mono)' }} />
            {showBaseline && <Line type="stepAfter" dataKey="bpt2" name="PT-2 · published timetable" stroke="var(--base)" strokeDasharray="5 4" dot={false} isAnimationActive={false} />}
            <Line type="stepAfter" dataKey="pt2" name="PT-2 (Jawali, Lamjana II, Chalburga)" stroke="var(--heat)" dot={false} strokeWidth={2} isAnimationActive={false} />
            <Line type="stepAfter" dataKey="pt1" name="PT-1 (Kharosa)" stroke="#4a6fa5" dot={false} strokeWidth={1.6} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
        <div className="score__legend"><span><i className="line" style={{ background: 'var(--heat)' }} />PT-2 · Jawali, Lamjana II, Chalburga</span><span><i className="line" style={{ background: '#4a6fa5' }} />PT-1 · Kharosa</span>{showBaseline && <span><i className="dash" />PT-2, published timetable</span>}<span>rating <span className="tagchip tagchip--public">PUBLIC</span></span></div>
      </Row>

      <Row eyebrow="Transformer heat" metrics={<>hottest <b>{m.dt_max_hot_spot_c?.toFixed(1)} °C</b><br />{m.dt_exceedance_blocks} blocks over 120 °C<br />ageing <b>{m.dt_ageing_hours_total?.toFixed(1)} h</b> today</>}>
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={heat} margin={{ top: 6, right: 0, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="#eef2f5" vertical={false} />
            <Window /><NowLine b={now} />
            <XAx show />
            <YAxis width={44} tick={tick} axisLine={false} tickLine={false} unit="°" domain={[20, 130]} ticks={[40, 80, 120]} />
            <Tooltip contentStyle={tipStyle} labelFormatter={label} formatter={(v) => `${Number(v).toFixed(1)} °C`} />
            <ReferenceLine y={120} stroke="var(--heat)" strokeDasharray="4 3" label={{ value: 'IEC 60076-7 limit 120 °C', fontSize: 10, fill: 'var(--heat)', position: 'insideTopLeft', fontFamily: 'var(--mono)' }} />
            {names.map((f, i) => <Line key={f} type="monotone" dataKey={f} stroke={FEEDER_COLORS[i % FEEDER_COLORS.length]} dot={false} strokeWidth={1.6} isAnimationActive={false} connectNulls />)}
          </LineChart>
        </ResponsiveContainer>
        <div className="score__legend">{names.map((f, i) => <span key={f}><i className="line" style={{ background: FEEDER_COLORS[i % FEEDER_COLORS.length] }} />{f}, hottest DT</span>)}<span>constants <span className="tagchip tagchip--assumed">ASSUMED</span> ±30 %</span></div>
      </Row>

      <Row eyebrow="Every transformer" metrics={<>{Object.keys(dtMax).length} distribution transformers<br />63 and 100 kVA<br />peak hot-spot today</>}>
        <div className="dtgrid" style={{ marginLeft: 'var(--yaxis)' }}>
          {Object.entries(dtMax).map(([dt, v]) => (
            <div key={dt} className={`dt${v == null ? ' dt--failed' : ''}`} title={`${dt} · ${plan.dt_rating_kva[dt]} kVA · ${v == null ? 'failed' : `${v.toFixed(1)} °C`}`} style={v == null ? {} : { background: heatColor(v) }}>{plan.dt_rating_kva[dt]}</div>
          ))}
        </div>
        <div className="dt-legend" style={{ marginLeft: 'var(--yaxis)' }}><span><i style={{ background: '#178a52' }} />under 95 °C</span><span><i style={{ background: '#e08a00' }} />95 to 110</span><span><i style={{ background: '#d8432b' }} />110 to 120</span><span><i style={{ background: '#7a1d10' }} />120 or more</span><span><i className="dt--failed" style={{ width: 10, height: 10 }} />failed</span></div>
      </Row>
    </div>
  )
}

function heatColor(t) {
  if (t >= 120) return '#7a1d10'
  if (t >= 110) return '#d8432b'
  if (t >= 95) return '#e08a00'
  return '#178a52'
}

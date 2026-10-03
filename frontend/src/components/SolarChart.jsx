import React, { useMemo } from 'react'
import { ComposedChart, Area, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid } from 'recharts'

export default function SolarChart({ current, showBaseline }) {
  const data = useMemo(() => {
    const sc = current.scenario
    const plan = current.plan
    const base = current.baseline
    return plan.blocks.map((b, i) => ({
      t: b,
      p10: sc.pv_p10_mw ? sc.pv_p10_mw[i] : null,
      band: sc.pv_p10_mw && sc.pv_p90_mw ? [sc.pv_p10_mw[i], sc.pv_p90_mw[i]] : null,
      p50: sc.pv_p50_mw[i],
      load: plan.load_kw[i] / 1000,
      baseLoad: base.load_kw[i] / 1000,
      imp: plan.import_kw[i] / 1000,
      baseImp: base.import_kw[i] / 1000,
    }))
  }, [current])
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ComposedChart data={data} margin={{ top: 8, right: 12, left: -10, bottom: 0 }}>
        <CartesianGrid stroke="#eee" vertical={false} />
        <XAxis dataKey="t" interval={7} tick={{ fontSize: 11 }} />
        <YAxis tick={{ fontSize: 11 }} unit=" MW" />
        <Tooltip formatter={(v, n) => [Array.isArray(v) ? `${v[0].toFixed(2)}–${v[1].toFixed(2)} MW` : `${Number(v).toFixed(2)} MW`, n]} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Area type="monotone" dataKey="band" name="solar P10–P90" stroke="none" fill="var(--solar-soft)" isAnimationActive={false} />
        <Line type="monotone" dataKey="p50" name="solar P50" stroke="var(--solar)" dot={false} strokeWidth={2} isAnimationActive={false} />
        {showBaseline && <Line type="stepAfter" dataKey="baseLoad" name="load · published timetable" stroke="var(--base)" strokeDasharray="5 4" dot={false} strokeWidth={2} isAnimationActive={false} />}
        <Line type="stepAfter" dataKey="load" name="load · SUNFLOW plan" stroke="var(--sun)" dot={false} strokeWidth={2.2} isAnimationActive={false} />
        <Area type="stepAfter" dataKey="imp" name="grid import" stroke="var(--heat)" fill="var(--heat-soft)" isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}

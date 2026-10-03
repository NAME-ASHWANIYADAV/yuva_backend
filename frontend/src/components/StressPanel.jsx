import React, { useState } from 'react'

const SCENARIOS = [
  { kind: 'cloud_ramp', t: 'Cloud ramp', k: 'worst real midday ramp of 2025', color: 'var(--solar)', params: {} },
  { kind: 'heat_wave', t: 'Heat wave', k: 'hottest 2025 day + 3 °C', color: 'var(--heat)', params: { offset_c: 3 } },
  { kind: 'dt_failure', t: 'A transformer fails', k: '63 kVA unit on Chalburga', color: 'var(--heat)', params: {} },
  { kind: 'feeder_outage', t: 'Feeder outage', k: 'Kharosa 11:00–13:00', color: 'var(--ink-3)', params: { feeder: 'Kharosa', start: '11:00', end: '13:00' } },
  { kind: 'full_participation', t: 'Everyone switches on', k: 'participation 1.0', color: 'var(--amber)', params: {} },
  { kind: 'impossible', t: 'Impossible day', k: 'outage + heat · must say so', color: 'var(--heat)', params: {}, noIntraday: true },
]

export default function StressPanel({ actions, busy, log, config, current, showBaseline }) {
  const [feeder, setFeeder] = useState('Chalburga')
  const [start, setStart] = useState('07:30')
  const [intraday, setIntraday] = useState(false)
  const dis = !!busy
  const feeders = config?.feeders?.map((f) => f.name) || ['Kharosa', 'Jawali', 'Lamjana II', 'Chalburga']
  const times = []
  for (let b = 30; b <= 66; b += 2) times.push(`${String(Math.floor((b * 15) / 60)).padStart(2, '0')}:${String((b * 15) % 60).padStart(2, '0')}`)
  const active = current?.scenario_kind
  return (
    <>
      <section className="card">
        <div className="card__body">
          <span className="eyebrow">Plan</span>
          <div className="plan-actions">
            <button className="btn" disabled={dis} onClick={actions.baseline} aria-pressed={showBaseline}>{showBaseline ? 'Hide today’s timetable' : 'Show today’s timetable'}<span className="btn__k">Annexure-A</span></button>
            <button className="btn btn--primary" disabled={dis} onClick={actions.certify}>Plan tomorrow<span className="btn__k">solve + verify</span></button>
          </div>
        </div>
      </section>

      <section className="card">
        <div className="card__body">
          <span className="eyebrow">Stress the plan</span>
          <div className="stress">
            {SCENARIOS.map((s) => (
              <button key={s.kind} className="stress__item" disabled={dis} aria-pressed={active === s.kind} onClick={() => actions.scenario(s.kind, s.params, s.noIntraday ? false : intraday)}>
                <span className="stress__dot" style={{ background: s.color }} />
                <span><div className="stress__t">{s.t}</div><div className="stress__k">{s.k}</div></span>
              </button>
            ))}
          </div>
          <label className="switch"><input type="checkbox" checked={intraday} onChange={(e) => setIntraday(e.target.checked)} />Intra-day: keep announced blocks before 11:00 fixed</label>
        </div>
      </section>

      <section className="card">
        <div className="card__body">
          <span className="eyebrow">A farmer asks</span>
          <div className="ask">
            <label>Feeder<select value={feeder} onChange={(e) => setFeeder(e.target.value)}>{feeders.map((f) => <option key={f}>{f}</option>)}</select></label>
            <label>Wants to start at<select value={start} onChange={(e) => setStart(e.target.value)}>{times.map((t) => <option key={t}>{t}</option>)}</select></label>
            <button className="btn btn--water" disabled={dis} onClick={() => actions.request(feeder, start)}>Answer the farmer<span className="btn__k">IVR · press 1</span></button>
          </div>
        </div>
      </section>

      <section className="card">
        <div className="card__body">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <span className="eyebrow">Activity</span>
            <button className="btn btn--ghost btn--sm" disabled={dis} onClick={() => actions.reset()}>Reset day</button>
          </div>
          <div className="activity">
            {log.map((e, i) => <div className="activity__row" key={i}><span><b>{e.action}</b> · {e.detail} · {e.status}</span><span>{e.seconds?.toFixed ? e.seconds.toFixed(1) : e.seconds} s</span></div>)}
            {!log.length && <div className="activity__empty">Every action you take is listed here with the time the backend took.</div>}
          </div>
        </div>
      </section>
    </>
  )
}

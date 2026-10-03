import React, { useState } from 'react'

export default function DemoControls({ actions, busy, log, config, demoMode }) {
  const [feeder, setFeeder] = useState('Chalburga')
  const [start, setStart] = useState('07:30')
  const [intraday, setIntraday] = useState(false)
  const dis = !!busy
  const feeders = config?.feeders?.map((f) => f.name) || ['Kharosa', 'Jawali', 'Lamjana II', 'Chalburga']
  const times = []
  for (let b = 30; b <= 40; b++) times.push(`${String(Math.floor((b * 15) / 60)).padStart(2, '0')}:${String((b * 15) % 60).padStart(2, '0')}`)
  return (
    <aside className="side">
      <div className="brand"><h1>SUNFLOW</h1><span className="sub">{demoMode ? 'demo mode' : 'operator console'}</span></div>
      <div className="sub" style={{ fontSize: 12, color: '#bfd0c2' }}>Same eight hours. Better eight hours.</div>

      <h3>Plan</h3>
      <button className="btn base" disabled={dis} onClick={actions.baseline}>Replay published timetable <span className="k">baseline</span></button>
      <button className="btn primary" disabled={dis} onClick={actions.certify}>Certify SUNFLOW plan <span className="k">solve + verify</span></button>

      <h3>What if…</h3>
      <label style={{ fontSize: 12, display: 'block', margin: '4px 0 8px' }}><input type="checkbox" checked={intraday} onChange={(e) => setIntraday(e.target.checked)} /> intra-day (lock announced blocks up to 11:00)</label>
      <button className="btn solar" disabled={dis} onClick={() => actions.scenario('cloud_ramp', {}, intraday)}>Cloud ramp <span className="k">worst real 2025 day</span></button>
      <button className="btn heat" disabled={dis} onClick={() => actions.scenario('heat_wave', { offset_c: 3 }, intraday)}>Heat wave <span className="k">hottest 2025 day +3 °C</span></button>
      <button className="btn heat" disabled={dis} onClick={() => actions.scenario('dt_failure', {}, intraday)}>Fail a transformer <span className="k">Chalburga DT</span></button>
      <button className="btn" disabled={dis} onClick={() => actions.scenario('feeder_outage', { feeder: 'Kharosa', start: '11:00', end: '13:00' }, intraday)}>Fail feeder Kharosa <span className="k">11:00–13:00</span></button>
      <button className="btn" disabled={dis} onClick={() => actions.scenario('full_participation', {}, intraday)}>Everyone switches on <span className="k">participation 1.0</span></button>
      <button className="btn heat" disabled={dis} onClick={() => actions.scenario('impossible', {}, false)}>Impossible case <span className="k">outage + heat</span></button>

      <h3>Farmer request</h3>
      <div style={{ display: 'flex', gap: 6 }}>
        <select value={feeder} onChange={(e) => setFeeder(e.target.value)}>{feeders.map((f) => <option key={f}>{f}</option>)}</select>
        <select value={start} onChange={(e) => setStart(e.target.value)}>{times.map((t) => <option key={t}>{t}</option>)}</select>
      </div>
      <button className="btn water" disabled={dis} onClick={() => actions.request(feeder, start)}>Request this start <span className="k">IVR “press 1”</span></button>

      <h3>Explain</h3>
      <button className="btn" disabled={dis} onClick={actions.why}>Show why <span className="k">binding rules</span></button>
      <button className="btn" disabled={dis} onClick={actions.impactView}>Show impact <span className="k">experiments</span></button>
      <button className="btn base" disabled={dis} onClick={() => actions.reset()}>Reset day</button>

      <h3>Action log</h3>
      <div className="log">
        {log.map((e, i) => <div key={i}><span className="s">{e.action}</span> · {e.detail} · {e.seconds?.toFixed ? e.seconds.toFixed(1) : e.seconds}s · {e.status}</div>)}
        {!log.length && <div>No actions yet.</div>}
      </div>
    </aside>
  )
}

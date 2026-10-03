import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api.js'
import Rail from './components/Rail.jsx'
import Verdict from './components/Verdict.jsx'
import DayScore from './components/DayScore.jsx'
import WhyPanel from './components/WhyPanel.jsx'
import Certificate from './components/Certificate.jsx'
import Messages from './components/Messages.jsx'
import IrrigationPanel from './components/IrrigationPanel.jsx'
import StressPanel from './components/StressPanel.jsx'
import ImpactPanel from './components/ImpactPanel.jsx'
import Provenance from './components/Provenance.jsx'

export default function App() {
  const [config, setConfig] = useState(null)
  const [current, setCurrent] = useState(null)
  const [decision, setDecision] = useState(null)
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)
  const [log, setLog] = useState([])
  const [view, setView] = useState('plan')
  const [impact, setImpact] = useState(null)
  const [showBaseline, setShowBaseline] = useState(false)
  const whyRef = useRef(null)

  const push = useCallback((action, detail, seconds, status) => {
    setLog((l) => [{ action, detail, seconds, status, ts: Date.now() }, ...l].slice(0, 40))
  }, [])

  const run = useCallback(async (label, fn, after) => {
    setBusy(label); setError(null)
    try {
      const { data, seconds } = await fn()
      if (after) after(data, seconds)
      return data
    } catch (e) {
      setError(e.message); push(label, e.message, 0, 'ERROR')
    } finally { setBusy(null) }
  }, [push])

  useEffect(() => {
    api.config().then(({ data }) => setConfig(data)).catch((e) => setError(e.message))
    run('Loading the plan', api.current, (data, s) => { setCurrent(data); push('load', `day ${data.day}`, s, data.certified.status) })
    api.impact().then(({ data }) => setImpact(data)).catch(() => {})
  }, [run, push])

  const actions = useMemo(() => ({
    reset: (day) => run('Resetting the day', () => api.reset(day), (d, s) => { setCurrent(d); setDecision(null); setShowBaseline(false); setView('plan'); push('reset', `day ${d.day}`, s, d.certified.status) }),
    baseline: () => {
      if (showBaseline) { setShowBaseline(false); return }
      run('Replaying the published timetable', api.baseline, (d, s) => { setShowBaseline(true); setView('plan'); push('timetable', `${d.baseline_verify.ok ? 'passes' : 'fails'} the pessimistic check`, s, d.baseline_verify.ok ? 'OK' : 'VIOLATIONS') })
    },
    certify: () => run('Solving and verifying', api.certify, (d, s) => { setCurrent(d); setDecision(null); setShowBaseline(false); setView('plan'); push('plan', d.certified.rung, s, d.certified.status) }),
    scenario: (kind, params = {}, intraday = false) => run(`Running ${kind.replaceAll('_', ' ')}`, () => api.scenario(kind, params, intraday), (d, s) => { setCurrent(d); setDecision(null); setShowBaseline(false); setView('plan'); push(kind.replaceAll('_', ' '), d.weather_source || JSON.stringify(params), s, d.certified.status) }),
    request: (feeder, start) => run(`Answering ${feeder} for ${start}`, () => api.requestSlot(feeder, start), (d, s) => {
      setDecision(d); setView('plan'); push('farmer', `${feeder} ${start}: ${d.accepted ? 'granted' : 'refused'}`, s, d.accepted ? 'GRANTED' : 'REFUSED')
      setTimeout(() => whyRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
    }),
    evidence: () => { setView('evidence'); api.impact().then(({ data }) => setImpact(data)).catch(() => {}) },
    view: (v) => { setView(v); if (v === 'evidence') api.impact().then(({ data }) => setImpact(data)).catch(() => {}) },
  }), [run, push, showBaseline])

  return (
    <div className="shell">
      <Rail current={current} config={config} busy={busy} view={view} onView={actions.view} onDay={(d) => actions.reset(d)} />
      <div className="work">
        <main className="main">
          {error && <div className="error" role="alert">{error}. Reset the day and try again.</div>}
          {view === 'plan' && !current && <section className="card"><div className="empty">Loading tomorrow's plan…</div></section>}
          {view === 'plan' && current && (
            <>
              <section className="card"><div className="card__body"><Verdict current={current} config={config} showBaseline={showBaseline} actions={actions} busy={busy} /></div></section>
              <section className="card">
                <div className="card__head">
                  <span className="eyebrow">The day on one axis</span>
                  <span className="src">solar band <b>{current.forecast_source?.includes('learned') ? 'learned forecast-error model' : current.forecast_source}</b> · weather <b>{current.weather_source}</b> · load and temperatures <span className="tagchip tagchip--modelled">MODELLED</span></span>
                </div>
                <DayScore current={current} config={config} showBaseline={showBaseline} />
              </section>
              <div className="two">
                <section className="card" ref={whyRef}>
                  <div className="card__head"><span className="eyebrow">Why this plan</span><span className="src">every sentence is a number from the solver, the verifier or the simulation</span></div>
                  <div className="card__body"><WhyPanel current={current} decision={decision} /></div>
                </section>
                <section className="card">
                  <div className="card__head"><span className="eyebrow">Certificate</span><span className="src">independent verifier · never imports optimiser code</span></div>
                  <div className="card__body"><Certificate current={current} /></div>
                </section>
              </div>
              <div className="two">
                <section className="card">
                  <div className="card__head"><span className="eyebrow">Tomorrow's messages</span><span className="src">generated, not sent · Marathi first</span></div>
                  <div className="card__body"><Messages current={current} /></div>
                </section>
                <section className="card">
                  <div className="card__head"><span className="eyebrow">Water need vs supply</span><span className="src">FAO-56 <span className="tagchip tagchip--modelled">MODELLED</span> · crop calendar <span className="tagchip tagchip--assumed">ASSUMED</span></span></div>
                  <div className="card__body"><IrrigationPanel current={current} /></div>
                </section>
              </div>
            </>
          )}
          {view === 'evidence' && <ImpactPanel impact={impact} />}
        </main>
        <aside className="aside">
          <StressPanel actions={actions} busy={busy} log={log} config={config} current={current} showBaseline={showBaseline} />
        </aside>
      </div>
      <Provenance />
    </div>
  )
}

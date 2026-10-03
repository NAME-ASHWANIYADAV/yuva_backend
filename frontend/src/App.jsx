import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api.js'
import Header from './components/Header.jsx'
import SolarChart from './components/SolarChart.jsx'
import FeederGantt from './components/FeederGantt.jsx'
import TransformerPanel from './components/TransformerPanel.jsx'
import IrrigationPanel from './components/IrrigationPanel.jsx'
import MetricsStrip from './components/MetricsStrip.jsx'
import DemoControls from './components/DemoControls.jsx'
import ExplainPanel from './components/ExplainPanel.jsx'
import ImpactPanel from './components/ImpactPanel.jsx'
import Footer from './components/Footer.jsx'

export default function App() {
  const demoMode = typeof window !== 'undefined' && (window.location.pathname.startsWith('/demo') || window.location.hash.includes('demo'))
  const [config, setConfig] = useState(null)
  const [current, setCurrent] = useState(null)
  const [decision, setDecision] = useState(null)
  const [busy, setBusy] = useState(null)
  const [error, setError] = useState(null)
  const [log, setLog] = useState([])
  const [view, setView] = useState('plan')
  const [impact, setImpact] = useState(null)
  const [showBaseline, setShowBaseline] = useState(false)

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
    run('Loading plan for the default day', api.current, (data, s) => { setCurrent(data); push('load', `day ${data.day}`, s, data.certified.status) })
    api.impact().then(({ data }) => setImpact(data)).catch(() => {})
  }, [run, push])

  const actions = useMemo(() => ({
    reset: (day) => run('Resetting', () => api.reset(day), (d, s) => { setCurrent(d); setDecision(null); setShowBaseline(false); push('reset', `day ${d.day}`, s, d.certified.status) }),
    baseline: () => run('Replaying published timetable', api.baseline, (d, s) => { setShowBaseline(true); setView('plan'); push('replay baseline', `${d.baseline_verify.ok ? 'passes' : 'fails'} pessimistic verification`, s, d.baseline_verify.ok ? 'OK' : 'VIOLATIONS') }),
    certify: () => run('Solving and verifying', api.certify, (d, s) => { setCurrent(d); setShowBaseline(false); setView('plan'); push('certify', d.certified.rung, s, d.certified.status) }),
    scenario: (kind, params = {}, intraday = false) => run(`Running ${kind}`, () => api.scenario(kind, params, intraday), (d, s) => { setCurrent(d); setShowBaseline(false); setView('plan'); push(kind, d.weather_source || JSON.stringify(params), s, d.certified.status) }),
    request: (feeder, start) => run(`Evaluating request ${feeder} @ ${start}`, () => api.requestSlot(feeder, start), (d, s) => { setDecision(d); setView('why'); push('request', `${feeder} ${start}: ${d.accepted ? 'granted' : 'refused'}`, s, d.accepted ? 'GRANTED' : 'REFUSED') }),
    why: () => setView('why'),
    impactView: () => { setView('impact'); api.impact().then(({ data }) => setImpact(data)).catch(() => {}) },
  }), [run, push])

  return (
    <div className={`app${demoMode ? '' : ''}`}>
      <DemoControls actions={actions} busy={busy} log={log} config={config} demoMode={demoMode} />
      <main className="main">
        <Header current={current} config={config} busy={busy} onDay={(d) => actions.reset(d)} />
        {error && <div className="error">{error}</div>}
        {current && view === 'plan' && (
          <div className="grid">
            <div className="span12"><MetricsStrip current={current} /></div>
            <div className="span8 card"><h4>Solar, load and grid import <span className="tag">P10/P50/P90 from the learned forecast-error model · load MODELLED</span></h4><SolarChart current={current} showBaseline={showBaseline} /></div>
            <div className="span4 card"><h4>Irrigation requirement vs plan <span className="tag">FAO-56 · MODELLED</span></h4><IrrigationPanel current={current} /></div>
            <div className="span12 card"><h4>Feeder switching plan <span className="tag">grey = published Annexure-A slot (PUBLIC) · green = SUNFLOW</span></h4><FeederGantt current={current} config={config} /></div>
            <div className="span12 card"><h4>Transformers <span className="tag">PT rating PUBLIC · DT hot-spot IEC 60076-7 MODELLED (constants ASSUMED)</span></h4><TransformerPanel current={current} showBaseline={showBaseline} /></div>
            <div className="span12 card"><h4>Why this plan <span className="tag">solver facts only</span></h4><ExplainPanel current={current} decision={decision} compact /></div>
          </div>
        )}
        {current && view === 'why' && (
          <div className="grid"><div className="span12 card"><h4>Why <span className="tag">binding constraints · verifier · ladder</span></h4><ExplainPanel current={current} decision={decision} /></div></div>
        )}
        {view === 'impact' && (
          <div className="grid"><div className="span12 card impact"><h4>Impact: baseline vs SUNFLOW across scenarios <span className="tag">results/experiments · all MODELLED</span></h4><ImpactPanel impact={impact} /></div></div>
        )}
      </main>
      <Footer />
    </div>
  )
}

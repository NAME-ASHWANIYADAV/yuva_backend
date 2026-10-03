import React from 'react'

export default function Messages({ current }) {
  const night = current.certified?.night_comp || {}
  return (
    <div>
      <table className="t">
        <thead><tr><th>feeder</th><th>PT</th><th>published</th><th>plan</th><th className="num">hours</th></tr></thead>
        <tbody>
          {(current.operator || []).map((r) => (
            <tr key={r.feeder}><td>{r.feeder}</td><td>{r.pt}</td><td className="num">{r.published.join('–')}</td><td className="num">{r.spells.map((s) => s.join('–')).join(', ') || '—'}{night[r.feeder] > 0 ? ` + ${(night[r.feeder] / 4).toFixed(1)} h night` : ''}</td><td className="num">{r.hours}</td></tr>
          ))}
        </tbody>
      </table>
      <div className="msgs">
        {Object.entries(current.messages || {}).map(([f, m]) => (
          <div className="msg" key={f}>
            <div className="msg__f">{f}<span>SMS · IVR</span></div>
            <div className="msg__mr" lang="mr">{m.mr}</div>
            <div className="msg__en">{m.en}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

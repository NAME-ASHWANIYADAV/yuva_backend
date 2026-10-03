// One time axis for every row of the day score: 04:00 to 20:00 in 15-minute blocks (block b starts at b * 15 min).
export const X0 = 16
export const X1 = 80
export const SPAN = X1 - X0
export const WINDOW = [30, 70]                       // MSEDCL operating window 07:30-17:30
export const TICKS = [16, 24, 32, 40, 48, 56, 64, 72, 80]

export const label = (b) => `${String(Math.floor((b * 15) / 60)).padStart(2, '0')}:${String((b * 15) % 60).padStart(2, '0')}`
export const pct = (b) => `${((Math.min(Math.max(b, X0), X1) - X0) / SPAN) * 100}%`
export const width = (a, c) => `${((Math.min(c, X1) - Math.max(a, X0)) / SPAN) * 100}%`

/** Series for a numeric x-axis: one point per block from X0 to X1 (the last point repeats block X1 - 1). */
export function series(n, fill) {
  const out = []
  for (let b = X0; b <= X1; b++) out.push({ b, ...fill(Math.min(b, n - 1)) })
  return out
}

export function spells(u) {
  const out = []
  let s = null
  u.forEach((v, i) => { if (v === 1 && s === null) s = i; if (v === 0 && s !== null) { out.push([s, i]); s = null } })
  if (s !== null) out.push([s, u.length])
  return out
}

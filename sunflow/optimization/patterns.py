"""Admissible daily switching patterns per feeder (column formulation).

A pattern is a full-day on/off vector that already satisfies every rule that concerns one feeder alone:
operating window and outages, total supply blocks (8 h minus any night compensation), number and length of spells,
minimum off-time between spells, locked announced blocks, a forced start, the irrigation minimum and the
distribution-transformer hot-spot limit. The last one is exact: the IEC 60076-7 difference equations are evaluated for
every candidate with the planning ambient and the day's initial state, because a transformer's temperature depends on
its own feeder's pattern only. Ageing cost is likewise a per-pattern constant.

The MILP then picks exactly one pattern per feeder; only the coupling rules (power-transformer rating, switching cap,
start separation, import/surplus) remain as explicit constraints.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from .inputs import PlanInputs


@dataclass
class Pattern:
    u: np.ndarray          # 0/1 per block
    s: np.ndarray          # start indicators
    e: np.ndarray          # stop indicators (off from this block)
    sg: np.ndarray         # surge indicator (first `surge_blocks` blocks of each spell)
    n_on: int
    n_spells: int
    night: int             # night-compensation blocks implied (min_blocks - n_on)
    first_start: int
    spells: List[tuple]
    ageing_cost: float = 0.0                                   # rupees, from the exact thermal trajectory
    thermal: Dict[str, Tuple[float, int]] = field(default_factory=dict)   # class key -> (max hot-spot C, block)

    @property
    def switchings(self) -> int:
        return int(self.s.sum() + self.e.sum())


def _make(u: np.ndarray, inp: PlanInputs) -> Pattern:
    N = len(u)
    prev = np.concatenate([[0], u[:-1]])
    s = ((u == 1) & (prev == 0)).astype(int)
    e = ((u == 0) & (prev == 1)).astype(int)
    sg = np.zeros(N, dtype=int)
    for t in np.where(s == 1)[0]:
        sg[t:min(N, t + inp.surge_blocks)] = 1
    spells = []
    start = None
    for t in range(N):
        if u[t] == 1 and start is None:
            start = t
        if u[t] == 0 and start is not None:
            spells.append((start, t)); start = None
    if start is not None:
        spells.append((start, N))
    n_on = int(u.sum())
    return Pattern(u=u, s=s, e=e, sg=sg, n_on=n_on, n_spells=len(spells), night=inp.min_blocks - n_on,
                   first_start=int(spells[0][0]) if spells else -1, spells=spells)


def _night_options(inp: PlanInputs) -> List[int]:
    opts = [0]
    if inp.max_night_blocks >= 4:
        opts += list(range(4, inp.max_night_blocks + 1))
    return opts


def thermal_trajectories(U: np.ndarray, SG: np.ndarray, inp: PlanInputs, feeder: str) -> Dict[str, np.ndarray]:
    """Hot-spot trajectories (P x N) for every thermal class of `feeder`, for P candidate patterns, from the day's
    initial state with the planning ambient (exact zero-order-hold IEC 60076-7 recursion, see physics module)."""
    amb = np.asarray(inp.ambient_c, dtype=float)
    k21 = inp.thermal_params.k21
    out: Dict[str, np.ndarray] = {}
    P, N = U.shape
    for tc in inp.thermal_classes:
        if tc.feeder != feeder:
            continue
        g_o = tc.g_o["off"] + (tc.g_o["def"] - tc.g_o["off"]) * U + (tc.g_o["surge"] - tc.g_o["def"]) * SG
        g_h = tc.g_h["off"] + (tc.g_h["def"] - tc.g_h["off"]) * U + (tc.g_h["surge"] - tc.g_h["def"]) * SG
        st = inp.initial_state.get(tc.key, {})
        o = np.full(P, float(st.get("o", inp.init_oil_rise)))
        h1 = np.full(P, float(st.get("h1", 0.0)))
        h2 = np.full(P, float(st.get("h2", 0.0)))
        hot = np.empty((P, N))
        for t in range(N):
            o = inp.a_o * o + (1.0 - inp.a_o) * g_o[:, t]
            h1 = inp.a_h1 * h1 + (1.0 - inp.a_h1) * k21 * g_h[:, t]
            h2 = inp.a_h2 * h2 + (1.0 - inp.a_h2) * (k21 - 1.0) * g_h[:, t]
            hot[:, t] = amb[t] + o + h1 - h2
        out[tc.key] = hot
    return out


def enumerate_patterns(inp: PlanInputs, feeder: str, stats: Optional[dict] = None) -> List[Pattern]:
    N = inp.N
    avail = np.asarray(inp.avail[feeder], dtype=int)
    locked = None
    if inp.announced is not None and inp.lock_until > 0 and feeder in inp.announced:
        locked = np.minimum(np.asarray(inp.announced[feeder], dtype=int), avail)[: inp.lock_until]
    forced = inp.forced_starts.get(feeder)
    req = inp.irrigation_required[feeder] if (inp.options.use_irrigation and inp.options.irrigation_hard) else 0
    cands: List[Pattern] = []
    seen = set()

    def admit(u: np.ndarray) -> None:
        if np.any(u > avail):
            return
        if locked is not None and not np.array_equal(u[: inp.lock_until], locked):
            return
        key = u.tobytes()
        if key in seen:
            return
        p = _make(u, inp)
        if forced is not None and p.s[forced] != 1:
            return
        if p.n_on < req:
            return
        seen.add(key)
        cands.append(p)

    win = np.where(avail == 1)[0]
    st = {"candidates": 0, "thermal_dropped": 0, "kept": 0, "longest_single_spell_blocks": 0}
    if win.size == 0:
        if stats is not None:
            stats[feeder] = st
        return []
    lo, hi = int(win.min()), int(win.max()) + 1
    lattice = max(int(inp.options.split_lattice_blocks), 1)
    for night in _night_options(inp):
        total = inp.min_blocks - night
        if total <= 0:
            continue
        # one spell
        for a in range(lo, hi - total + 1):
            u = np.zeros(N, dtype=int); u[a:a + total] = 1
            admit(u)
        # two spells. Night compensation combined with a split is kept only at the cap and on a coarser lattice
        # (a split exists precisely to avoid night supply; this keeps the column set small).
        if inp.max_spells >= 2 and (night in (0, inp.max_night_blocks) or inp.options.split_night_options == "all"):
            step = lattice if night == 0 else 2 * lattice
            for L1 in range(inp.min_spell_blocks, total - inp.min_spell_blocks + 1):
                L2 = total - L1
                for a in range(lo, hi - total - inp.min_off_blocks + 1, step):
                    for gap in range(inp.min_off_blocks, hi - a - total + 1, step):
                        b = a + L1 + gap
                        if b + L2 > hi:
                            break
                        u = np.zeros(N, dtype=int); u[a:a + L1] = 1; u[b:b + L2] = 1
                        admit(u)
    st["candidates"] = len(cands)
    if not cands:
        if stats is not None:
            stats[feeder] = st
        return []

    # exact thermal evaluation of every candidate (vectorised over patterns)
    U = np.stack([p.u for p in cands]).astype(float)
    SG = np.stack([p.sg for p in cands]).astype(float)
    traj = thermal_trajectories(U, SG, inp, feeder)
    limit = inp.hot_spot_limit_c - inp.thermal_margin_c
    w_age = inp.weights.ageing_inr_per_deg_block
    mult = {tc.key: tc.multiplicity for tc in inp.thermal_classes}
    ok = np.ones(len(cands), dtype=bool)
    age = np.zeros(len(cands))
    for key, hot in traj.items():
        if inp.options.use_thermal:
            ok &= hot.max(axis=1) <= limit + 1e-9
        age += mult[key] * np.maximum(0.0, hot - inp.ageing_reference_c).sum(axis=1)
        for i, p in enumerate(cands):
            j = int(np.argmax(hot[i]))
            p.thermal[key] = (float(hot[i, j]), j)
    out: List[Pattern] = []
    for i, p in enumerate(cands):
        p.ageing_cost = float(w_age * age[i])
        if ok[i]:
            out.append(p)
            if p.n_spells == 1:
                st["longest_single_spell_blocks"] = max(st["longest_single_spell_blocks"], p.n_on)
    st["thermal_dropped"] = int((~ok).sum())
    st["kept"] = len(out)
    if stats is not None:
        stats[feeder] = st
    return out


def pattern_sets(inp: PlanInputs, stats: Optional[dict] = None) -> Dict[str, List[Pattern]]:
    return {f: enumerate_patterns(inp, f, stats) for f in inp.feeders}

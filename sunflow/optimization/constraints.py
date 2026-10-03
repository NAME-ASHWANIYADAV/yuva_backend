"""Hard constraints of the switching MILP. Each family can be toggled for ablations (SolveOptions)."""
from __future__ import annotations

import pyomo.environ as pyo

from .inputs import PlanInputs


def _surge_ind(m, f, t, inp: PlanInputs):
    """1 if block t is within the surge window after a start of feeder f (linear in s)."""
    return sum(m.s[f, t - k] for k in range(inp.surge_blocks) if t - k >= 0)


def load_kva_expr(m, f, t, inp: PlanInputs):
    base = inp.base_kva[f]
    return base * (inp.p_def * m.u[f, t] + (inp.p_surge - inp.p_def) * _surge_ind(m, f, t, inp))


def add_constraints(m: pyo.ConcreteModel, inp: PlanInputs) -> None:
    N = inp.N
    opt = inp.options

    # --- availability (window + outages): fix variables outside the window so presolve removes them --
    for f in inp.feeders:
        for t in range(N):
            if int(inp.avail[f][t]) == 0:
                m.u[f, t].fix(0)
                m.s[f, t].fix(0)

    # --- linking: a feeder can only be on within max_spell_len blocks after one of its starts ---------
    # (valid inequality that tightens the LP relaxation; total daily hours are exactly min_blocks)
    def c_link(m, f, t):
        lo = max(0, t - inp.min_blocks + 1)
        return m.u[f, t] <= sum(m.s[f, k] for k in range(lo, t + 1))
    m.c_link = pyo.Constraint(m.F, m.T, rule=c_link)

    # --- start / stop indicators --------------------------------------------------------------------
    def c_start(m, f, t):
        prev = m.u[f, t - 1] if t > 0 else 0
        return m.s[f, t] >= m.u[f, t] - prev
    m.c_start = pyo.Constraint(m.F, m.T, rule=c_start)

    def c_start_ub1(m, f, t):
        return m.s[f, t] <= m.u[f, t]
    m.c_start_ub1 = pyo.Constraint(m.F, m.T, rule=c_start_ub1)

    def c_start_ub2(m, f, t):
        if t == 0:
            return pyo.Constraint.Skip
        return m.s[f, t] <= 1 - m.u[f, t - 1]
    m.c_start_ub2 = pyo.Constraint(m.F, m.T, rule=c_start_ub2)

    def c_stop(m, f, t):
        prev = m.u[f, t - 1] if t > 0 else 0
        return m.e[f, t] >= prev - m.u[f, t]
    m.c_stop = pyo.Constraint(m.F, m.T, rule=c_stop)

    def c_stop_ub1(m, f, t):
        return m.e[f, t] <= 1 - m.u[f, t]
    m.c_stop_ub1 = pyo.Constraint(m.F, m.T, rule=c_stop_ub1)

    def c_stop_ub2(m, f, t):
        if t == 0:
            return pyo.Constraint.Skip
        return m.e[f, t] <= m.u[f, t - 1]
    m.c_stop_ub2 = pyo.Constraint(m.F, m.T, rule=c_stop_ub2)

    # --- spells: count, minimum length, minimum off time --------------------------------------------
    def c_max_spells(m, f):
        return sum(m.s[f, t] for t in m.T) <= inp.max_spells
    m.c_max_spells = pyo.Constraint(m.F, rule=c_max_spells)

    def c_min_spell(m, f, t, k):
        if t + k >= N:
            return pyo.Constraint.Skip
        return m.u[f, t + k] >= m.s[f, t]
    m.K_spell = pyo.RangeSet(0, inp.min_spell_blocks - 1)
    m.c_min_spell = pyo.Constraint(m.F, m.T, m.K_spell, rule=c_min_spell)

    def c_min_off(m, f, t, k):
        if t + k >= N:
            return pyo.Constraint.Skip
        return m.u[f, t + k] <= 1 - m.e[f, t]
    m.K_off = pyo.RangeSet(0, inp.min_off_blocks - 1)
    m.c_min_off = pyo.Constraint(m.F, m.T, m.K_off, rule=c_min_off)

    # --- supply hours: "strictly limited to 08 hours per day" (equality) with the night-compensation clause --
    def c_hours(m, f):
        return sum(m.u[f, t] for t in m.T) + m.night[f] == inp.min_blocks
    m.c_hours = pyo.Constraint(m.F, rule=c_hours)

    # night compensation is all-or-nothing in practice: when invoked it is at least 1 h (4 blocks), at most the cap
    def c_night_cap(m, f):
        return m.night[f] <= inp.max_night_blocks * m.znight[f]
    m.c_night_cap = pyo.Constraint(m.F, rule=c_night_cap)

    def c_night_min(m, f):
        return m.night[f] >= min(4, inp.max_night_blocks) * m.znight[f]
    m.c_night_min = pyo.Constraint(m.F, rule=c_night_min)

    # --- irrigation minimum blocks (hard by default; soft with shortfall variable in relaxed rungs) --
    if opt.use_irrigation:
        def c_irr(m, f):
            req = inp.irrigation_required[f]
            if req <= 0:
                return pyo.Constraint.Skip
            if opt.irrigation_hard:
                return sum(m.u[f, t] for t in m.T) >= req
            return sum(m.u[f, t] for t in m.T) + m.irr_short[f] >= req
        m.c_irr = pyo.Constraint(m.F, rule=c_irr)
    if not (opt.use_irrigation and not opt.irrigation_hard):
        def c_irr_short_zero(m, f):
            return m.irr_short[f] == 0
        m.c_irr_short_zero = pyo.Constraint(m.F, rule=c_irr_short_zero)

    # --- power transformer rating -----------------------------------------------------------------
    if opt.use_pt_rating:
        def c_pt(m, p, t):
            return sum(load_kva_expr(m, f, t, inp) for f in inp.pt_feeders[p]) <= inp.pt_rating[p]
        m.c_pt = pyo.Constraint(m.P, m.T, rule=c_pt)

    # --- switching cap (kVA switched per block) and start separation ------------------------------
    if opt.use_switch_cap:
        def c_cap(m, t):
            return sum(inp.base_kva[f] * inp.p_surge * (m.s[f, t] + m.e[f, t]) for f in m.F) <= inp.switch_cap_kva
        m.c_cap = pyo.Constraint(m.T, rule=c_cap)
    if opt.use_start_separation and inp.start_separation > 1:
        def c_sep(m, t):
            return sum(m.s[f, t - k] for f in m.F for k in range(inp.start_separation) if t - k >= 0) <= 1
        m.c_sep = pyo.Constraint(m.T, rule=c_sep)

    # --- power balance ------------------------------------------------------------------------------
    def c_import(m, t):
        return m.imp[t] >= inp.pf * sum(load_kva_expr(m, f, t, inp) for f in m.F) - float(inp.pv_import_kw[t])
    m.c_import = pyo.Constraint(m.T, rule=c_import)

    def c_surplus(m, t):
        return m.sur[t] >= float(inp.pv_surplus_kw[t]) - inp.pf * sum(load_kva_expr(m, f, t, inp) for f in m.F)
    m.c_surplus = pyo.Constraint(m.T, rule=c_surplus)

    # --- transformer thermal state: exact linear IEC 60076-7 recursion per thermal class ------------
    cls = {c.key: c for c in inp.thermal_classes}
    p = inp.thermal_params

    def forcing_o(m, c, t):
        tc = cls[c]
        return tc.g_o["off"] + (tc.g_o["def"] - tc.g_o["off"]) * m.u[tc.feeder, t] \
            + (tc.g_o["surge"] - tc.g_o["def"]) * _surge_ind(m, tc.feeder, t, inp)

    def forcing_h(m, c, t):
        tc = cls[c]
        return tc.g_h["off"] + (tc.g_h["def"] - tc.g_h["off"]) * m.u[tc.feeder, t] \
            + (tc.g_h["surge"] - tc.g_h["def"]) * _surge_ind(m, tc.feeder, t, inp)

    def init(c, var):
        st = inp.initial_state.get(c)
        if st and var in st:
            return float(st[var])
        return inp.init_oil_rise if var == "o" else 0.0

    def c_oil(m, c, t):
        prev = m.o[c, t - 1] if t > 0 else init(c, "o")
        return m.o[c, t] == inp.a_o * prev + (1.0 - inp.a_o) * forcing_o(m, c, t)
    m.c_oil = pyo.Constraint(m.C, m.T, rule=c_oil)

    def c_h1(m, c, t):
        prev = m.h1[c, t - 1] if t > 0 else init(c, "h1")
        return m.h1[c, t] == inp.a_h1 * prev + (1.0 - inp.a_h1) * p.k21 * forcing_h(m, c, t)
    m.c_h1 = pyo.Constraint(m.C, m.T, rule=c_h1)

    def c_h2(m, c, t):
        prev = m.h2[c, t - 1] if t > 0 else init(c, "h2")
        return m.h2[c, t] == inp.a_h2 * prev + (1.0 - inp.a_h2) * (p.k21 - 1.0) * forcing_h(m, c, t)
    m.c_h2 = pyo.Constraint(m.C, m.T, rule=c_h2)

    def hot_spot(m, c, t):
        return float(inp.ambient_c[t]) + m.o[c, t] + m.h1[c, t] - m.h2[c, t]

    if opt.use_thermal:
        def c_limit(m, c, t):
            return hot_spot(m, c, t) <= inp.hot_spot_limit_c - inp.thermal_margin_c
        m.c_limit = pyo.Constraint(m.C, m.T, rule=c_limit)

    def c_age(m, c, t):
        return m.age[c, t] >= hot_spot(m, c, t) - inp.ageing_reference_c
    m.c_age = pyo.Constraint(m.C, m.T, rule=c_age)

    # --- forced starts (contrastive explanations: "what if feeder f started at t?") -----------------
    if inp.forced_starts:
        def c_forced(m, f):
            if f not in inp.forced_starts:
                return pyo.Constraint.Skip
            return m.s[f, int(inp.forced_starts[f])] == 1
        m.c_forced = pyo.Constraint(m.F, rule=c_forced)

    # --- plan stability and locked blocks ---------------------------------------------------------
    if inp.announced is not None:
        def c_lock(m, f, t):
            if t < inp.lock_until:
                return m.u[f, t] == int(min(inp.announced[f][t], inp.avail[f][t]))
            return pyo.Constraint.Skip
        m.c_lock = pyo.Constraint(m.F, m.T, rule=c_lock)
        if opt.use_stability:
            def c_dev1(m, f, t):
                return m.dev[f, t] >= m.u[f, t] - int(inp.announced[f][t])
            def c_dev2(m, f, t):
                return m.dev[f, t] >= int(inp.announced[f][t]) - m.u[f, t]
            m.c_dev1 = pyo.Constraint(m.F, m.T, rule=c_dev1)
            m.c_dev2 = pyo.Constraint(m.F, m.T, rule=c_dev2)

    # --- fairness: distance of the first start from the rotating preferred start -------------------
    if opt.use_fairness:
        def c_fair1(m, f):
            return m.fair[f] >= sum(t * m.s[f, t] for t in m.T) - inp.preferred_start[f] * sum(m.s[f, t] for t in m.T)
        def c_fair2(m, f):
            return m.fair[f] >= inp.preferred_start[f] * sum(m.s[f, t] for t in m.T) - sum(t * m.s[f, t] for t in m.T)
        m.c_fair1 = pyo.Constraint(m.F, rule=c_fair1)
        m.c_fair2 = pyo.Constraint(m.F, rule=c_fair2)

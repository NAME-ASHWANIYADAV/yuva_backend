"""Coupling constraints of the switching MILP. Per-feeder rules (window, outages, hours, spells, off-time, locks,
forced start, night-compensation cap, irrigation minimum, DT hot-spot limit) are enforced by the pattern enumeration;
here only the rules that couple feeders remain. Each family can be toggled for ablations (SolveOptions).
"""
from __future__ import annotations

from itertools import combinations

import pyomo.environ as pyo

from .inputs import PlanInputs


def _is_const(expr) -> bool:
    return isinstance(expr, (int, float))


def load_kva_expr(m, f, t, inp: PlanInputs):
    base = inp.base_kva[f]
    return base * (inp.p_def * m.ind.u(f, t) + (inp.p_surge - inp.p_def) * m.ind.sg(f, t))


def add_constraints(m: pyo.ConcreteModel, inp: PlanInputs) -> None:
    opt = inp.options
    T_win = list(inp.window)
    T_edge = list(range(min(T_win), min(inp.N, max(T_win) + 2))) if T_win else []   # window plus the block after it

    # --- power transformer rating -----------------------------------------------------------------------------------
    if opt.use_pt_rating:
        def c_pt(m, p, t):
            fs = inp.pt_feeders[p]
            if t not in T_win or not fs:
                return pyo.Constraint.Skip
            body = sum(load_kva_expr(m, f, t, inp) for f in fs)
            return pyo.Constraint.Skip if _is_const(body) else body <= inp.pt_rating[p]
        m.c_pt = pyo.Constraint(m.P, m.T, rule=c_pt)
        # cover inequalities (valid, tighten the LP relaxation): a set of feeders whose default-participation load
        # already exceeds the rating can never be energised together
        covers = []
        for pt, fs in inp.pt_feeders.items():
            for r in range(2, len(fs) + 1):
                for S in combinations(fs, r):
                    if sum(inp.base_kva[f] * inp.p_def for f in S) > inp.pt_rating[pt] + 1e-6 and \
                       not any(set(S2) < set(S) for S2 in covers):
                        covers.append(S)
        m.pt_covers = covers
        m.c_cover = pyo.ConstraintList()
        for S in covers:
            for t in T_win:
                body = sum(m.ind.u(f, t) for f in S)
                if not _is_const(body):
                    m.c_cover.add(body <= len(S) - 1)

    # --- switching cap (kVA switched per block) and start separation -----------------------------------------------
    if opt.use_switch_cap:
        def c_cap(m, t):   # a spell that ends at the window close switches off in the first block outside it
            if t not in T_edge:
                return pyo.Constraint.Skip
            body = sum(inp.base_kva[f] * inp.p_surge * (m.ind.s(f, t) + m.ind.e(f, t)) for f in m.F)
            return pyo.Constraint.Skip if _is_const(body) else body <= inp.switch_cap_kva
        m.c_cap = pyo.Constraint(m.T, rule=c_cap)
    if opt.use_start_separation and inp.start_separation > 1:
        def c_sep(m, t):
            if t not in T_win:
                return pyo.Constraint.Skip
            body = sum(m.ind.s(f, t - k) for f in m.F for k in range(inp.start_separation) if t - k >= 0)
            return pyo.Constraint.Skip if _is_const(body) else body <= 1
        m.c_sep = pyo.Constraint(m.T, rule=c_sep)

    # --- plant power balance (import is paid, surplus is lost value) ----------------------------------------------
    def c_import(m, t):
        return m.imp[t] >= inp.pf * sum(load_kva_expr(m, f, t, inp) for f in m.F) - float(inp.pv_import_kw[t])
    m.c_import = pyo.Constraint(m.T, rule=c_import)

    if opt.use_surplus:
        def c_surplus(m, t):
            return m.sur[t] >= float(inp.pv_surplus_kw[t]) - inp.pf * sum(load_kva_expr(m, f, t, inp) for f in m.F)
        m.c_surplus = pyo.Constraint(m.T, rule=c_surplus)
    else:
        m.sur.fix(0.0)

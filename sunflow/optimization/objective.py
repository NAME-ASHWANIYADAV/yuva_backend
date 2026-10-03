"""Weighted objective in rupees (weights in configs/weights.yaml). Pattern-level costs are precomputed constants."""
from __future__ import annotations

import numpy as np
import pyomo.environ as pyo

from .inputs import PlanInputs


def pattern_cost(p, f: str, inp: PlanInputs) -> float:
    """Costs that depend only on the feeder's own pattern: switchings, night compensation (energy + penalty),
    deviation from the announced plan, irrigation urgency (start delay) and fairness, irrigation shortfall,
    transformer ageing (from the pattern's exact thermal trajectory)."""
    w = inp.weights
    opt = inp.options
    cost = w.switching_inr_per_event * p.switchings + p.ageing_cost
    if p.night > 0:
        cost += (w.night_comp_inr_per_block + w.import_inr_per_kwh * inp.dt_h * inp.base_kva[f] * inp.p_def * inp.pf) * p.night
    if inp.announced is not None and opt.use_stability and f in inp.announced:
        ann = np.asarray(inp.announced[f], dtype=int)
        cost += w.deviation_inr_per_block * float(np.sum(np.abs(p.u - ann)))
    if opt.use_irrigation and p.first_start >= 0:
        cost += w.urgency_inr_per_block * inp.urgency[f] * p.first_start
        req = inp.irrigation_required[f]
        if not opt.irrigation_hard and req > p.n_on:
            cost += (w.night_comp_inr_per_block * 2.0) * (req - p.n_on)
    if opt.use_fairness and p.first_start >= 0:
        cost += w.fairness_inr_per_block * abs(p.first_start - inp.preferred_start[f])
    return float(cost)


def add_objective(m: pyo.ConcreteModel, inp: PlanInputs) -> None:
    w = inp.weights
    opt = inp.options
    dt_h = inp.dt_h
    pats = m.patterns
    import_cost = w.import_inr_per_kwh * dt_h * sum(m.imp[t] for t in m.T)
    surplus_cost = (w.surplus_inr_per_kwh * dt_h * sum(m.sur[t] for t in m.T)) if opt.use_surplus else 0.0
    pattern_costs = sum(pattern_cost(p, f, inp) * m.x[f, i] for f in inp.feeders for i, p in enumerate(pats[f]))
    m.obj = pyo.Objective(expr=import_cost + surplus_cost + pattern_costs, sense=pyo.minimize)

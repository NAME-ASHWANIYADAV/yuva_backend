"""Weighted objective in rupees (weights in configs/weights.yaml)."""
from __future__ import annotations

import pyomo.environ as pyo

from .inputs import PlanInputs


def add_objective(m: pyo.ConcreteModel, inp: PlanInputs) -> None:
    w = inp.weights
    opt = inp.options
    cls = {c.key: c for c in inp.thermal_classes}
    dt_h = inp.dt_h

    import_cost = w.import_inr_per_kwh * dt_h * sum(m.imp[t] for t in m.T)
    surplus_cost = (w.surplus_inr_per_kwh * dt_h * sum(m.sur[t] for t in m.T)) if opt.use_surplus else 0.0
    ageing_cost = w.ageing_inr_per_deg_block * sum(cls[c].multiplicity * m.age[c, t] for c in m.C for t in m.T)
    switching_cost = w.switching_inr_per_event * sum(m.s[f, t] + m.e[f, t] for f in m.F for t in m.T)
    deviation_cost = (w.deviation_inr_per_block * sum(m.dev[f, t] for f in m.F for t in m.T)) if (inp.announced is not None and opt.use_stability) else 0.0
    urgency_cost = w.urgency_inr_per_block * sum(inp.urgency[f] * sum(t * m.s[f, t] for t in m.T) for f in m.F) if opt.use_irrigation else 0.0
    fairness_cost = (w.fairness_inr_per_block * sum(m.fair[f] for f in m.F)) if opt.use_fairness else 0.0
    # night compensation is pure grid import (no solar at night) plus a penalty for invoking the clause
    night_cost = sum((w.night_comp_inr_per_block + w.import_inr_per_kwh * dt_h * inp.base_kva[f] * inp.p_def * inp.pf) * m.night[f] for f in m.F)
    irr_short_cost = (w.night_comp_inr_per_block * 2.0) * sum(m.irr_short[f] for f in m.F)

    m.obj = pyo.Objective(
        expr=import_cost + surplus_cost + ageing_cost + switching_cost + deviation_cost + urgency_cost
        + fairness_cost + night_cost + irr_short_cost,
        sense=pyo.minimize,
    )

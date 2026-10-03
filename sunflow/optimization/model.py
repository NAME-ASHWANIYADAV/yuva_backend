"""Pyomo MILP for feeder switching (OPTIMISATION layer). Decision: u[f,t] in {0,1}."""
from __future__ import annotations

import pyomo.environ as pyo

from .inputs import PlanInputs
from .constraints import add_constraints
from .objective import add_objective


def build_model(inp: PlanInputs) -> pyo.ConcreteModel:
    m = pyo.ConcreteModel(name="sunflow_switching")
    m.F = pyo.Set(initialize=inp.feeders, ordered=True)
    m.T = pyo.RangeSet(0, inp.N - 1)
    m.P = pyo.Set(initialize=list(inp.pt_rating.keys()), ordered=True)
    m.C = pyo.Set(initialize=[c.key for c in inp.thermal_classes], ordered=True)

    m.u = pyo.Var(m.F, m.T, domain=pyo.Binary)          # feeder energised
    m.s = pyo.Var(m.F, m.T, domain=pyo.Binary)          # spell start at t
    m.e = pyo.Var(m.F, m.T, domain=pyo.Binary)          # spell stop at t (off from t)
    m.imp = pyo.Var(m.T, domain=pyo.NonNegativeReals)   # grid import kW
    m.sur = pyo.Var(m.T, domain=pyo.NonNegativeReals)   # solar not used on feeder kW
    m.night = pyo.Var(m.F, domain=pyo.NonNegativeIntegers)  # night-compensation blocks (clause 3)
    m.znight = pyo.Var(m.F, domain=pyo.Binary)              # 1 if night compensation is invoked (then >= 1 h)
    m.o = pyo.Var(m.C, m.T, domain=pyo.Reals)           # top-oil rise per thermal class
    m.h1 = pyo.Var(m.C, m.T, domain=pyo.Reals)          # hot-spot rise component 1
    m.h2 = pyo.Var(m.C, m.T, domain=pyo.Reals)          # hot-spot rise component 2
    m.age = pyo.Var(m.C, m.T, domain=pyo.NonNegativeReals)   # degree-blocks above ageing reference
    m.dev = pyo.Var(m.F, m.T, domain=pyo.NonNegativeReals)   # deviation from announced plan
    m.fair = pyo.Var(m.F, domain=pyo.NonNegativeReals)       # blocks away from preferred start
    m.irr_short = pyo.Var(m.F, domain=pyo.NonNegativeReals)  # irrigation shortfall blocks (soft mode only)

    add_constraints(m, inp)
    add_objective(m, inp)
    return m

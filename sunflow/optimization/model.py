"""Pyomo MILP for feeder switching (OPTIMISATION layer).

Column formulation: x[f,p] = 1 if feeder f runs admissible daily pattern p (see patterns.py). Per-feeder rules and
the transformer hot-spot limit are enforced by the pattern set; the model carries only the feeder-coupling rules
(power-transformer rating, switching cap, start separation) and the plant power balance (import / surplus).
The familiar per-block indicators u (on), s (start), e (stop) and sg (surge) are linear expressions in x.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np
import pyomo.environ as pyo
from pyomo.core.expr.numeric_expr import LinearExpression

from .inputs import PlanInputs
from .patterns import Pattern, pattern_sets
from .constraints import add_constraints
from .objective import add_objective


class Indicators:
    """Linear expressions u/s/e/sg[f,t] over the pattern binaries, with per-block index lists precomputed."""

    def __init__(self, m: pyo.ConcreteModel, pats: Dict[str, List[Pattern]], N: int):
        self.m = m
        self.idx: Dict[str, Dict[str, List[List[int]]]] = {}
        for f, ps in pats.items():
            self.idx[f] = {attr: [[] for _ in range(N)] for attr in ("u", "s", "e", "sg")}
            for i, p in enumerate(ps):
                for attr in ("u", "s", "e", "sg"):
                    for t in np.flatnonzero(getattr(p, attr)):
                        self.idx[f][attr][int(t)].append(i)

    def expr(self, attr: str, f: str, t: int):
        ids = self.idx[f][attr][t] if 0 <= t < len(self.idx[f][attr]) else []
        if not ids:
            return 0.0
        return LinearExpression(constant=0.0, linear_coefs=[1.0] * len(ids), linear_vars=[self.m.x[f, i] for i in ids])

    def u(self, f, t): return self.expr("u", f, t)
    def s(self, f, t): return self.expr("s", f, t)
    def e(self, f, t): return self.expr("e", f, t)
    def sg(self, f, t): return self.expr("sg", f, t)



def build_model(inp: PlanInputs, pats: Optional[Dict[str, List[Pattern]]] = None) -> pyo.ConcreteModel:
    pats = pats if pats is not None else pattern_sets(inp)
    m = pyo.ConcreteModel(name="sunflow_switching")
    m.patterns = pats
    m.F = pyo.Set(initialize=inp.feeders, ordered=True)
    m.T = pyo.RangeSet(0, inp.N - 1)
    m.P = pyo.Set(initialize=list(inp.pt_rating.keys()), ordered=True)
    m.FP = pyo.Set(initialize=[(f, i) for f in inp.feeders for i in range(len(pats[f]))], dimen=2)

    m.x = pyo.Var(m.FP, domain=pyo.Binary)                  # pattern choice
    m.imp = pyo.Var(m.T, domain=pyo.NonNegativeReals)       # grid import kW
    m.sur = pyo.Var(m.T, domain=pyo.NonNegativeReals)       # solar not used on feeder kW
    m.ind = Indicators(m, pats, inp.N)

    def c_one(m, f):
        if not pats[f]:
            return pyo.Constraint.Infeasible
        return sum(m.x[f, i] for i in range(len(pats[f]))) == 1
    m.c_one = pyo.Constraint(m.F, rule=c_one)

    add_constraints(m, inp)
    add_objective(m, inp)
    return m

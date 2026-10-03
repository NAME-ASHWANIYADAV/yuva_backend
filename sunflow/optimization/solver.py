"""Solve the switching MILP with HiGHS and extract the plan plus binding-constraint facts."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pyomo.environ as pyo

from ..core.logging import get_logger
from ..simulation.types import Plan
from .inputs import PlanInputs
from .model import build_model

log = get_logger("sunflow.opt")


@dataclass
class SolveResult:
    status: str                              # optimal | feasible | infeasible | error | timeout
    plan: Optional[Plan]
    objective: Optional[float]
    solve_time_s: float
    night_comp: Dict[str, float] = field(default_factory=dict)
    irrigation_shortfall: Dict[str, float] = field(default_factory=dict)
    binding: Dict[str, list] = field(default_factory=dict)   # facts about tight constraints
    message: str = ""
    model_size: Dict[str, int] = field(default_factory=dict)


def _extract_binding(m: pyo.ConcreteModel, inp: PlanInputs) -> Dict[str, list]:
    facts: Dict[str, list] = {"pt": [], "thermal": [], "cap": [], "hours": []}
    tol = 1e-3
    if inp.options.use_pt_rating:
        for p in m.P:
            for t in m.T:
                body = pyo.value(m.c_pt[p, t].body)
                if inp.pt_rating[p] - body <= 1.0:  # within 1 kVA of the rating
                    facts["pt"].append({"pt": p, "block": int(t), "load_kva": round(body, 1), "rating_kva": inp.pt_rating[p]})
    if inp.options.use_thermal:
        limit = inp.hot_spot_limit_c - inp.thermal_margin_c
        cls = {c.key: c for c in inp.thermal_classes}
        for c in m.C:
            worst_t, worst_v = None, -1e9
            for t in m.T:
                v = pyo.value(m.c_limit[c, t].body)
                if v > worst_v:
                    worst_v, worst_t = v, int(t)
            facts["thermal"].append({"class": c, "feeder": cls[c].feeder, "rating_kva": cls[c].rating_kva,
                                     "n_dts": cls[c].multiplicity, "max_hot_spot_c": round(worst_v, 2),
                                     "block": worst_t, "limit_c": limit, "binding": bool(limit - worst_v <= 0.5)})
    if inp.options.use_switch_cap:
        for t in m.T:
            body = pyo.value(m.c_cap[t].body)
            if inp.switch_cap_kva - body <= 1.0 and body > 0:
                facts["cap"].append({"block": int(t), "switched_kva": round(body, 1), "cap_kva": inp.switch_cap_kva})
    for f in m.F:
        on = sum(pyo.value(m.u[f, t]) for t in m.T)
        facts["hours"].append({"feeder": f, "blocks_on": int(round(on)), "night_comp": float(pyo.value(m.night[f]))})
    return facts


def solve_plan(inp: PlanInputs) -> SolveResult:
    t0 = time.time()
    try:
        m = build_model(inp)
        from pyomo.contrib.appsi.solvers.highs import Highs
        opt = Highs()
        opt.config.time_limit = float(inp.options.time_limit_s)
        opt.config.mip_gap = float(inp.options.mip_gap)
        opt.config.load_solution = False
        res = opt.solve(m)
        tc = str(res.termination_condition).split(".")[-1].lower()
        n_bin = sum(1 for v in m.component_data_objects(pyo.Var) if v.is_binary())
        size = {"binaries": n_bin, "constraints": sum(1 for _ in m.component_data_objects(pyo.Constraint))}
        if tc in ("optimal", "maxtimelimit", "maxiterations") and res.best_feasible_objective is not None:
            res.solution_loader.load_vars()
            plan: Plan = {f: np.array([int(round(pyo.value(m.u[f, t]))) for t in m.T], dtype=int) for f in m.F}
            status = "optimal" if tc == "optimal" else "feasible"
            out = SolveResult(status=status, plan=plan, objective=float(pyo.value(m.obj)),
                              solve_time_s=time.time() - t0,
                              night_comp={f: float(pyo.value(m.night[f])) for f in m.F},
                              irrigation_shortfall={f: float(pyo.value(m.irr_short[f])) for f in m.F},
                              binding=_extract_binding(m, inp), message=tc, model_size=size)
            log.info(f"solve status={status} obj={out.objective:.1f} t={out.solve_time_s:.2f}s size={size}")
            return out
        status = "infeasible" if "infeasible" in tc else ("timeout" if "time" in tc else "error")
        log.warning(f"solve status={status} tc={tc} t={time.time() - t0:.2f}s")
        return SolveResult(status=status, plan=None, objective=None, solve_time_s=time.time() - t0, message=tc, model_size=size)
    except Exception as exc:  # solver crash, model bug, missing solver: report, never raise into the planner
        log.error(f"solver error: {exc!r}")
        return SolveResult(status="error", plan=None, objective=None, solve_time_s=time.time() - t0, message=repr(exc))

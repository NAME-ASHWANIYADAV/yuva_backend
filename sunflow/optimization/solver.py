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
from .heuristic import warm_start
from .model import build_model
from .patterns import Pattern, pattern_sets

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
    model_size: Dict[str, object] = field(default_factory=dict)
    gap: Optional[float] = None


def _extract_binding(m: pyo.ConcreteModel, inp: PlanInputs, chosen: Dict[str, Pattern], pstats: Dict[str, dict]) -> Dict[str, list]:
    facts: Dict[str, list] = {"pt": [], "thermal": [], "cap": [], "hours": []}
    if inp.options.use_pt_rating:
        for (p, t) in m.c_pt:
            body = pyo.value(m.c_pt[p, t].body)
            if inp.pt_rating[p] - body <= 1.0:
                facts["pt"].append({"pt": p, "block": int(t), "load_kva": round(body, 1), "rating_kva": inp.pt_rating[p]})
    limit = inp.hot_spot_limit_c - inp.thermal_margin_c
    cls = {c.key: c for c in inp.thermal_classes}
    for f in inp.feeders:
        p = chosen[f]
        st = pstats.get(f, {})
        for key, (mx, blk) in p.thermal.items():
            tc = cls[key]
            facts["thermal"].append({"class": key, "feeder": f, "rating_kva": tc.rating_kva, "n_dts": tc.multiplicity,
                                     "max_hot_spot_c": round(mx, 2), "block": int(blk), "limit_c": limit,
                                     "binding": bool(inp.options.use_thermal and (limit - mx <= 0.5 or st.get("thermal_dropped", 0) > 0)),
                                     "candidates": st.get("candidates", 0), "thermal_dropped": st.get("thermal_dropped", 0),
                                     "longest_single_spell_blocks": st.get("longest_single_spell_blocks", 0)})
    if inp.options.use_switch_cap:
        for t in m.c_cap:
            body = pyo.value(m.c_cap[t].body)
            if inp.switch_cap_kva - body <= 1.0 and body > 0:
                facts["cap"].append({"block": int(t), "switched_kva": round(body, 1), "cap_kva": inp.switch_cap_kva})
    for f in inp.feeders:
        p = chosen[f]
        facts["hours"].append({"feeder": f, "blocks_on": int(p.n_on), "night_comp": float(p.night), "spells": p.spells})
    facts["pattern_stats"] = [dict(feeder=f, **pstats.get(f, {})) for f in inp.feeders]
    facts["pt_covers"] = [list(S) for S in getattr(m, "pt_covers", [])]
    return facts


def _apply_warm_start(m: pyo.ConcreteModel, inp: PlanInputs, pats: Dict[str, List[Pattern]], choice: Dict[str, int]) -> None:
    """Load a full feasible point (patterns + implied import/surplus) into the Pyomo variables as a MIP start."""
    load = np.zeros(inp.N)
    for f, i in choice.items():
        p = pats[f][i]
        load += inp.base_kva[f] * (inp.p_def * p.u + (inp.p_surge - inp.p_def) * p.sg)
        for j in range(len(pats[f])):
            m.x[f, j].value = 1.0 if j == i else 0.0
    imp = np.maximum(0.0, inp.pf * load - np.asarray(inp.pv_import_kw, dtype=float))
    sur = np.maximum(0.0, np.asarray(inp.pv_surplus_kw, dtype=float) - inp.pf * load)
    for t in range(inp.N):
        m.imp[t].value = float(imp[t])
        if not m.sur[t].fixed:
            m.sur[t].value = float(sur[t])


def _run_highs(m: pyo.ConcreteModel, inp: PlanInputs, presolve: bool, warm: bool = False):
    from pyomo.contrib.appsi.solvers.highs import Highs
    opt = Highs()
    opt.config.time_limit = float(inp.options.time_limit_s)
    opt.config.mip_gap = float(inp.options.mip_gap)
    opt.config.load_solution = False
    opt.config.warmstart = bool(warm)
    opt.highs_options["mip_heuristic_effort"] = 0.2
    if not presolve:
        opt.highs_options["presolve"] = "off"
    res = opt.solve(m)
    return res, str(res.termination_condition).split(".")[-1].lower()


def solve_plan(inp: PlanInputs) -> SolveResult:
    t0 = time.time()
    try:
        pstats: Dict[str, dict] = {}
        pats = pattern_sets(inp, pstats)
        n_pat = {f: len(ps) for f, ps in pats.items()}
        size: Dict[str, object] = {"binaries": int(sum(n_pat.values())), "patterns": n_pat, "pattern_stats": pstats}
        if any(n == 0 for n in n_pat.values()):
            empty = [f for f, n in n_pat.items() if n == 0]
            log.warning(f"no admissible pattern for {empty}: infeasible by construction ({pstats})")
            return SolveResult(status="infeasible", plan=None, objective=None, solve_time_s=time.time() - t0,
                               message=f"no admissible daily pattern for {empty}", model_size=size)
        m = build_model(inp, pats)
        size["constraints"] = sum(1 for _ in m.component_data_objects(pyo.Constraint))
        hs = warm_start(inp, pats, seed=0)
        if hs is not None:
            _apply_warm_start(m, inp, pats, hs.choice)
            size["warm_start_objective"] = round(hs.objective, 1)
        res, tc = _run_highs(m, inp, presolve=True, warm=hs is not None)
        if "infeasible" in tc:
            # HiGHS presolve has been observed to declare this model class infeasible while the same model solves
            # without presolve; an infeasibility verdict is therefore always confirmed with presolve off.
            res2, tc2 = _run_highs(m, inp, presolve=False)
            if "infeasible" not in tc2:
                log.warning(f"presolve infeasibility not confirmed (presolve off: {tc2}); using the confirmed run")
            res, tc = res2, tc2
        if tc in ("optimal", "maxtimelimit", "maxiterations") and res.best_feasible_objective is not None:
            res.solution_loader.load_vars()
            chosen: Dict[str, Pattern] = {}
            plan: Plan = {}
            for f in inp.feeders:
                vals = [pyo.value(m.x[f, i]) for i in range(n_pat[f])]
                chosen[f] = pats[f][int(np.argmax(vals))]
                plan[f] = np.array(chosen[f].u, dtype=int)
            status = "optimal" if tc == "optimal" else "feasible"
            obj = float(res.best_feasible_objective)
            bound = res.best_objective_bound
            gap = (abs(obj - bound) / max(abs(obj), 1e-9)) if bound is not None and np.isfinite(bound) else None
            out = SolveResult(status=status, plan=plan, objective=obj, solve_time_s=time.time() - t0,
                              night_comp={f: float(chosen[f].night) for f in inp.feeders},
                              irrigation_shortfall={f: float(max(0, inp.irrigation_required[f] - chosen[f].n_on))
                                                    if (inp.options.use_irrigation and not inp.options.irrigation_hard) else 0.0
                                                    for f in inp.feeders},
                              binding=_extract_binding(m, inp, chosen, pstats), message=tc, model_size=size, gap=gap)
            log.info(f"solve status={status} obj={out.objective:.1f} gap={gap if gap is None else round(gap, 4)} t={out.solve_time_s:.2f}s "
                     f"binaries={size['binaries']} constraints={size['constraints']}")
            return out
        status = "infeasible" if "infeasible" in tc else ("timeout" if "time" in tc else "error")
        log.warning(f"solve status={status} tc={tc} t={time.time() - t0:.2f}s")
        return SolveResult(status=status, plan=None, objective=None, solve_time_s=time.time() - t0, message=tc, model_size=size)
    except Exception as exc:  # solver crash, model bug, missing solver: report, never raise into the planner
        log.error(f"solver error: {exc!r}")
        return SolveResult(status="error", plan=None, objective=None, solve_time_s=time.time() - t0, message=repr(exc))

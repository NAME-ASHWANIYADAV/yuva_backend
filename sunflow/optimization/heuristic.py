"""Constructive warm start for the pattern MILP: penalised coordinate descent over the pattern sets.

Every feeder-only rule is already inside its pattern set, so the heuristic only has to balance the coupling rules
(power-transformer rating, switching cap, start separation) and the plant import/surplus cost. It evaluates the exact
MILP objective of each candidate pattern given the other feeders' current choices (vectorised over patterns), adds a
large penalty per unit of coupling violation, and sweeps feeders until nothing improves. Several seeded restarts are
run; the best violation-free assignment is handed to HiGHS as a MIP start, so the branch-and-bound begins with a
feasible incumbent instead of searching for one. Deterministic for a given seed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from .inputs import PlanInputs
from .objective import pattern_cost
from .patterns import Pattern


@dataclass
class HeuristicResult:
    choice: Dict[str, int]
    objective: float
    violation: float
    restarts: int


class _FeederArrays:
    def __init__(self, f: str, pats: List[Pattern], inp: PlanInputs):
        self.f = f
        U = np.stack([p.u for p in pats]).astype(float)
        S = np.stack([p.s for p in pats]).astype(float)
        E = np.stack([p.e for p in pats]).astype(float)
        SG = np.stack([p.sg for p in pats]).astype(float)
        base = inp.base_kva[f]
        self.load = base * (inp.p_def * U + (inp.p_surge - inp.p_def) * SG)          # kVA per block
        self.switch = base * inp.p_surge * (S + E)                                      # kVA switched per block
        sep = inp.start_separation
        win = np.zeros_like(S)
        for k in range(sep):
            win[:, k:] += S[:, : S.shape[1] - k] if k else S
        self.startwin = win                                                             # starts in the last `sep` blocks
        self.cost = np.array([pattern_cost(p, f, inp) for p in pats])
        self.pt = next((pt for pt, fs in inp.pt_feeders.items() if f in fs), None)


def warm_start(inp: PlanInputs, pats: Dict[str, List[Pattern]], restarts: int = 16, sweeps: int = 12,
               seed: int = 0, penalty: float = 1e4, repair_budget_s: float = 2.5) -> Optional[HeuristicResult]:
    feeders = [f for f in inp.feeders if pats[f]]
    if len(feeders) != len(inp.feeders):
        return None
    arr = {f: _FeederArrays(f, pats[f], inp) for f in feeders}
    opt = inp.options
    w = inp.weights
    pf, dt_h = inp.pf, inp.dt_h
    pv_imp = np.asarray(inp.pv_import_kw, dtype=float)
    pv_sur = np.asarray(inp.pv_surplus_kw, dtype=float)
    rng = np.random.default_rng(seed)
    N = inp.N

    def totals(choice):
        load = np.zeros(N); switch = np.zeros(N); startwin = np.zeros(N)
        pt_load = {pt: np.zeros(N) for pt in inp.pt_rating}
        for f, i in choice.items():
            a = arr[f]
            load += a.load[i]; switch += a.switch[i]; startwin += a.startwin[i]
            if a.pt is not None:
                pt_load[a.pt] += a.load[i]
        return load, switch, startwin, pt_load

    def evaluate(f, load_o, switch_o, startwin_o, pt_o):
        a = arr[f]
        load = load_o[None, :] + a.load
        obj = a.cost + w.import_inr_per_kwh * dt_h * np.maximum(0.0, pf * load - pv_imp[None, :]).sum(axis=1)
        if opt.use_surplus:
            obj = obj + w.surplus_inr_per_kwh * dt_h * np.maximum(0.0, pv_sur[None, :] - pf * load).sum(axis=1)
        viol = np.zeros(len(a.cost))
        if opt.use_pt_rating and a.pt is not None:
            viol += np.maximum(0.0, pt_o[None, :] + a.load - inp.pt_rating[a.pt]).sum(axis=1) / 100.0
        if opt.use_switch_cap:
            viol += np.maximum(0.0, switch_o[None, :] + a.switch - inp.switch_cap_kva).sum(axis=1) / 100.0
        if opt.use_start_separation and inp.start_separation > 1:
            viol += np.maximum(0.0, startwin_o[None, :] + a.startwin - 1.0).sum(axis=1)
        return obj, viol

    def descend(choice, cost_weight: float, pen: float):
        """Coordinate descent on cost_weight * objective + pen * violation; returns the final totals."""
        load, switch, startwin, pt_load = totals(choice)
        for _ in range(sweeps):
            improved = False
            order = list(feeders)
            rng.shuffle(order)
            for f in order:
                a = arr[f]; i0 = choice[f]
                load_o = load - a.load[i0]; switch_o = switch - a.switch[i0]; startwin_o = startwin - a.startwin[i0]
                pt_o = (pt_load[a.pt] - a.load[i0]) if a.pt is not None else np.zeros(N)
                obj, viol = evaluate(f, load_o, switch_o, startwin_o, pt_o)
                score = cost_weight * obj + pen * viol
                i1 = int(np.argmin(score))
                if i1 != i0 and score[i1] < score[i0] - 1e-9:
                    choice[f] = i1; improved = True
                    load = load_o + a.load[i1]; switch = switch_o + a.switch[i1]; startwin = startwin_o + a.startwin[i1]
                    if a.pt is not None:
                        pt_load[a.pt] = pt_o + a.load[i1]
            if not improved:
                break
        return choice

    best: Optional[HeuristicResult] = None
    # phase 1: cost + penalty from the cheapest-pattern start and random starts;
    # phase 2 (only if nothing feasible yet): violation-only repair from random starts, then a cost polish that
    # keeps feasibility (large penalty). Tight instances (e.g. participation 1.0) need the repair phase.
    import time as _time
    t_repair0 = None
    plan_runs = [("cost", r) for r in range(restarts)] + [("repair", r) for r in range(6 * restarts)]
    for phase, r in plan_runs:
        if phase == "repair":
            if best is not None:
                break
            t_repair0 = t_repair0 or _time.time()
            if _time.time() - t_repair0 > repair_budget_s:
                break
        if phase == "cost" and r == 0:
            choice = {f: int(np.argmin(arr[f].cost)) for f in feeders}
        else:
            choice = {f: int(rng.integers(len(pats[f]))) for f in feeders}
        if phase == "cost":
            choice = descend(choice, 1.0, penalty)
        else:
            choice = descend(choice, 0.0, 1.0)
            choice = descend(choice, 1.0, penalty * 100.0)
        # final exact evaluation of the assignment
        load, switch, startwin, pt_load = totals(choice)
        total_obj = sum(arr[f].cost[choice[f]] for f in feeders) + w.import_inr_per_kwh * dt_h * np.maximum(0.0, pf * load - pv_imp).sum()
        if opt.use_surplus:
            total_obj += w.surplus_inr_per_kwh * dt_h * np.maximum(0.0, pv_sur - pf * load).sum()
        violation = 0.0
        if opt.use_pt_rating:
            violation += sum(np.maximum(0.0, pt_load[pt] - inp.pt_rating[pt]).sum() for pt in pt_load)
        if opt.use_switch_cap:
            violation += np.maximum(0.0, switch - inp.switch_cap_kva).sum()
        if opt.use_start_separation and inp.start_separation > 1:
            violation += np.maximum(0.0, startwin - 1.0).sum()
        if violation <= 1e-6 and (best is None or total_obj < best.objective - 1e-9):
            best = HeuristicResult(choice=dict(choice), objective=float(total_obj), violation=0.0, restarts=r + 1)
    return best

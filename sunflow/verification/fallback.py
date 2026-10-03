"""Certification ladder: solve -> verify -> (tighten on mismatch | relax only what the circular allows) -> baseline.

Rungs relax constraint families in the order the operating rules permit:
  1. nominal            : today's practice (one contiguous spell), all hard rules
  2. split_spells       : two spells per feeder so hot DTs can cool mid-day (operator does one extra switching)
  3. feasibility_focus  : split spells + irrigation requirement deferred (flagged) + comfort terms off
The transformer temperature limit, PT rating, switching cap and window are never relaxed. If a solved plan fails
the independent verifier (model mismatch), the thermal margin is tightened and the rung is re-solved (twice).
If nothing certifies, the published MSEDCL timetable is returned with an alert: never worse than today.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional

from ..core.config import SunflowConfig, Weights
from ..core.logging import get_logger
from ..optimization.inputs import SolveOptions, build_inputs
from ..optimization.solver import solve_plan, SolveResult
from ..simulation.baseline import baseline_plan
from ..simulation.types import Plan, Scenario
from .verifier import VerifyReport, VerifySettings, verify

log = get_logger("sunflow.certify")

CERTIFIED = "CERTIFIED"
CERTIFIED_AFTER_TIGHTENING = "CERTIFIED_AFTER_TIGHTENING"
CERTIFIED_WITH_RELAXATION = "CERTIFIED_WITH_RELAXATION"
FALLBACK_BASELINE = "FALLBACK_BASELINE"
INFEASIBLE = "INFEASIBLE"


@dataclass
class Certified:
    status: str
    plan: Plan
    report: Optional[VerifyReport]
    ladder: List[dict] = field(default_factory=list)
    solve: Optional[SolveResult] = None
    night_comp: Dict[str, float] = field(default_factory=dict)
    irrigation_deferred: bool = False
    rung: str = ""
    conflicts: List[dict] = field(default_factory=list)
    alert: str = ""
    max_spells_allowed: int = 1          # spells per feeder the issuing rung allowed (for independent re-verification)

    @property
    def certified(self) -> bool:
        return self.status in (CERTIFIED, CERTIFIED_AFTER_TIGHTENING, CERTIFIED_WITH_RELAXATION)


SPLIT_TIME_LIMIT_S = 15.0     # split-spell models are larger; the heuristic warm start guarantees an incumbent
SPLIT_MIP_GAP = 0.03


def _split(base: SolveOptions, **kw) -> SolveOptions:
    return replace(base, max_spells=max(2, base.max_spells or 0), time_limit_s=min(base.time_limit_s, SPLIT_TIME_LIMIT_S),
                   mip_gap=max(base.mip_gap, SPLIT_MIP_GAP), **kw)


def _rungs(base: SolveOptions) -> List[dict]:
    return [
        {"name": "nominal", "opts": base},
        {"name": "split_spells", "opts": _split(base)},
        {"name": "feasibility_focus", "opts": _split(base, irrigation_hard=False, use_fairness=False, use_stability=False, use_surplus=False,
                                                      split_night_options="all")},
    ]


def economic_cost_inr(plan: Plan, scenario: Scenario, cfg: SunflowConfig, weights: Weights, night_comp: Optional[Dict[str, float]] = None) -> float:
    """Day cost of a plan under expected conditions, economic terms only (import, lost surplus, switching, night
    compensation energy + penalty). Used for the never-worse-than-baseline guard."""
    from ..simulation.truth_engine import simulate
    sim = simulate(plan, scenario, cfg, night_comp=night_comp)      # import already includes night-compensation energy
    mt = sim.metrics
    cost = weights.import_inr_per_kwh * mt["import_kwh"] + weights.surplus_inr_per_kwh * mt.get("surplus_kwh", 0.0)         + weights.switching_inr_per_event * mt["switchings"]
    for f, nb in (night_comp or {}).items():
        if nb > 0:
            cost += nb * weights.night_comp_inr_per_block
    return float(cost)


def attribute_conflict(cfg: SunflowConfig, scenario: Scenario, weights: Weights, base: SolveOptions) -> List[dict]:
    """Which single constraint family, when relaxed, restores feasibility? (deterministic conflict attribution)"""
    relaxed_base = replace(base, max_spells=max(2, base.max_spells or 0), irrigation_hard=False, split_night_options="all",
                           time_limit_s=min(base.time_limit_s, 8.0), mip_gap=0.05)
    families = [
        ("transformer_hot_spot_limit", replace(relaxed_base, use_thermal=False)),
        ("power_transformer_rating", replace(relaxed_base, use_pt_rating=False)),
        ("switching_cap", replace(relaxed_base, use_switch_cap=False)),
        ("start_separation", replace(relaxed_base, use_start_separation=False)),
        ("supply_hours_8h", replace(relaxed_base, allow_night_compensation=True, max_night_blocks_override=32, use_irrigation=False)),
    ]
    out = []
    for name, opts in families:
        res = solve_plan(build_inputs(cfg, scenario, weights, opts))
        out.append({"family": name, "feasible_when_relaxed": res.status in ("optimal", "feasible")})
    return out


def certify(cfg: SunflowConfig, scenario: Scenario, weights: Weights, options: Optional[SolveOptions] = None,
            settings: Optional[VerifySettings] = None, baseline: Optional[Plan] = None, max_tightenings: int = 2) -> Certified:
    base = options or SolveOptions()
    settings = settings or VerifySettings.from_config(cfg)
    ladder: List[dict] = []
    last_solve: Optional[SolveResult] = None
    any_solver_problem = False
    bl = baseline or baseline_plan(cfg)

    def guard(cert: Certified) -> Certified:
        """Never worse than today's practice: if the published timetable itself verifies and is not more expensive
        under expected conditions, issue the timetable (an optimiser cannot make the operator worse off)."""
        bl_rep = verify(bl, scenario, cfg, settings)
        if not bl_rep.ok:
            return cert
        c_plan = economic_cost_inr(cert.plan, scenario, cfg, weights, cert.night_comp)
        c_base = economic_cost_inr(bl, scenario, cfg, weights)
        cert.ladder.append({"rung": "baseline_guard", "plan_cost_inr": round(c_plan, 1), "baseline_cost_inr": round(c_base, 1),
                            "baseline_verified": True})
        if c_base <= c_plan + 1e-6:
            log.info(f"baseline guard: published timetable (Rs {c_base:,.0f}) not worse than plan (Rs {c_plan:,.0f}); issuing timetable")
            return Certified(status=CERTIFIED, plan=bl, report=bl_rep, ladder=cert.ladder, solve=cert.solve, night_comp={},
                             irrigation_deferred=False, rung="baseline_guard", max_spells_allowed=cfg.rules.max_spells,
                             alert="Published timetable is already as cheap as any certified plan today; no change issued.")
        return cert

    for i, rung in enumerate(_rungs(base)):
        opts: SolveOptions = rung["opts"]
        margin = opts.thermal_margin_c if opts.thermal_margin_c is not None else weights.thermal_margin_c
        for k in range(max_tightenings + 1):
            o = replace(opts, thermal_margin_c=margin + 4.0 * k)
            res = solve_plan(build_inputs(cfg, scenario, weights, o))
            last_solve = res
            entry = {"rung": rung["name"], "tightening": k, "solve_status": res.status, "solve_time_s": round(res.solve_time_s, 2),
                     "thermal_margin_c": o.thermal_margin_c, "participation": o.participation, "max_spells": o.max_spells}
            if res.plan is None:
                entry["verify"] = None
                ladder.append(entry)
                if res.status == "error":
                    any_solver_problem = True
                elif res.status == "timeout":
                    any_solver_problem = True   # could not prove infeasible nor find a plan in time; keep trying other rungs
                break  # infeasible or failed: tightening cannot help, move to the next rung
            deferred = any(v > 1e-6 for v in res.irrigation_shortfall.values())
            allowed = o.max_spells if o.max_spells is not None else cfg.rules.max_spells
            rep = verify(res.plan, scenario, cfg, settings, night_comp=res.night_comp, irrigation_deferred=deferred, max_spells=allowed)
            entry["verify"] = rep.as_dict()
            ladder.append(entry)
            if rep.ok:
                uses_night = any(v > 1e-6 for v in res.night_comp.values())
                if i == 0 and uses_night and base.max_spells in (None, 1):
                    # a split spell (one extra switching) is preferable to sending farmers water at night: try it
                    alt_opts = _split(o)
                    alt = solve_plan(build_inputs(cfg, scenario, weights, alt_opts))
                    if alt.plan is not None and not any(v > 1e-6 for v in alt.night_comp.values()):
                        alt_def = any(v > 1e-6 for v in alt.irrigation_shortfall.values())
                        alt_rep = verify(alt.plan, scenario, cfg, settings, night_comp=alt.night_comp, irrigation_deferred=alt_def, max_spells=2)
                        ladder.append({"rung": "split_instead_of_night", "tightening": k, "solve_status": alt.status,
                                       "solve_time_s": round(alt.solve_time_s, 2), "thermal_margin_c": alt_opts.thermal_margin_c,
                                       "participation": alt_opts.participation, "max_spells": 2, "verify": alt_rep.as_dict()})
                        if alt_rep.ok:
                            from ..simulation.types import plan_spells
                            split_used = any(len(plan_spells(alt.plan[f])) > 1 for f in alt.plan)
                            log.info("certified without night compensation" + (" using split spells" if split_used else ""))
                            return guard(Certified(status=CERTIFIED_WITH_RELAXATION if split_used else CERTIFIED, plan=alt.plan, report=alt_rep,
                                             ladder=ladder, solve=alt, night_comp=alt.night_comp, irrigation_deferred=alt_def,
                                             rung="split_instead_of_night" if split_used else "nominal", max_spells_allowed=2,
                                             alert=("Plan uses two supply spells for some feeders instead of night compensation (allowed relaxation)." if split_used else "")))
                if i == 0 and k == 0:
                    status = CERTIFIED
                elif i == 0:
                    status = CERTIFIED_AFTER_TIGHTENING
                else:
                    status = CERTIFIED_WITH_RELAXATION
                alert = ""
                if i >= 1:
                    alert = "Plan uses two supply spells for some feeders (allowed relaxation)."
                if deferred:
                    alert += " Irrigation requirement deferred by one day for some feeders (flagged)."
                if any(v > 1e-6 for v in res.night_comp.values()):
                    alert += " Night compensation (circular clause 3) invoked for some feeders."
                log.info(f"certified status={status} rung={rung['name']} tightening={k}")
                return guard(Certified(status=status, plan=res.plan, report=rep, ladder=ladder, solve=res,
                                       night_comp=res.night_comp, irrigation_deferred=deferred, rung=rung["name"], alert=alert.strip(),
                                       max_spells_allowed=int(allowed)))
            # verification failed: tightening the thermal margin only helps a thermal mismatch
            if "hot_spot" not in rep.kinds():
                log.warning(f"verification failed on non-thermal rules {rep.kinds()}: model/verifier mismatch, next rung")
                break
    rep = verify(bl, scenario, cfg, settings)
    conflicts: List[dict] = []
    if any_solver_problem:
        status, alert = FALLBACK_BASELINE, "Solver failure; published timetable issued with alert."
    elif last_solve is not None and last_solve.plan is None:
        conflicts = attribute_conflict(cfg, scenario, weights, base)
        status, alert = INFEASIBLE, "No plan satisfies every hard rule under the declared assumptions; published timetable issued with alert."
    else:
        status, alert = FALLBACK_BASELINE, "Optimiser plans failed independent verification; published timetable issued with alert."
    log.warning(alert)
    return Certified(status=status, plan=bl, report=rep, ladder=ladder, solve=last_solve, conflicts=conflicts, alert=alert, rung="baseline",
                     max_spells_allowed=cfg.rules.max_spells)

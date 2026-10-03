"""Explanations from solver facts only (binding constraints, conflict attribution, contrastive re-solves).

No free-text reasoning is generated; every sentence is a template filled with numbers from the optimiser,
the verifier or the simulation.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, List, Optional

import numpy as np

from ..core.config import SunflowConfig, Weights
from ..core.timegrid import TimeGrid
from ..optimization.inputs import SolveOptions, build_inputs
from ..optimization.solver import solve_plan
from ..simulation.types import Plan, Scenario, SimResult, plan_starts, plan_spells
from ..verification import Certified, VerifySettings, verify


@dataclass
class Decision:
    feeder: str
    requested_start: int
    requested_label: str
    accepted: bool
    reason: str
    blocking_families: List[str] = field(default_factory=list)
    facts: Dict[str, object] = field(default_factory=dict)
    alternative_start: Optional[int] = None
    alternative_label: Optional[str] = None
    plan: Optional[Plan] = None
    cost_delta_inr: Optional[float] = None
    marathi: str = ""


def describe_binding(binding: Dict[str, list], grid: TimeGrid = TimeGrid()) -> List[str]:
    out: List[str] = []
    pts = binding.get("pt", [])
    if pts:
        by_pt: Dict[str, List[int]] = {}
        for x in pts:
            by_pt.setdefault(x["pt"], []).append(x["block"])
        for p, blocks in by_pt.items():
            out.append(f"{p} is at its 5 MVA rating in {len(blocks)} block(s), first at {grid.label(min(blocks))}: the start order of its feeders is fixed by this limit.")
    seen_feeder = set()
    for x in binding.get("thermal", []):
        if not x.get("binding"):
            continue
        if x.get("thermal_dropped", 0) > 0 and x["feeder"] not in seen_feeder:
            seen_feeder.add(x["feeder"])
            longest = x.get("longest_single_spell_blocks", 0)
            out.append(f"{x['feeder']}: {x['thermal_dropped']} of {x['candidates']} candidate daily schedules were excluded because its "
                       f"{int(x['rating_kva'])} kVA transformers would pass {x['limit_c']:.0f} C (planning limit incl. margin)"
                       + (f"; the longest admissible single spell today is {longest / 4:.2g} h" if longest else "; no single spell is admissible today")
                       + f". Chosen schedule peaks at {x['max_hot_spot_c']:.1f} C at {grid.label(x['block'])}.")
        elif x.get("thermal_dropped", 0) == 0:
            out.append(f"{x['n_dts']} x {int(x['rating_kva'])} kVA transformers on {x['feeder']} reach {x['max_hot_spot_c']:.1f} C at {grid.label(x['block'])}, "
                       f"within 0.5 C of the planning limit ({x['limit_c']:.0f} C incl. margin): their spell cannot sit later in the afternoon.")
    caps = binding.get("cap", [])
    if caps:
        out.append(f"The switching cap binds at {grid.label(caps[0]['block'])}: two feeders cannot be switched in the same block.")
    for x in binding.get("hours", []):
        if x.get("night_comp", 0) > 1e-6:
            out.append(f"{x['feeder']} receives {x['night_comp']:.0f} block(s) of night compensation (circular clause 3).")
    return out


def explain_plan(cert: Certified, cfg: SunflowConfig, baseline_sim: SimResult, plan_sim: SimResult,
                 grid: TimeGrid = TimeGrid()) -> List[str]:
    lines: List[str] = []
    if cert.solve is not None and cert.solve.binding:
        lines += describe_binding(cert.solve.binding, grid)
    # what moved vs the published timetable and the measurable consequence
    for f in cfg.feeders:
        b_sp = plan_spells(baseline_sim.plan[f.name]); p_sp = plan_spells(plan_sim.plan[f.name])
        if b_sp != p_sp:
            bs = ", ".join(f"{grid.label(a)}-{grid.label(b)}" for a, b in b_sp)
            ps = ", ".join(f"{grid.label(a)}-{grid.label(b)}" for a, b in p_sp)
            lines.append(f"{f.name}: published {bs} -> plan {ps}.")
    bm, pm = baseline_sim.metrics, plan_sim.metrics
    lines.append(f"Grid import {bm['import_kwh']:.0f} -> {pm['import_kwh']:.0f} kWh; solar used on feeder "
                 f"{100 * bm['solar_used_frac_of_pv']:.0f}% -> {100 * pm['solar_used_frac_of_pv']:.0f}%; "
                 f"PT-2 peak {100 * bm['pt2_max_loading_frac']:.0f}% -> {100 * pm['pt2_max_loading_frac']:.0f}% of rating; "
                 f"max DT hot-spot {bm['dt_max_hot_spot_c']:.1f} -> {pm['dt_max_hot_spot_c']:.1f} C (expected conditions, MODELLED).")
    if cert.alert:
        lines.append(cert.alert)
    if cert.conflicts:
        fams = [c["family"] for c in cert.conflicts if c["feasible_when_relaxed"]]
        lines.append("Infeasible as requested. Relaxing any one of these would restore feasibility: " + (", ".join(fams) if fams else "none individually; several rules conflict jointly") + ".")
    return lines


FAMILY_TEXT = {
    "power_transformer_rating": "the power transformer would exceed its rating",
    "transformer_hot_spot_limit": "distribution transformers would exceed the IEC hot-spot limit",
    "switching_cap": "the per-block switching cap would be exceeded",
    "start_separation": "two feeders would start within the 30-minute separation rule",
    "supply_hours_8h": "the 8-hour supply rule could not be met for every feeder",
    "irrigation_minimum": "another feeder's irrigation minimum could not be met",
}


def _solve_with_forced_start(cfg, weights, scenario, feeder, start, options) -> "SolveResult":
    inp = build_inputs(cfg, scenario, weights, options)
    inp.forced_starts = {feeder: start}
    return solve_plan(inp)


def explain_request(cfg: SunflowConfig, weights: Weights, scenario: Scenario, feeder: str, start_block: int,
                    options: Optional[SolveOptions] = None, settings: Optional[VerifySettings] = None,
                    grid: TimeGrid = TimeGrid(), search_radius: int = 12) -> Decision:
    """Can feeder `feeder` start at `start_block`? Answer with solver facts, the blocking rules and the nearest feasible start."""
    options = options or SolveOptions()
    # single-spell contrastive solves are sub-second; split-spell ones get a short limit (the heuristic start keeps
    # them feasible) so a request with up to a dozen candidate alternatives still answers within about a minute
    split = (options.max_spells or 1) > 1
    options = replace(options, time_limit_s=min(options.time_limit_s, 4.0 if split else 15.0), mip_gap=max(options.mip_gap, 0.05 if split else 0.005))
    max_candidates = 6 if split else 40
    settings = settings or VerifySettings.from_config(cfg)
    label = grid.label(start_block)
    rules = cfg.rules
    w0, w1 = grid.block_of(rules.window_start), grid.block_of(rules.window_end)
    latest_start = w1 - rules.min_blocks_per_feeder + rules.max_night_compensation_blocks
    feasible_starts = [t for t in range(w0, min(w1, latest_start) + 1)]
    facts: Dict[str, object] = {}
    # structural refusal first (no solve needed): outside the operating window or too late to deliver the hours
    structural = None
    if start_block < w0 or start_block >= w1:
        structural = f"{label} is outside the operating window {rules.window_start}-{rules.window_end}"
    elif start_block > latest_start:
        structural = (f"a start at {label} leaves fewer than {rules.min_blocks_per_feeder // 4} h before the window closes at "
                      f"{rules.window_end}, even with the {rules.max_night_compensation_blocks // 4} h night-compensation cap")
    res = _solve_with_forced_start(cfg, weights, scenario, feeder, start_block, options) if structural is None else None
    if res is not None and res.plan is not None:
        rep = verify(res.plan, scenario, cfg, settings, night_comp=res.night_comp, max_spells=options.max_spells)
        if rep.ok:
            base = solve_plan(build_inputs(cfg, scenario, weights, options))
            delta = (res.objective - base.objective) if (base.objective is not None and res.objective is not None) else None
            facts["binding"] = describe_binding(res.binding, grid)
            reason = f"Granted: {feeder} can start at {label}." + (f" Daily cost changes by Rs {delta:,.0f}." if delta is not None else "")
            return Decision(feeder, start_block, label, True, reason, [], facts, None, None, res.plan, delta,
                            marathi=f"मंजूर: {feeder} फीडर उद्या {label} पासून सुरू होईल.")
        blocking = sorted(rep.kinds().keys())
        facts["verify"] = rep.as_dict()
        reason = f"Refused: at {label} the plan fails verification ({', '.join(blocking)})."
    elif structural is not None:
        blocking = ["operating_window"]
        reason = f"Refused: {feeder} cannot start at {label} because {structural}."
    else:
        # attribute the conflict: which rule family blocks this start?
        blocking = []
        for name, opts in [
            ("power_transformer_rating", replace(options, use_pt_rating=False)),
            ("transformer_hot_spot_limit", replace(options, use_thermal=False)),
            ("switching_cap", replace(options, use_switch_cap=False)),
            ("start_separation", replace(options, use_start_separation=False)),
            ("irrigation_minimum", replace(options, use_irrigation=False)),
        ]:
            r = _solve_with_forced_start(cfg, weights, scenario, feeder, start_block, opts)
            if r.plan is not None:
                blocking.append(name)
        facts["pt_context"] = _pt_context(cfg, scenario, feeder, start_block, grid)
        why = "; ".join(FAMILY_TEXT[b] for b in blocking) if blocking else "several rules conflict jointly"
        reason = f"Refused: {feeder} cannot start at {label} because {why}."
    # nearest feasible alternative among structurally possible starts, searched outward from the request
    alt, alt_plan = None, None
    tried = 0
    for cand in sorted(feasible_starts, key=lambda t: (abs(t - start_block), t)):
        if cand == start_block:
            continue
        if tried >= max_candidates:
            break
        tried += 1
        r = _solve_with_forced_start(cfg, weights, scenario, feeder, cand, options)
        if r.plan is not None and verify(r.plan, scenario, cfg, settings, night_comp=r.night_comp, max_spells=options.max_spells).ok:
            alt, alt_plan = cand, r.plan
            break
    if alt is not None:
        reason += f" Nearest feasible start: {grid.label(alt)}."
    mr = f"नाकारले: {feeder} फीडर {label} ला सुरू करता येणार नाही." + (f" सर्वात जवळची शक्य वेळ: {grid.label(alt)}." if alt is not None else "")
    return Decision(feeder, start_block, label, False, reason, blocking, facts, alt, grid.label(alt) if alt is not None else None,
                    alt_plan, None, marathi=mr)


def _pt_context(cfg: SunflowConfig, scenario: Scenario, feeder: str, start_block: int, grid: TimeGrid) -> dict:
    """Numbers for the refusal card: the PT the feeder sits on, its rating and the feeder's surge load."""
    from ..simulation.feeder_model import FeederModel
    fm = FeederModel(cfg, scenario.failed_dts)
    f = cfg.feeder(feeder)
    pt = cfg.pt(f.pt)
    others = [x.name for x in cfg.feeders_on_pt(f.pt) if x.name != feeder]
    p = cfg.verification.participation
    return {"pt": pt.name, "rating_kva": pt.rating_kva, "feeder_surge_kva": round(fm.feeder_installed_kva(feeder) * cfg.participation.surge_level, 0),
            "other_feeders_kva_at_p90": round(sum(fm.feeder_installed_kva(o) for o in others) * p, 0), "others": others,
            "requested": grid.label(start_block)}

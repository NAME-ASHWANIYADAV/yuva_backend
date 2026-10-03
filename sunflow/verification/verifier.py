"""Independent deterministic verifier (VERIFICATION layer).

Re-simulates a plan with the full nonlinear IEC 60076-7 model under pessimistic settings and checks every hard
rule. This module imports only core, physics and simulation; it never imports the optimiser, so an optimiser bug
cannot hide from it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from ..core.config import SunflowConfig
from ..core.timegrid import TimeGrid
from ..simulation.truth_engine import simulate
from ..simulation.types import Plan, Scenario, SimResult, plan_spells


@dataclass(frozen=True)
class VerifySettings:
    ambient_offset_c: float = 3.0
    thermal_factor: float = 1.3
    participation: float = 1.0
    solar_quantile: str = "p10"
    hot_spot_limit_c: Optional[float] = None   # default: config limit, no margin

    @classmethod
    def from_config(cls, cfg: SunflowConfig) -> "VerifySettings":
        v = cfg.verification
        return cls(ambient_offset_c=v.ambient_offset_c, thermal_factor=v.thermal_factor,
                   participation=v.participation, solar_quantile=v.solar_quantile)


@dataclass
class Violation:
    kind: str
    where: str
    block: Optional[int]
    value: float
    limit: float
    detail: str = ""

    def as_dict(self) -> dict:
        return {"kind": self.kind, "where": self.where, "block": self.block, "value": self.value,
                "limit": self.limit, "detail": self.detail}


@dataclass
class VerifyReport:
    ok: bool
    violations: List[Violation]
    settings: VerifySettings
    summary: Dict[str, float] = field(default_factory=dict)
    sim: Optional[SimResult] = None

    def kinds(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for v in self.violations:
            out[v.kind] = out.get(v.kind, 0) + 1
        return out

    def as_dict(self) -> dict:
        return {"ok": self.ok, "n_violations": len(self.violations), "kinds": self.kinds(),
                "violations": [v.as_dict() for v in self.violations[:50]], "summary": self.summary,
                "settings": {"ambient_offset_c": self.settings.ambient_offset_c, "thermal_factor": self.settings.thermal_factor,
                             "participation": self.settings.participation, "solar_quantile": self.settings.solar_quantile}}


def verify(plan: Plan, scenario: Scenario, cfg: SunflowConfig, settings: Optional[VerifySettings] = None,
           night_comp: Optional[Dict[str, float]] = None, irrigation_deferred: bool = False,
           grid: TimeGrid = TimeGrid()) -> VerifyReport:
    st = settings or VerifySettings.from_config(cfg)
    limit = st.hot_spot_limit_c if st.hot_spot_limit_c is not None else cfg.thermal.hot_spot_limit_c
    night_comp = night_comp or {}
    viol: List[Violation] = []
    rules = cfg.rules
    w0, w1 = grid.block_of(rules.window_start), grid.block_of(rules.window_end)

    # 0: sanitise (malformed feeders are reported and treated as 'never energised' for the physical checks)
    clean: Plan = {}
    for f in cfg.feeders:
        raw = plan.get(f.name, np.zeros(grid.N, dtype=int))
        try:
            u = np.asarray(raw, dtype=int)
        except (TypeError, ValueError):
            u = np.array([])
        if u.shape != (grid.N,) or not set(np.unique(u)).issubset({0, 1}):
            viol.append(Violation("malformed_plan", f.name, None, float(u.size), float(grid.N), "plan must be 96 binary blocks"))
            clean[f.name] = np.zeros(grid.N, dtype=int)
        else:
            clean[f.name] = u
    plan = clean

    # 1-3: structural rules per feeder
    starts_all: List[tuple] = []
    for f in cfg.feeders:
        u = plan[f.name]
        if any(v.kind == "malformed_plan" and v.where == f.name for v in viol):
            continue
        outside = int(u[:w0].sum() + u[w1:].sum())
        if outside:
            viol.append(Violation("outside_window", f.name, None, outside, 0, "energised outside the operating window"))
        avail = scenario.feeder_available(f.name)
        bad = np.where((u == 1) & (avail == 0))[0]
        if bad.size:
            viol.append(Violation("energised_during_outage", f.name, int(bad[0]), float(bad.size), 0))
        on = int(u.sum())
        nc = float(night_comp.get(f.name, 0.0))
        if nc > rules.max_night_compensation_blocks + 1e-6:
            viol.append(Violation("night_compensation_cap", f.name, None, nc, rules.max_night_compensation_blocks))
        if on + nc < rules.min_blocks_per_feeder - 1e-6:
            viol.append(Violation("supply_hours", f.name, None, on, rules.min_blocks_per_feeder, "fewer than 8 h incl. night compensation"))
        spells = plan_spells(u)
        if len(spells) > rules.max_spells:
            viol.append(Violation("too_many_spells", f.name, None, len(spells), rules.max_spells))
        for (a, b) in spells:
            if b - a < min(rules.min_spell_blocks, rules.min_blocks_per_feeder) and len(spells) > 1:
                viol.append(Violation("short_spell", f.name, a, b - a, rules.min_spell_blocks))
            starts_all.append((a, f.name))
        for i in range(1, len(spells)):
            gap = spells[i][0] - spells[i - 1][1]
            if gap < rules.min_off_blocks_between_spells:
                viol.append(Violation("short_off_time", f.name, spells[i][0], gap, rules.min_off_blocks_between_spells))
        req = int(scenario.irrigation_required_blocks.get(f.name, 0))
        if req > 0 and on < req and not irrigation_deferred:
            viol.append(Violation("irrigation_minimum", f.name, None, on, req, "fewer blocks than today's irrigation requirement"))
        if scenario.announced_plan is not None and f.name in scenario.announced_plan:
            ann = np.asarray(scenario.announced_plan[f.name], dtype=int)
            locked = np.arange(grid.N) < scenario.lock_until
            expected = np.minimum(ann, avail)
            diff = np.where(locked & (u != expected))[0]
            if diff.size:
                viol.append(Violation("locked_block_changed", f.name, int(diff[0]), float(diff.size), 0))
    # start separation across feeders
    starts_sorted = sorted(starts_all)
    for (a, fa), (b, fb) in zip(starts_sorted, starts_sorted[1:]):
        if b - a < rules.min_start_separation_blocks:
            viol.append(Violation("start_separation", f"{fa}/{fb}", b, b - a, rules.min_start_separation_blocks))

    # 4-7: physical rules under pessimistic settings
    sim = simulate(plan, scenario, cfg, participation=st.participation, thermal_factor=st.thermal_factor,
                   ambient_offset_c=st.ambient_offset_c, solar_quantile=st.solar_quantile, grid=grid)
    for p, kva in sim.pt_kva.items():
        over = np.where(kva > sim.pt_rating_kva[p] + 1e-6)[0]
        if over.size:
            viol.append(Violation("pt_rating", p, int(over[0]), float(kva.max()), sim.pt_rating_kva[p], f"{over.size} blocks over rating"))
    # switching cap: kVA switched per block (starts and stops), at surge level
    from ..simulation.feeder_model import FeederModel
    fm = FeederModel(cfg, scenario.failed_dts)
    switched = np.zeros(grid.N)
    for f in cfg.feeders:
        u = plan[f.name]
        prev = np.concatenate([[0], u[:-1]])
        events = (u != prev).astype(float)
        switched += events * fm.feeder_installed_kva(f.name) * cfg.participation.surge_level
    over = np.where(switched > rules.substation_switch_cap_kva + 1e-6)[0]
    if over.size:
        viol.append(Violation("switching_cap", "substation", int(over[0]), float(switched.max()), rules.substation_switch_cap_kva))
    max_hot = -1e9
    for did, trace in sim.dt_hot_spot_c.items():
        if np.all(np.isnan(trace)):
            continue
        mx = float(np.nanmax(trace))
        max_hot = max(max_hot, mx)
        if mx > limit + 1e-6:
            viol.append(Violation("hot_spot", did, int(np.nanargmax(trace)), mx, limit, f"feeder {sim.dt_feeder[did]}"))

    summary = {
        "max_hot_spot_c": max_hot if max_hot > -1e8 else float("nan"),
        "pt_max_loading_frac": sim.metrics["pt_max_loading_frac"],
        "pt2_max_loading_frac": sim.metrics["pt2_max_loading_frac"],
        "import_kwh": sim.metrics["import_kwh"],
        "exceedance_blocks": sim.metrics["dt_exceedance_blocks"],
    }
    return VerifyReport(ok=len(viol) == 0, violations=viol, settings=st, summary=summary, sim=sim)

"""Truth engine: simulate any plan under a scenario with the full nonlinear physics.

Used by the baseline replay, the verifier (with pessimistic settings) and the evaluation runner. The optimiser
never calls this module; it builds its own linear constraints from the physics helpers.
"""
from __future__ import annotations

from typing import Dict, Optional

import numpy as np

from ..core.config import SunflowConfig
from ..core.timegrid import TimeGrid
from ..physics.transformer_thermal import ThermalParams, simulate_thermal
from .feeder_model import FeederModel
from .types import Plan, Scenario, SimResult, plan_starts


def simulate(plan: Plan, scenario: Scenario, cfg: SunflowConfig, participation: Optional[float] = None,
             thermal_factor: Optional[float] = None, ambient_offset_c: Optional[float] = None,
             solar_quantile: str = "p50", grid: TimeGrid = TimeGrid()) -> SimResult:
    fm = FeederModel(cfg, scenario.failed_dts)
    # scenario perturbations (heat wave, degraded DTs) compound with the caller's pessimistic settings
    part = participation if participation is not None else (scenario.participation if scenario.participation is not None else cfg.participation.default)
    tf = scenario.thermal_factor * (thermal_factor if thermal_factor is not None else 1.0)
    amb_off = scenario.ambient_offset_c + (ambient_offset_c if ambient_offset_c is not None else 0.0)
    params = ThermalParams.from_config(cfg.thermal).scaled(tf)
    ambient = np.asarray(scenario.ambient_c, dtype=float) + amb_off
    pv_mw = np.asarray(scenario.pv(solar_quantile), dtype=float)
    N = grid.N
    pf = cfg.pumps.power_factor

    feeder_kva: Dict[str, np.ndarray] = {}
    effective_plan: Plan = {}
    violations = []
    for f in cfg.feeders:
        raw = plan.get(f.name, np.zeros(N, dtype=int))
        try:
            u = np.asarray(raw, dtype=int)
        except (TypeError, ValueError):
            u = np.zeros(N, dtype=int)
        if u.shape != (N,) or not set(np.unique(u)).issubset({0, 1}):
            violations.append({"kind": "malformed_plan", "feeder": f.name, "blocks": []})
            u = np.zeros(N, dtype=int)
        avail = scenario.feeder_available(f.name)
        if np.any((u == 1) & (avail == 0)):
            violations.append({"kind": "energised_during_outage", "feeder": f.name,
                               "blocks": [int(t) for t in np.where((u == 1) & (avail == 0))[0]]})
        u_eff = u * avail
        effective_plan[f.name] = u_eff
        feeder_kva[f.name] = fm.feeder_kva_series(f.name, u_eff, part)

    pt_kva = {p.name: sum(feeder_kva[fn] for fn in fm.pt_feeders()[p.name]) for p in cfg.power_transformers}
    pt_rating = {p.name: p.rating_kva for p in cfg.power_transformers}
    load_kw = sum(feeder_kva.values()) * pf
    pv_kw = pv_mw * 1000.0
    import_kw = np.clip(load_kw - pv_kw, 0, None)
    surplus_kw = np.clip(pv_kw - load_kw, 0, None)

    dt_hot: Dict[str, np.ndarray] = {}
    dt_age: Dict[str, float] = {}
    dt_rating: Dict[str, float] = {}
    dt_feeder: Dict[str, str] = {}
    exceed_blocks = 0
    max_hot = -1e9
    for f in cfg.feeders:
        for did in fm.feeder_dts[f.name]:
            dt = fm.dts[did]
            dt_rating[did] = dt.rating_kva
            dt_feeder[did] = f.name
            if dt.failed:
                dt_hot[did] = np.full(N, np.nan)
                dt_age[did] = 0.0
                continue
            K = fm.dt_load_factor_series(did, effective_plan[f.name], part)
            tr = simulate_thermal(K, ambient, params, grid.dt_min)
            dt_hot[did] = tr.hot_spot_c
            dt_age[did] = tr.ageing_hours
            exceed_blocks += tr.exceedance_blocks(cfg.thermal.hot_spot_limit_c)
            max_hot = max(max_hot, tr.max_hot_spot)

    dt_h = grid.dt_h
    solar_hour = pv_kw >= 0.2 * cfg.plant.capacity_mw_ac * 1000.0
    total_ha = sum(fm.irrigated_ha(f.name) for f in cfg.feeders)
    per_feeder: Dict[str, Dict[str, float]] = {}
    switchings = 0
    changes_vs_announced = 0
    irrigation_shortfall_blocks = 0
    for f in cfg.feeders:
        u = effective_plan[f.name]
        starts = plan_starts(u)
        hours_blocks = int(u.sum())
        req = int(scenario.irrigation_required_blocks.get(f.name, 0))
        shortfall = max(0, req - hours_blocks)
        irrigation_shortfall_blocks += shortfall
        sw = len(starts) + len(plan_starts(1 - u)) - (1 if u[0] == 1 else 0) - (1 if u[-1] == 1 else 0)
        sw = max(sw, 2 * len(starts)) if hours_blocks else 0
        switchings += sw
        if scenario.announced_plan is not None and f.name in scenario.announced_plan:
            ann = np.asarray(scenario.announced_plan[f.name], dtype=int)
            if ann.shape == u.shape:
                changes_vs_announced += int(np.sum(u != ann))
        per_feeder[f.name] = {
            "blocks_on": hours_blocks,
            "hours_on": hours_blocks * dt_h,
            "starts": starts,
            "required_blocks": req,
            "shortfall_blocks": shortfall,
            "energy_kwh": float(feeder_kva[f.name].sum() * pf * dt_h),
            "irrigated_ha": fm.irrigated_ha(f.name),
        }

    load_kwh = float(load_kw.sum() * dt_h)
    import_kwh = float(import_kw.sum() * dt_h)
    import_nonsolar_kwh = float(import_kw[~solar_hour].sum() * dt_h)
    surplus_kwh = float(surplus_kw.sum() * dt_h)
    pv_kwh = float(pv_kw.sum() * dt_h)
    solar_used_kwh = float(np.minimum(load_kw, pv_kw).sum() * dt_h)
    pt_overload_blocks = int(sum(np.sum(pt_kva[p] > pt_rating[p] + 1e-6) for p in pt_kva))
    pt_max_loading = {p: float(pt_kva[p].max() / pt_rating[p]) for p in pt_kva}
    ageing_total = float(sum(dt_age.values()))
    metrics = {
        "load_kwh": load_kwh,
        "pv_kwh": pv_kwh,
        "import_kwh": import_kwh,
        "import_nonsolar_kwh": import_nonsolar_kwh,
        "surplus_kwh": surplus_kwh,
        "solar_used_kwh": solar_used_kwh,
        "solar_used_frac_of_pv": (solar_used_kwh / pv_kwh) if pv_kwh > 0 else 0.0,
        "solar_share_of_load": (solar_used_kwh / load_kwh) if load_kwh > 0 else 0.0,
        "pt_overload_blocks": pt_overload_blocks,
        "pt_max_loading_frac": max(pt_max_loading.values()) if pt_max_loading else 0.0,
        "pt2_max_loading_frac": pt_max_loading.get("PT-2", 0.0),
        "dt_max_hot_spot_c": float(max_hot) if max_hot > -1e8 else float("nan"),
        "dt_exceedance_blocks": int(exceed_blocks),
        "dt_ageing_hours_total": ageing_total,
        "dt_ageing_hours_mean": ageing_total / max(1, sum(1 for d in fm.dts.values() if not d.failed)),
        "switchings": int(switchings),
        "changes_vs_announced_blocks": int(changes_vs_announced),
        "irrigation_shortfall_blocks": int(irrigation_shortfall_blocks),
        "import_kwh_per_ha": import_kwh / total_ha if total_ha else 0.0,
        "import_cost_inr": import_kwh * cfg.economics.appc_inr_per_kwh,
        "surplus_value_lost_inr": surplus_kwh * (cfg.economics.appc_inr_per_kwh - cfg.economics.surplus_value_inr_per_kwh),
        "participation": float(part),
        "thermal_factor": float(tf),
        "ambient_offset_c": float(amb_off),
    }
    return SimResult(
        plan={f: effective_plan[f] for f in effective_plan},
        blocks=[grid.label(t) for t in range(N)], pv_mw=pv_mw, load_kw=load_kw, import_kw=import_kw,
        surplus_kw=surplus_kw, feeder_kva=feeder_kva, pt_kva=pt_kva, pt_rating_kva=pt_rating,
        dt_hot_spot_c=dt_hot, dt_rating_kva=dt_rating, dt_feeder=dt_feeder, dt_ageing_hours=dt_age,
        metrics=metrics, per_feeder=per_feeder, violations=violations,
    )

"""Assemble the numeric inputs of the MILP from config + scenario (no Pyomo here).

Thermal classes: distribution transformers on the same feeder with the same rating and the same carried load have
identical temperature trajectories, so they are modelled once with a multiplicity. This keeps the MILP small
without any approximation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from ..core.config import SunflowConfig, Weights
from ..core.timegrid import TimeGrid
from ..physics.transformer_thermal import ThermalParams, lag_coefficients, oil_rise_input, hotspot_rise_input
from ..simulation.feeder_model import FeederModel
from ..simulation.types import Scenario


@dataclass
class ThermalClass:
    key: str
    feeder: str
    rating_kva: float
    K_on: float                  # per-unit load at participation 1.0
    multiplicity: int
    dt_ids: List[str]
    # forcing constants per load state (off / default participation / surge)
    g_o: Dict[str, float] = field(default_factory=dict)
    g_h: Dict[str, float] = field(default_factory=dict)


@dataclass
class SolveOptions:
    use_thermal: bool = True
    use_pt_rating: bool = True
    use_switch_cap: bool = True
    use_start_separation: bool = True
    use_irrigation: bool = True
    irrigation_hard: bool = True
    use_fairness: bool = True
    use_stability: bool = True
    use_surplus: bool = True
    allow_night_compensation: bool = True
    max_night_blocks_override: Optional[int] = None   # conflict attribution only: lift the night-compensation cap
    max_spells: Optional[int] = None
    split_lattice_blocks: int = 1               # time lattice (blocks) for the first start and the gap of two-spell patterns
    split_night_options: str = "cap"            # two-spell patterns with night compensation: only at the cap ("cap") or every allowed value ("all")
    thermal_margin_c: Optional[float] = None
    participation: Optional[float] = None       # planning participation (default: verification P90 value)
    robust: bool = True                         # plan under the verifier's pessimistic thermal/ambient settings
    time_limit_s: float = 30.0
    mip_gap: float = 0.005
    solar_quantile_for_import: Optional[str] = None


@dataclass
class PlanInputs:
    feeders: List[str]
    N: int
    dt_h: float
    window: List[int]                           # blocks inside the operating window
    avail: Dict[str, np.ndarray]                # feeder -> 0/1 per block (window and outages)
    base_kva: Dict[str, float]                  # feeder installed kVA at participation 1.0 (with DT failures carried)
    p_def: float
    p_surge: float
    surge_blocks: int
    pf: float
    pt_feeders: Dict[str, List[str]]
    pt_rating: Dict[str, float]
    pv_import_kw: np.ndarray                    # pessimistic PV used for import
    pv_surplus_kw: np.ndarray                   # expected PV used for surplus
    ambient_c: np.ndarray
    thermal_params: ThermalParams
    a_o: float
    a_h1: float
    a_h2: float
    init_oil_rise: float
    thermal_classes: List[ThermalClass]
    hot_spot_limit_c: float
    thermal_margin_c: float
    ageing_reference_c: float
    min_blocks: int
    max_spells: int
    min_spell_blocks: int
    min_off_blocks: int
    start_separation: int
    switch_cap_kva: float
    max_night_blocks: int
    irrigation_required: Dict[str, int]
    urgency: Dict[str, float]
    preferred_start: Dict[str, int]
    announced: Optional[Dict[str, np.ndarray]]
    lock_until: int
    weights: Weights
    options: SolveOptions
    initial_state: Dict[str, Dict[str, float]] = field(default_factory=dict)  # class key -> {o,h1,h2} at t=-1
    forced_starts: Dict[str, int] = field(default_factory=dict)             # feeder -> block (contrastive what-if)


def build_inputs(cfg: SunflowConfig, scenario: Scenario, weights: Weights, options: Optional[SolveOptions] = None,
                 grid: TimeGrid = TimeGrid(), initial_state: Optional[Dict[str, Dict[str, float]]] = None) -> PlanInputs:
    options = options or SolveOptions()
    fm = FeederModel(cfg, scenario.failed_dts)
    N = grid.N
    w0, w1 = grid.block_of(cfg.rules.window_start), grid.block_of(cfg.rules.window_end)
    window = list(range(w0, w1))
    in_window = np.zeros(N, dtype=int); in_window[w0:w1] = 1
    avail = {f.name: in_window * scenario.feeder_available(f.name) for f in cfg.feeders}

    # Robust planning: constraints are built under the same pessimistic assumptions the verifier will use
    # (P90 participation, upper thermal band, ambient offset), compounded with any scenario perturbation.
    v = cfg.verification
    p_def = options.participation if options.participation is not None else (
        scenario.participation if scenario.participation is not None else v.participation)
    p_def = float(min(max(p_def, 0.0), 1.0))
    p_surge = float(max(cfg.participation.surge_level, p_def))

    params = ThermalParams.from_config(cfg.thermal).scaled(scenario.thermal_factor * (v.thermal_factor if options.robust else 1.0))
    a_o, a_h1, a_h2 = lag_coefficients(params, grid.dt_min)
    classes: Dict[str, ThermalClass] = {}
    for f in cfg.feeders:
        for did in fm.feeder_dts[f.name]:
            dt = fm.dts[did]
            if dt.failed:
                continue
            key = f"{f.name}|{int(dt.rating_kva)}|{dt.K_on:.6f}"
            if key not in classes:
                tc = ThermalClass(key=key, feeder=f.name, rating_kva=dt.rating_kva, K_on=dt.K_on, multiplicity=0, dt_ids=[])
                for state, K in (("off", 0.0), ("def", dt.K_on * p_def), ("surge", dt.K_on * p_surge)):
                    tc.g_o[state] = float(oil_rise_input(K, params))
                    tc.g_h[state] = float(hotspot_rise_input(K, params))
                classes[key] = tc
            classes[key].multiplicity += 1
            classes[key].dt_ids.append(did)

    q_imp = options.solar_quantile_for_import or weights.solar_quantile_for_import
    pv_import = np.asarray(scenario.pv(q_imp), dtype=float) * 1000.0
    pv_surplus = np.asarray(scenario.pv(weights.solar_quantile_for_surplus), dtype=float) * 1000.0
    ambient = np.asarray(scenario.ambient_c, dtype=float) + scenario.ambient_offset_c + (v.ambient_offset_c if options.robust else 0.0)

    margin = options.thermal_margin_c if options.thermal_margin_c is not None else weights.thermal_margin_c
    announced = None
    if scenario.announced_plan is not None:
        announced = {f: np.asarray(scenario.announced_plan[f], dtype=int) for f in scenario.announced_plan}

    return PlanInputs(
        feeders=[f.name for f in cfg.feeders], N=N, dt_h=grid.dt_h, window=window, avail=avail,
        base_kva={f.name: fm.feeder_installed_kva(f.name) for f in cfg.feeders},
        p_def=p_def, p_surge=p_surge, surge_blocks=int(cfg.participation.surge_blocks), pf=cfg.pumps.power_factor,
        pt_feeders=fm.pt_feeders(), pt_rating={p.name: p.rating_kva for p in cfg.power_transformers},
        pv_import_kw=pv_import, pv_surplus_kw=pv_surplus, ambient_c=ambient, thermal_params=params,
        a_o=a_o, a_h1=a_h1, a_h2=a_h2, init_oil_rise=params.initial_top_oil_rise_k,
        thermal_classes=list(classes.values()), hot_spot_limit_c=cfg.thermal.hot_spot_limit_c,
        thermal_margin_c=float(margin), ageing_reference_c=cfg.thermal.ageing_reference_c,
        min_blocks=cfg.rules.min_blocks_per_feeder,
        max_spells=int(options.max_spells if options.max_spells is not None else cfg.rules.max_spells),
        min_spell_blocks=cfg.rules.min_spell_blocks, min_off_blocks=cfg.rules.min_off_blocks_between_spells,
        start_separation=cfg.rules.min_start_separation_blocks, switch_cap_kva=cfg.rules.substation_switch_cap_kva,
        max_night_blocks=(options.max_night_blocks_override if options.max_night_blocks_override is not None
                          else (cfg.rules.max_night_compensation_blocks if options.allow_night_compensation else 0)),
        irrigation_required={f.name: int(scenario.irrigation_required_blocks.get(f.name, 0)) for f in cfg.feeders},
        urgency={f.name: float(scenario.irrigation_urgency.get(f.name, 0.0)) for f in cfg.feeders},
        preferred_start={f.name: int(scenario.preferred_start.get(f.name, w0)) for f in cfg.feeders},
        announced=announced, lock_until=int(scenario.lock_until), weights=weights, options=options,
        initial_state=initial_state or {},
    )

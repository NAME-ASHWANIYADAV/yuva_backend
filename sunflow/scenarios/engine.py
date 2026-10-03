"""What-if engine: transform a base scenario into a named or random stress scenario."""
from __future__ import annotations

import copy
from datetime import date
from typing import Dict, Optional

import numpy as np

from ..core.config import SunflowConfig
from ..core.timegrid import TimeGrid
from ..simulation.feeder_model import FeederModel
from ..simulation.types import Scenario
from ..simulation.weather import scenario_from_era5_day
from .library import pick_hottest_day, pick_worst_ramp_day


def apply_scenario(cfg: SunflowConfig, base: Scenario, kind: str, grid: TimeGrid = TimeGrid(), **p) -> Scenario:
    sc = copy.deepcopy(base)
    sc.label = f"{base.label} + {kind}"
    if kind == "cloud_ramp":
        day = p.get("day") or pick_worst_ramp_day(p.get("year", 2025))
        real = scenario_from_era5_day(cfg, day, with_irrigation=False)
        ratio = np.divide(real.pv_p50_mw, np.maximum(base.pv_p50_mw, 1e-6), out=np.ones_like(real.pv_p50_mw), where=base.pv_p50_mw > 1e-6)
        sc.pv_p50_mw = real.pv_p50_mw
        sc.pv_p10_mw = (base.pv_p10_mw * ratio) if base.pv_p10_mw is not None else 0.8 * real.pv_p50_mw
        sc.pv_p90_mw = (base.pv_p90_mw * ratio) if base.pv_p90_mw is not None else np.minimum(1.1 * real.pv_p50_mw, cfg.plant.capacity_mw_ac)
        sc.weather_source = f"solar from real ERA5 day {day.isoformat()} (worst midday ramp of {day.year})"
    elif kind == "heat_wave":
        day = p.get("day") or pick_hottest_day(p.get("year", 2025))
        real = scenario_from_era5_day(cfg, day, with_irrigation=False)
        sc.ambient_c = np.maximum(base.ambient_c, real.ambient_c)
        sc.ambient_offset_c = base.ambient_offset_c + float(p.get("offset_c", 0.0))
        sc.weather_source = f"ambient from real ERA5 day {day.isoformat()} (hottest of {day.year}) + {sc.ambient_offset_c:.1f} C"
    elif kind == "dt_failure":
        fm = FeederModel(cfg)
        ids = fm.feeder_dts["Chalburga"]
        mid = len(ids) // 2
        # default: a 63 kVA unit in the middle of Chalburga (its 100 kVA neighbours can absorb part of its pumps)
        dt_id = p.get("dt_id") or next((d for d in ids[mid:] if fm.dts[d].rating_kva == 63), ids[mid])
        sc.failed_dts = set(base.failed_dts) | {dt_id}
    elif kind == "feeder_outage":
        feeder = p.get("feeder", "Kharosa")
        t0 = grid.block_of(p.get("start", "11:00")); t1 = grid.block_of(p.get("end", "13:00"))
        sc.feeder_outages = dict(base.feeder_outages)
        sc.feeder_outages[feeder] = sc.feeder_outages.get(feeder, []) + [(t0, t1)]
    elif kind == "full_participation":
        sc.participation = 1.0
    elif kind == "impossible":
        sc.feeder_outages = dict(base.feeder_outages)
        sc.feeder_outages["Kharosa"] = sc.feeder_outages.get("Kharosa", []) + [(grid.block_of("07:30"), grid.block_of("15:30"))]
        hot = pick_hottest_day(p.get("year", 2025))
        real = scenario_from_era5_day(cfg, hot, with_irrigation=False)
        sc.ambient_c = np.maximum(base.ambient_c, real.ambient_c)
        sc.ambient_offset_c = base.ambient_offset_c + 4.0
        sc.weather_source = f"outage 07:30-15:30 on Kharosa + hottest day {hot.isoformat()} + 4 C"
    elif kind == "farmer_request":
        pass  # handled by explain_request; the scenario is unchanged
    else:
        raise ValueError(f"unknown scenario kind {kind}")
    return sc


def named_scenario(cfg: SunflowConfig, base: Scenario, kind: str, **p) -> Scenario:
    return apply_scenario(cfg, base, kind, **p)


def random_scenario(cfg: SunflowConfig, base: Scenario, seed: int, grid: TimeGrid = TimeGrid()) -> Scenario:
    """Seeded random stress scenario for sweeps: participation, thermal band, ambient offset, random DT failure/outage."""
    rng = np.random.default_rng(seed)
    sc = copy.deepcopy(base)
    sc.participation = float(rng.uniform(*cfg.participation.sweep_range))
    sc.thermal_factor = float(rng.uniform(1.0 - cfg.thermal.uncertainty_band, 1.0 + cfg.thermal.uncertainty_band))
    sc.ambient_offset_c = float(rng.uniform(-2.0, 6.0))
    fm = FeederModel(cfg)
    if rng.random() < 0.3:
        f = rng.choice([x.name for x in cfg.feeders])
        sc.failed_dts = {str(rng.choice(fm.feeder_dts[f]))}
    if rng.random() < 0.2:
        f = str(rng.choice([x.name for x in cfg.feeders]))
        t0 = int(rng.integers(grid.block_of("08:00"), grid.block_of("15:00")))
        sc.feeder_outages = {f: [(t0, min(t0 + int(rng.integers(2, 9)), grid.block_of("17:30")))]}
    for f in cfg.feeders:
        sc.irrigation_urgency[f.name] = float(rng.uniform(0.0, 1.0))
        sc.irrigation_required_blocks[f.name] = int(rng.choice([0, 16, 24, 32]))
    sc.label = f"{base.label} + random seed {seed}"
    return sc

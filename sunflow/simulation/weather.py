"""Build scenarios from real weather days (ERA5 reanalysis, PUBLIC) in the local cache."""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ..core.config import SunflowConfig
from ..core.timegrid import TimeGrid
from ..data.cache import cache_file
from ..physics.pv import day_profile_from_hourly
from ..physics.irrigation import CropCalendar, SoilBucket, FeederIrrigation
from .feeder_model import FeederModel
from .types import Scenario


@lru_cache(maxsize=1)
def load_era5_hourly() -> pd.DataFrame:
    path = cache_file("era5_hourly_latur")
    if not path.exists():
        raise FileNotFoundError("ERA5 cache missing; run scripts/fetch_data.py")
    df = pd.read_csv(path)
    df["time"] = pd.to_datetime(df["time"])
    df["date"] = df["time"].dt.date
    return df


@lru_cache(maxsize=1)
def load_daily_agro() -> pd.DataFrame:
    path = cache_file("era5_daily_agro_latur")
    if not path.exists():
        raise FileNotFoundError("daily agro cache missing; run scripts/fetch_data.py")
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df.set_index("date")


def available_days() -> List[date]:
    df = load_era5_hourly()
    counts = df.groupby("date").size()
    return [d for d, n in counts.items() if n == 24]


def _day_rows(day: date) -> pd.DataFrame:
    df = load_era5_hourly()
    rows = df[df["date"] == day]
    if len(rows) != 24:
        raise KeyError(f"no complete ERA5 day for {day}")
    return rows


def irrigation_state_for_day(cfg: SunflowConfig, day: date, warmup_days: int = 60) -> Dict[str, Dict[str, float]]:
    """Run the FAO-56 bucket for each feeder from `warmup_days` before `day`, assuming the published 8 h were
    delivered each day, and return today's requirement/urgency per feeder."""
    agro = load_daily_agro()
    fm = FeederModel(cfg)
    empty = {"required_blocks": 0, "needed_blocks_total": 0, "urgency": 0.0, "critical": False, "depletion_mm": 0.0, "requirement_mm": 0.0, "crop": None}
    out: Dict[str, Dict[str, float]] = {}
    for f in cfg.feeders:
        # one soil bucket per crop in the rotation; the crop in season on `day` sets the feeder's requirement
        buckets = {}
        for g in f.crop_groups():
            cal = CropCalendar(cfg.crops[g])
            buckets[g] = (cal, FeederIrrigation(f.name, SoilBucket.initial(cal, cfg.irrigation), fm.irrigated_ha(f.name), fm.n_pumps(f.name),
                                                cfg.pumps.discharge_m3_per_h, cfg.irrigation.application_efficiency))
        plans = {g: None for g in buckets}
        for k in range(warmup_days, -1, -1):
            d = day - timedelta(days=k)
            if d not in agro.index:
                continue
            row = agro.loc[d]
            for g, (cal, fi) in buckets.items():
                if not cal.in_season(d):
                    continue
                plans[g] = fi.plan_for_day(d, float(row["et0"]), float(row["rain"]), cfg.rules.min_blocks_per_feeder)
                if k > 0:
                    fi.deliver(min(plans[g]["needed_blocks_total"], cfg.rules.min_blocks_per_feeder))
        active = [g for g, (cal, _) in buckets.items() if cal.in_season(day) and plans[g] is not None]
        if active:
            g = max(active, key=lambda x: plans[x]["urgency"])
            out[f.name] = dict(plans[g], crop=g)
        else:
            out[f.name] = dict(empty)
    return out


def scenario_from_era5_day(cfg: SunflowConfig, day: date, pv_band: Optional[Dict[str, np.ndarray]] = None,
                           with_irrigation: bool = True, grid: TimeGrid = TimeGrid()) -> Scenario:
    rows = _day_rows(day)
    pv, ambient, _ = day_profile_from_hourly(rows[["time", "ghi", "temp"]], cfg.plant, cfg.site, grid)
    sc = Scenario(day=day, pv_p50_mw=pv, ambient_c=ambient, label=f"era5 {day.isoformat()}", weather_source="era5 (reanalysis, PUBLIC)")
    if pv_band is not None:
        sc.pv_p10_mw = pv_band.get("p10")
        sc.pv_p90_mw = pv_band.get("p90")
        if "p50" in pv_band:
            sc.pv_p50_mw = pv_band["p50"]
    if with_irrigation:
        st = irrigation_state_for_day(cfg, day)
        sc.irrigation_required_blocks = {f: int(v["required_blocks"]) for f, v in st.items()}
        sc.irrigation_urgency = {f: float(v["urgency"]) for f, v in st.items()}
    # fairness rotation: preferred start rotates daily among the published starts (PUBLIC-derived)
    starts = sorted(grid.block_of(f.published_slot[0]) for f in cfg.feeders)
    k = day.toordinal() % len(cfg.feeders)
    sc.preferred_start = {f.name: starts[(i + k) % len(starts)] for i, f in enumerate(cfg.feeders)}
    return sc

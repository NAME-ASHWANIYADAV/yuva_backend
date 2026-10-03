"""Real weather events from the ERA5 archive (PUBLIC) used by the what-if engine."""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Dict

import numpy as np
import pandas as pd

from ..simulation.weather import load_era5_hourly, load_daily_agro

SCENARIO_KINDS = ["cloud_ramp", "heat_wave", "dt_failure", "feeder_outage", "farmer_request", "full_participation", "impossible"]


def describe_kinds() -> Dict[str, str]:
    return {
        "cloud_ramp": "Solar follows the worst real midday cloud ramp day of the test year (ERA5 record).",
        "heat_wave": "Ambient follows the hottest real day of the test year (ERA5 record) plus an optional offset.",
        "dt_failure": "A distribution transformer fails; its pumps are carried by the two neighbouring DTs.",
        "feeder_outage": "A feeder is unavailable for a window (line fault / maintenance).",
        "farmer_request": "A feeder's farmers ask for a different start time (answered by contrastive re-solve).",
        "full_participation": "Every pump draws for the whole spell (participation 1.0).",
        "impossible": "Outage leaving too little window plus a heat wave: no plan satisfies every hard rule.",
    }


@lru_cache(maxsize=4)
def pick_worst_ramp_day(year: int = 2025) -> date:
    """Day with the largest drop in GHI between consecutive hours inside 10:00-16:00 (relative to the day's max)."""
    df = load_era5_hourly()
    d = df[df["time"].dt.year == year].copy()
    d["hour"] = d["time"].dt.hour
    mid = d[(d["hour"] >= 10) & (d["hour"] <= 16)]
    best_day, best = None, -1.0
    for day, g in mid.groupby("date"):
        if g["ghi"].max() < 500:  # skip overcast days: a ramp needs sun first
            continue
        drops = -np.diff(g["ghi"].values)
        score = float(drops.max()) if len(drops) else 0.0
        if score > best:
            best, best_day = score, day
    return best_day


@lru_cache(maxsize=4)
def pick_hottest_day(year: int = 2025) -> date:
    agro = load_daily_agro()
    a = agro[[d.year == year for d in agro.index]]
    return a["tmax"].idxmax()

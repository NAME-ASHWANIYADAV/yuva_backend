"""Open-Meteo clients (key-free; non-commercial terms apply).

Datasets used (all PUBLIC):
- ERA5 reanalysis hourly (archive-api): shortwave_radiation, direct_normal_irradiance, diffuse_radiation,
  temperature_2m, cloud_cover. Used as the primary 'actual' proxy. ERA5 is a reanalysis, not a ground measurement.
- Historical Forecast API (archived model runs, explicit models icon_seamless / gfs_seamless / ecmwf_ifs025):
  the day-ahead NWP the forecast-error model learns to correct. Never use `best_match` (at Latur it reproduces
  the analysis itself and would leak the target).
- Daily agro variables from the ERA5 archive: et0_fao_evapotranspiration, precipitation_sum, temperature_2m_max.
- Live forecast API for the demo's 'today/tomorrow' band.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, Iterable, List, Tuple

import pandas as pd
import requests

from ..core.logging import get_logger

log = get_logger("sunflow.data")

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
HIST_FORECAST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

HOURLY_VARS = ["shortwave_radiation", "direct_normal_irradiance", "diffuse_radiation", "temperature_2m", "cloud_cover"]
NWP_VARS = ["shortwave_radiation", "temperature_2m", "cloud_cover"]
DAILY_VARS = ["et0_fao_evapotranspiration", "precipitation_sum", "temperature_2m_max", "temperature_2m_min"]
RENAME = {
    "shortwave_radiation": "ghi", "direct_normal_irradiance": "dni", "diffuse_radiation": "dhi",
    "temperature_2m": "temp", "cloud_cover": "cloud",
    "et0_fao_evapotranspiration": "et0", "precipitation_sum": "rain", "temperature_2m_max": "tmax",
    "temperature_2m_min": "tmin",
}


@dataclass(frozen=True)
class Location:
    latitude: float
    longitude: float
    timezone: str = "Asia/Kolkata"


LATUR = Location(18.4088, 76.5604)


def _get(url: str, params: dict, retries: int = 4, timeout: int = 120) -> dict:
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            r.raise_for_status()
            j = r.json()
            if "error" in j and j.get("error"):
                raise RuntimeError(j.get("reason", "open-meteo error"))
            return j
        except Exception as exc:  # network hiccup: back off and retry
            last = exc
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"open-meteo request failed after {retries} attempts: {last}")


def _year_chunks(start: date, end: date) -> Iterable[Tuple[date, date]]:
    cur = start
    while cur <= end:
        chunk_end = min(date(cur.year, 12, 31), end)
        yield cur, chunk_end
        cur = chunk_end + timedelta(days=1)


def _frame(j: dict, section: str) -> pd.DataFrame:
    block = j[section]
    df = pd.DataFrame(block)
    df = df.rename(columns={"time": "time", **RENAME})
    df["time"] = pd.to_datetime(df["time"])
    return df


def fetch_era5_hourly(start: date, end: date, loc: Location = LATUR) -> pd.DataFrame:
    """ERA5 hourly irradiance and temperature (local time). PUBLIC (Open-Meteo archive)."""
    frames: List[pd.DataFrame] = []
    for a, b in _year_chunks(start, end):
        log.info(f"fetch era5 hourly {a}..{b}")
        j = _get(ARCHIVE_URL, {
            "latitude": loc.latitude, "longitude": loc.longitude,
            "start_date": a.isoformat(), "end_date": b.isoformat(),
            "hourly": ",".join(HOURLY_VARS), "timezone": loc.timezone,
        })
        frames.append(_frame(j, "hourly"))
    df = pd.concat(frames, ignore_index=True)
    df["source"] = "era5"
    return df


def fetch_nwp_hourly(model: str, start: date, end: date, loc: Location = LATUR) -> pd.DataFrame:
    """Archived NWP forecasts for an explicit model (icon_seamless, gfs_seamless, ecmwf_ifs025). PUBLIC."""
    if model == "best_match":
        raise ValueError("best_match leaks the analysis at this site; use an explicit model")
    frames: List[pd.DataFrame] = []
    for a, b in _year_chunks(start, end):
        log.info(f"fetch nwp {model} {a}..{b}")
        j = _get(HIST_FORECAST_URL, {
            "latitude": loc.latitude, "longitude": loc.longitude,
            "start_date": a.isoformat(), "end_date": b.isoformat(),
            "hourly": ",".join(NWP_VARS), "models": model, "timezone": loc.timezone,
        })
        frames.append(_frame(j, "hourly"))
    df = pd.concat(frames, ignore_index=True)
    df["source"] = model
    return df


PREVIOUS_RUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"


def fetch_nwp_previous_day1(model: str, start: date, end: date, loc: Location = LATUR) -> pd.DataFrame:
    """Day-ahead NWP: the forecast for each hour as issued ONE DAY EARLIER (Previous-Runs API, PUBLIC).

    This is the honest input for an 18:00 day-ahead plan (lead times of roughly 6-30 h), as opposed to the
    Historical Forecast API whose archive keeps the latest short-lead run.
    """
    if model == "best_match":
        raise ValueError("best_match leaks the analysis at this site; use an explicit model")
    vars_ = ["shortwave_radiation_previous_day1", "temperature_2m_previous_day1", "cloud_cover_previous_day1"]
    frames: List[pd.DataFrame] = []
    for a, b in _year_chunks(start, end):
        log.info(f"fetch previous-day1 {model} {a}..{b}")
        j = _get(PREVIOUS_RUNS_URL, {
            "latitude": loc.latitude, "longitude": loc.longitude,
            "start_date": a.isoformat(), "end_date": b.isoformat(),
            "hourly": ",".join(vars_), "models": model, "timezone": loc.timezone,
        })
        df = pd.DataFrame(j["hourly"]).rename(columns={
            "shortwave_radiation_previous_day1": "ghi", "temperature_2m_previous_day1": "temp",
            "cloud_cover_previous_day1": "cloud"})
        df["time"] = pd.to_datetime(df["time"])
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df["source"] = f"{model}_day1"
    return df


def fetch_daily_agro(start: date, end: date, loc: Location = LATUR) -> pd.DataFrame:
    """Daily FAO-56 ET0, precipitation and temperature extremes from the ERA5 archive. PUBLIC."""
    frames: List[pd.DataFrame] = []
    for a, b in _year_chunks(start, end):
        log.info(f"fetch daily agro {a}..{b}")
        j = _get(ARCHIVE_URL, {
            "latitude": loc.latitude, "longitude": loc.longitude,
            "start_date": a.isoformat(), "end_date": b.isoformat(),
            "daily": ",".join(DAILY_VARS), "timezone": loc.timezone,
        })
        df = _frame(j, "daily").rename(columns={"time": "date"})
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df["source"] = "era5_daily"
    return df


def fetch_live_forecast(model: str = "icon_seamless", days: int = 3, loc: Location = LATUR) -> Dict[str, pd.DataFrame]:
    """Live forecast (hourly NWP + daily ET0/rain) for the demo's 'tomorrow'. PUBLIC."""
    j = _get(FORECAST_URL, {
        "latitude": loc.latitude, "longitude": loc.longitude,
        "hourly": ",".join(NWP_VARS), "daily": ",".join(DAILY_VARS),
        "models": model, "forecast_days": days, "timezone": loc.timezone,
    })
    hourly = _frame(j, "hourly")
    hourly["source"] = f"{model}_live"
    daily = _frame(j, "daily").rename(columns={"time": "date"})
    return {"hourly": hourly, "daily": daily}

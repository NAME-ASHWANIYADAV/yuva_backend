"""NASA POWER hourly point API (PUBLIC, key-free). Second, independent irradiance proxy."""
from __future__ import annotations

import time
from datetime import date, timedelta
from typing import List

import pandas as pd
import requests

from ..core.logging import get_logger
from .openmeteo import LATUR, Location

log = get_logger("sunflow.data")
URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"


def _chunks(start: date, end: date):
    cur = start
    while cur <= end:
        chunk_end = min(date(cur.year, 12, 31), end)
        yield cur, chunk_end
        cur = chunk_end + timedelta(days=1)


def fetch_nasa_power_hourly(start: date, end: date, loc: Location = LATUR) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []
    for a, b in _chunks(start, end):
        log.info(f"fetch nasa power hourly {a}..{b}")
        params = {
            "parameters": "ALLSKY_SFC_SW_DWN,T2M", "community": "RE",
            "longitude": loc.longitude, "latitude": loc.latitude,
            "start": a.strftime("%Y%m%d"), "end": b.strftime("%Y%m%d"),
            "format": "JSON", "time-standard": "LST",
        }
        for attempt in range(4):
            try:
                r = requests.get(URL, params=params, timeout=180)
                r.raise_for_status()
                p = r.json()["properties"]["parameter"]
                break
            except Exception as exc:
                if attempt == 3:
                    raise RuntimeError(f"NASA POWER failed: {exc}")
                time.sleep(3 * (attempt + 1))
        ghi = p["ALLSKY_SFC_SW_DWN"]
        t2m = p["T2M"]
        rows = [(pd.to_datetime(k, format="%Y%m%d%H"), v, t2m.get(k)) for k, v in ghi.items()]
        df = pd.DataFrame(rows, columns=["time", "ghi", "temp"])
        df.loc[df["ghi"] < 0, "ghi"] = float("nan")  # -999 fill values
        df.loc[df["temp"] < -100, "temp"] = float("nan")
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out["source"] = "nasa_power"
    return out

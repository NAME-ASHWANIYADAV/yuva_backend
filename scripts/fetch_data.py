"""Download all public datasets used by SUNFLOW into data/raw (idempotent, cached).

Run:  python scripts/fetch_data.py [--quick]
--quick fetches a short recent window only (for CI / first look).
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sunflow.data import (  # noqa: E402
    cached_frame, fetch_daily_agro, fetch_era5_hourly, fetch_nasa_power_hourly, fetch_nwp_hourly, fetch_nwp_previous_day1,
)
from sunflow.core.logging import get_logger  # noqa: E402

log = get_logger("sunflow.fetch")


def main(quick: bool) -> None:
    if quick:
        era_start, nwp_start, nasa_start, daily_start = date(2025, 1, 1), date(2025, 1, 1), date(2025, 1, 1), date(2024, 1, 1)
        end = date(2025, 3, 31)
    else:
        era_start, nwp_start, nasa_start, daily_start = date(2019, 1, 1), date(2022, 11, 24), date(2023, 1, 1), date(2015, 1, 1)
        end = date(2026, 9, 30)
    suffix = "_quick" if quick else ""
    df = cached_frame(f"era5_hourly_latur{suffix}", lambda: fetch_era5_hourly(era_start, end))
    log.info(f"era5 hourly rows={len(df)} {df['time'].min()}..{df['time'].max()}")
    for model in ("icon_seamless", "gfs_seamless"):
        start = nwp_start if model == "icon_seamless" else max(date(2022, 1, 1), nwp_start if quick else date(2022, 1, 1))
        d = cached_frame(f"nwp_{model}_latur{suffix}", lambda m=model, s=start: fetch_nwp_hourly(m, s, end))
        log.info(f"nwp {model} rows={len(d)} {d['time'].min()}..{d['time'].max()}")
    for model in ("icon_seamless", "gfs_seamless"):
        start = nwp_start if model == "icon_seamless" else (nwp_start if quick else date(2022, 1, 1))
        try:
            d = cached_frame(f"nwp_day1_{model}_latur{suffix}", lambda m=model, s=start: fetch_nwp_previous_day1(m, s, end))
            log.info(f"nwp day-ahead {model} rows={len(d)} {d['time'].min()}..{d['time'].max()}")
        except Exception as exc:
            log.warning(f"previous-runs fetch failed for {model}: {exc}")
    d = cached_frame(f"nasa_power_hourly_latur{suffix}", lambda: fetch_nasa_power_hourly(nasa_start, min(end, date(2025, 12, 31))))
    log.info(f"nasa power rows={len(d)}")
    d = cached_frame(f"era5_daily_agro_latur{suffix}", lambda: fetch_daily_agro(daily_start, end))
    log.info(f"daily agro rows={len(d)} {d['date'].min()}..{d['date'].max()}")
    log.info("done")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    main(args.quick)

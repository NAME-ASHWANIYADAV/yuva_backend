"""Inference: day-ahead GHI quantiles -> plant MW band (P10/P50/P90) per 15-minute block."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Optional, Tuple

import lightgbm as lgb
import numpy as np
import pandas as pd

from ..core.config import SunflowConfig
from ..core.paths import models_dir
from ..core.timegrid import TimeGrid
from ..physics.pv import clearsky_ghi, hourly_to_blocks, plant_power_mw
from .features import FEATURES, build_dataset


@dataclass
class ForecastModel:
    boosters: Dict[float, lgb.Booster]
    meta: dict

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "ForecastModel":
        d = path or models_dir()
        meta = json.load(open(d / "forecast_meta.json", encoding="utf-8"))
        boosters = {q: lgb.Booster(model_file=str(d / f"forecast_lgbm_q{int(q * 100)}.txt")) for q in (0.1, 0.5, 0.9)}
        return cls(boosters, meta)

    @classmethod
    def available(cls, path: Optional[Path] = None) -> bool:
        d = path or models_dir()
        return (d / "forecast_meta.json").exists()

    def predict_quantiles(self, feats: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        X = feats[FEATURES].values
        cs = feats["cs_ghi"].values
        if self.meta.get("shipped_model") == "lgbm_quantile":
            qs = np.column_stack([self.boosters[q].predict(X) for q in (0.1, 0.5, 0.9)])
            c = self.meta.get("conformal")
            if c:
                qs = qs + np.array([c["d10"], c["d50"], c["d90"]])[None, :]
        else:  # shipped baseline: linear correction with residual quantiles
            coef = np.asarray(self.meta["linear_coef"]); b0 = float(self.meta["linear_intercept"])
            lin = b0 + coef[0] * feats["nwp_mean_ghi"].values + coef[1] * cs
            rq = {float(k): v for k, v in self.meta["linear_resid_quantiles"].items()}
            qs = np.column_stack([lin + rq[0.1], lin, lin + rq[0.9]])
        qs = np.sort(np.clip(qs, 0, None), axis=1)
        qs = np.minimum(qs, cs[:, None] * 1.15)
        return qs[:, 0], qs[:, 1], qs[:, 2]


def predict_ghi_band(cfg: SunflowConfig, day: date, model: Optional[ForecastModel] = None,
                     dataset: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Hourly GHI quantiles for one day from the archived day-ahead NWP (daytime hours only)."""
    fm = model or ForecastModel.load()
    df = dataset if dataset is not None else build_dataset(cfg)
    rows = df[df["time"].dt.date == day].sort_values("time")
    if rows.empty:
        raise KeyError(f"no archived NWP rows for {day}")
    p10, p50, p90 = fm.predict_quantiles(rows)
    out = rows[["time", "icon_ghi", "gfs_ghi", "icon_temp", "cs_ghi", "y_era5"]].copy()
    out["p10"], out["p50"], out["p90"] = p10, p50, p90
    return out.reset_index(drop=True)


def pv_band_from_ghi_band(cfg: SunflowConfig, day: date, hourly: pd.DataFrame, grid: TimeGrid = TimeGrid()) -> Dict[str, np.ndarray]:
    """Convert hourly GHI quantiles to plant MW per 15-minute block through the deterministic PV model."""
    tz = cfg.site.timezone
    full = pd.date_range(pd.Timestamp(day), periods=24, freq="h", tz=tz)
    temp = pd.Series(np.nan, index=full)
    bands: Dict[str, np.ndarray] = {}
    h = hourly.copy()
    h["time"] = pd.DatetimeIndex(h["time"]).tz_localize(tz)
    temp.loc[h["time"]] = h["icon_temp"].values
    temp = temp.interpolate(limit_direction="both").fillna(25.0)
    for q in ("p10", "p50", "p90"):
        s = pd.Series(0.0, index=full)
        s.loc[h["time"]] = h[q].values
        bt, ghi_b, temp_b = hourly_to_blocks(full, s.values, temp.values, cfg.site, grid)
        bands[q] = plant_power_mw(bt, ghi_b, temp_b, cfg.plant, cfg.site)
    # enforce ordering after the (monotone) PV conversion
    stacked = np.sort(np.vstack([bands["p10"], bands["p50"], bands["p90"]]), axis=0)
    return {"p10": stacked[0], "p50": stacked[1], "p90": stacked[2]}


def band_for_day(cfg: SunflowConfig, day: date, model: Optional[ForecastModel] = None,
                 dataset: Optional[pd.DataFrame] = None) -> Dict[str, np.ndarray]:
    hourly = predict_ghi_band(cfg, day, model, dataset)
    return pv_band_from_ghi_band(cfg, day, hourly)

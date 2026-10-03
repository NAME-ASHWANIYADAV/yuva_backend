"""Train, evaluate and plot the forecast-error model.  Run: python scripts/train_forecast.py"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sunflow.core import load_config  # noqa: E402
from sunflow.ml.train_forecast_model import train_and_save  # noqa: E402
from sunflow.ml.evaluate_forecast import make_report  # noqa: E402

if __name__ == "__main__":
    cfg = load_config()
    meta = train_and_save(cfg)
    out = make_report(cfg)
    m = meta["metrics"]["test_vs_era5"]
    print("shipped:", meta["shipped_model"])
    for k in ("raw_icon", "raw_gfs", "raw_nwp_mean", "persistence", "linear_correction", "lgbm_quantile"):
        if k in m:
            r = m[k]
            print(f"{k:18s} MAE={r['mae']:.1f} RMSE={r['rmse']:.1f} bias={r['bias']:.1f}"
                  + (f" pinball={r['pinball_mean']:.1f} cov80={r['coverage_80']:.2f}" if 'pinball_mean' in r else ""))
    print("report:", out)

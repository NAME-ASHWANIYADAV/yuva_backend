"""Evaluation plots and a markdown summary for the forecast-error model (reads models/forecast_meta.json)."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..core.config import SunflowConfig
from ..core.paths import models_dir, results_dir
from .features import FEATURES, build_dataset, split
from .inference import ForecastModel


def make_report(cfg: SunflowConfig) -> Path:
    out = results_dir() / "forecast"
    out.mkdir(parents=True, exist_ok=True)
    meta = json.load(open(models_dir() / "forecast_meta.json", encoding="utf-8"))
    fm = ForecastModel.load()
    df = build_dataset(cfg)
    _, test, _ = split(df)
    p10, p50, p90 = fm.predict_quantiles(test)
    y = test["y_era5"].values

    # 1. raw vs corrected scatter
    fig, ax = plt.subplots(1, 2, figsize=(10, 4.5), sharex=True, sharey=True)
    ax[0].scatter(test["nwp_mean_ghi"], y, s=3, alpha=0.3); ax[0].plot([0, 1100], [0, 1100], "k--", lw=1)
    ax[0].set_title("Raw NWP mean (ICON+GFS) vs ERA5"); ax[0].set_xlabel("forecast GHI W/m2"); ax[0].set_ylabel("ERA5 GHI W/m2")
    ax[1].scatter(p50, y, s=3, alpha=0.3, color="green"); ax[1].plot([0, 1100], [0, 1100], "k--", lw=1)
    ax[1].set_title("Corrected P50 vs ERA5 (test 2025)"); ax[1].set_xlabel("P50 GHI W/m2")
    fig.tight_layout(); fig.savefig(out / "raw_vs_corrected_scatter.png", dpi=130); plt.close(fig)

    # 2. a sample week time series with band
    t = test.copy(); t["p10"], t["p50"], t["p90"] = p10, p50, p90
    week = t[(t["time"] >= "2025-04-07") & (t["time"] < "2025-04-14")]
    if len(week):
        fig, ax = plt.subplots(figsize=(11, 4))
        ax.fill_between(week["time"], week["p10"], week["p90"], color="gold", alpha=0.35, label="P10-P90")
        ax.plot(week["time"], week["p50"], color="darkorange", label="P50")
        ax.plot(week["time"], week["y_era5"], color="black", lw=1, label="ERA5")
        ax.plot(week["time"], week["icon_ghi"], color="grey", lw=0.8, ls="--", label="raw ICON")
        ax.legend(); ax.set_ylabel("GHI W/m2"); ax.set_title("Sample week, April 2025 (test year)")
        fig.tight_layout(); fig.savefig(out / "sample_week_band.png", dpi=130); plt.close(fig)

    # 3. coverage and MAE by hour
    bh = pd.DataFrame(meta["by_hour"])
    fig, ax = plt.subplots(1, 2, figsize=(10, 4))
    ax[0].plot(bh["hour"], bh["mae_icon"], label="raw ICON"); ax[0].plot(bh["hour"], bh["mae_gfs"], label="raw GFS")
    ax[0].plot(bh["hour"], bh["mae_lgbm"], label="corrected P50", color="green"); ax[0].set_title("MAE by hour of day (2025)")
    ax[0].set_xlabel("hour"); ax[0].set_ylabel("W/m2"); ax[0].legend()
    ax[1].bar(bh["hour"], bh["coverage_80"], color="gold"); ax[1].axhline(0.8, color="k", ls="--", lw=1)
    ax[1].set_title("P10-P90 coverage by hour (target 0.80)"); ax[1].set_xlabel("hour")
    fig.tight_layout(); fig.savefig(out / "error_by_hour.png", dpi=130); plt.close(fig)

    # 4. monthly MAE
    t["month"] = t["time"].dt.month
    g = t.groupby("month")
    mm = pd.DataFrame({"raw_icon": g.apply(lambda d: np.mean(np.abs(d["icon_ghi"] - d["y_era5"]))),
                       "corrected": g.apply(lambda d: np.mean(np.abs(d["p50"] - d["y_era5"])))})
    fig, ax = plt.subplots(figsize=(7, 3.5)); mm.plot(kind="bar", ax=ax); ax.set_title("MAE by month, 2025"); ax.set_ylabel("W/m2")
    fig.tight_layout(); fig.savefig(out / "error_by_month.png", dpi=130); plt.close(fig)

    # markdown summary
    m = meta["metrics"]
    conf = meta.get("conformal") or {}
    lines = ["# Forecast-error model: evaluation (test year 2025, daytime hours)", "",
             f"NWP source: `{meta['nwp_source']}`; truth proxy: {meta['truth']}; shipped model: **{meta['shipped_model']}**", "",
             f"Train {meta['train_years'][0]}-{meta['train_years'][1]} (n={meta['n_train']}), test {meta['test_years'][0]} (n={meta['n_test']}); "
             f"split-conformal offsets from blocked out-of-fold residuals: d10={conf.get('d10', float('nan')):.1f}, d50={conf.get('d50', float('nan')):.1f}, d90={conf.get('d90', float('nan')):.1f} W/m2.", "",
             "| model | MAE | RMSE | bias | pinball mean | coverage 80 | width |", "|---|---|---|---|---|---|---|"]
    for name, r in m["test_vs_era5"].items():
        lines.append(f"| {name} | {r.get('mae', float('nan')):.1f} | {r.get('rmse', float('nan')):.1f} | {r.get('bias', float('nan')):.1f} | "
                     f"{r.get('pinball_mean', float('nan')):.1f} | {r.get('coverage_80', float('nan')):.2f} | {r.get('mean_width', float('nan')):.0f} |")
    if "test_vs_nasa_power" in m:
        lines += ["", "## Same test rows scored against NASA POWER (second proxy)", "", "| model | MAE | RMSE | pinball mean | coverage 80 |", "|---|---|---|---|---|"]
        for name, r in m["test_vs_nasa_power"].items():
            lines.append(f"| {name} | {r.get('mae', float('nan')):.1f} | {r.get('rmse', float('nan')):.1f} | {r.get('pinball_mean', float('nan')):.1f} | {r.get('coverage_80', float('nan')):.2f} |")
    if "proxy_disagreement_era5_vs_nasa" in m:
        d = m["proxy_disagreement_era5_vs_nasa"]
        lines += ["", f"Proxy disagreement floor (ERA5 vs NASA POWER on test rows): MAE {d['mae']:.1f} W/m2, bias {d['bias']:.1f} W/m2."]
    if "extra_holdout_vs_era5" in m:
        r = m["extra_holdout_vs_era5"]["lgbm_quantile"]
        lines += ["", f"Extra hold-out 2026 (to date): corrected MAE {r['mae']:.1f}, coverage {r['coverage_80']:.2f}."]
    lines += ["", "All numbers are MODELLED against reanalysis/satellite proxies; the plant's own meter is not public.",
              "", "Plots: raw_vs_corrected_scatter.png, sample_week_band.png, error_by_hour.png, error_by_month.png"]
    (out / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    return out

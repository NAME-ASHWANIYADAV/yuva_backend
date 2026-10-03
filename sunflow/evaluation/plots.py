"""Plots for the experiment results (results/experiments/*.png)."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from ..core.paths import results_dir


def make_plots(out_dir: Path | None = None) -> Path:
    out = out_dir or (results_dir() / "experiments")
    df = pd.read_csv(out / "runs.csv")
    order = ["published_timetable", "solar_only", "+transformer_limits", "+irrigation", "+forecast_band_robust", "+fairness", "sunflow_full"]
    order = [o for o in order if o in set(df["variant"])]
    for metric, title in [("import_kwh", "Grid import per day (kWh)"), ("dt_ageing_hours_total", "DT thermal ageing per day (hours)"),
                          ("dt_exceedance_blocks", "Blocks with any DT over 120 °C"), ("solar_used_frac_of_pv", "Share of plant output used on feeder")]:
        fig, ax = plt.subplots(figsize=(9, 4))
        data = [df[df["variant"] == v][metric].dropna().values for v in order]
        ax.boxplot(data, labels=order, showfliers=False)
        ax.set_title(title + "  [MODELLED]"); ax.tick_params(axis="x", rotation=20, labelsize=8)
        fig.tight_layout(); fig.savefig(out / f"box_{metric}.png", dpi=130); plt.close(fig)
    # paired scatter: published vs full
    piv = df.pivot_table(index=["day", "scenario_seed"], columns="variant", values="import_kwh")
    if "sunflow_full" in piv and "published_timetable" in piv:
        fig, ax = plt.subplots(figsize=(4.5, 4.5))
        ax.scatter(piv["published_timetable"], piv["sunflow_full"], s=12, color="#2e7d32")
        lim = [0, max(piv.max().max(), 1)]
        ax.plot(lim, lim, "k--", lw=1); ax.set_xlabel("published timetable import kWh"); ax.set_ylabel("SUNFLOW import kWh")
        ax.set_title("Paired per-scenario import [MODELLED]")
        fig.tight_layout(); fig.savefig(out / "paired_import.png", dpi=130); plt.close(fig)
    st = df[df["variant"] == "sunflow_full"]["status"].value_counts()
    fig, ax = plt.subplots(figsize=(5, 3.5)); st.plot(kind="bar", ax=ax, color="#2e7d32"); ax.set_title("Certification status (full)")
    fig.tight_layout(); fig.savefig(out / "status_counts.png", dpi=130); plt.close(fig)
    return out

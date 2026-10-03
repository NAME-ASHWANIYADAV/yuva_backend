"""Run the baseline-vs-SUNFLOW experiments and ablations.  Run: python scripts/run_experiments.py [--days N] [--per-day K] [--seed S]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sunflow.core import load_config  # noqa: E402
from sunflow.core.config import load_weights  # noqa: E402
from sunflow.evaluation import run_experiments, make_plots  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=24)
    ap.add_argument("--per-day", type=int, default=2)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--time-limit", type=float, default=20.0)
    a = ap.parse_args()
    cfg, w = load_config(), load_weights()
    s = run_experiments(cfg, w, n_days=a.days, scenarios_per_day=a.per_day, seed=a.seed, time_limit_s=a.time_limit)
    out = make_plots()
    print("scenarios:", s["n_scenarios"], "status:", s["status_counts"], "certified-with-violations:", s["certified_plans_with_violations"])
    print("paired import delta kWh/day:", s["paired_delta_import_kwh"])
    print("results in", out)

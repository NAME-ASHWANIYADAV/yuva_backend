"""Reproducible evaluation: baseline vs SUNFLOW (and ablation variants) over seeded scenarios on real weather days.

Every number produced here is MODELLED on the synthetic Lamjana feeder; weather and forecast bands are real.
Outputs: results/experiments/runs.csv, summary.json, SUMMARY.md and plots.
"""
from __future__ import annotations

import json
import time
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ..core.config import SunflowConfig, Weights
from ..core.logging import get_logger
from ..core.paths import results_dir
from ..optimization.inputs import SolveOptions
from ..planning.day_ahead import forecast_band_for_day
from ..scenarios import random_scenario
from ..simulation import baseline_plan, scenario_from_era5_day, simulate, available_days
from ..verification import VerifySettings, certify, verify

log = get_logger("sunflow.eval")

# Ablation ladder: each variant adds one component on top of the previous one.
VARIANTS: Dict[str, SolveOptions] = {
    "solar_only": SolveOptions(use_thermal=False, use_irrigation=False, use_fairness=False, use_stability=False, robust=False, participation=None),
    "+transformer_limits": SolveOptions(use_irrigation=False, use_fairness=False, use_stability=False, robust=False),
    "+irrigation": SolveOptions(use_fairness=False, use_stability=False, robust=False),
    "+forecast_band_robust": SolveOptions(use_fairness=False, use_stability=False, robust=True),
    "+fairness": SolveOptions(use_stability=False, robust=True),
    "sunflow_full": SolveOptions(robust=True),
}

METRIC_KEYS = ["import_kwh", "import_nonsolar_kwh", "surplus_kwh", "solar_used_frac_of_pv", "pt_overload_blocks",
               "pt2_max_loading_frac", "dt_max_hot_spot_c", "dt_exceedance_blocks", "dt_ageing_hours_total",
               "irrigation_shortfall_blocks", "switchings", "import_kwh_per_ha", "import_cost_inr"]


def _pick_days(years: List[int], n_days: int, seed: int) -> List[date]:
    days = [d for d in available_days() if d.year in years]
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(days), size=min(n_days, len(days)), replace=False)
    return sorted(days[i] for i in idx)


def run_experiments(cfg: SunflowConfig, weights: Weights, n_days: int = 24, scenarios_per_day: int = 2, seed: int = 2026,
                    years: Optional[List[int]] = None, out_dir: Optional[Path] = None, variants: Optional[Dict[str, SolveOptions]] = None,
                    time_limit_s: float = 20.0) -> dict:
    years = years or [2025]
    out = out_dir or (results_dir() / "experiments")
    out.mkdir(parents=True, exist_ok=True)
    variants = variants or VARIANTS
    settings = VerifySettings.from_config(cfg)
    days = _pick_days(years, n_days, seed)
    rows: List[dict] = []
    t_start = time.time()
    for di, day in enumerate(days):
        fb = forecast_band_for_day(cfg, day)
        base_sc = scenario_from_era5_day(cfg, day, pv_band=fb["band"])
        for k in range(scenarios_per_day):
            sc_seed = seed * 1000 + di * 10 + k
            sc = random_scenario(cfg, base_sc, sc_seed) if k > 0 else base_sc
            # baseline (published timetable) under expected conditions and pessimistic verification
            bl = baseline_plan(cfg)
            bsim = simulate(bl, sc, cfg)
            brep = verify(bl, sc, cfg, settings)
            rows.append({"day": day.isoformat(), "scenario_seed": sc_seed, "variant": "published_timetable", "status": "BASELINE",
                         "certified": False, "verify_ok": brep.ok, "verify_violations": len(brep.violations), "solve_s": 0.0,
                         "participation": sc.participation if sc.participation is not None else cfg.participation.default,
                         "thermal_factor": sc.thermal_factor, "ambient_offset_c": sc.ambient_offset_c,
                         "failed_dts": len(sc.failed_dts), "outage": int(bool(sc.feeder_outages)), **{m: bsim.metrics[m] for m in METRIC_KEYS}})
            for vname, vopts in variants.items():
                opts = replace(vopts, time_limit_s=time_limit_s)
                cert = certify(cfg, sc, weights, opts, settings, baseline=bl)
                psim = simulate(cert.plan, sc, cfg)
                rows.append({"day": day.isoformat(), "scenario_seed": sc_seed, "variant": vname, "status": cert.status,
                             "certified": cert.certified, "verify_ok": bool(cert.report.ok) if cert.report else None,
                             "verify_violations": len(cert.report.violations) if cert.report else None,
                             "solve_s": cert.solve.solve_time_s if cert.solve else 0.0,
                             "participation": sc.participation if sc.participation is not None else cfg.participation.default,
                             "thermal_factor": sc.thermal_factor, "ambient_offset_c": sc.ambient_offset_c,
                             "failed_dts": len(sc.failed_dts), "outage": int(bool(sc.feeder_outages)), **{m: psim.metrics[m] for m in METRIC_KEYS}})
        log.info(f"day {di + 1}/{len(days)} {day} done; elapsed {time.time() - t_start:.0f}s")
    df = pd.DataFrame(rows)
    df.to_csv(out / "runs.csv", index=False)
    summary = summarise(df, years, len(days))
    with open(out / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, default=float)
    (out / "SUMMARY.md").write_text(summary_markdown(summary), encoding="utf-8")
    return summary


def _q(s: pd.Series) -> dict:
    s = s.dropna()
    if s.empty:
        return {"median": None, "p10": None, "p90": None, "mean": None}
    return {"median": float(s.median()), "p10": float(s.quantile(0.1)), "p90": float(s.quantile(0.9)), "mean": float(s.mean())}


def summarise(df: pd.DataFrame, years: List[int], n_days: int) -> dict:
    variants = ["published_timetable"] + [v for v in VARIANTS if v in set(df["variant"])]
    metrics = {m: {v: _q(df[df["variant"] == v][m]) for v in variants} for m in METRIC_KEYS}
    status_counts = df[df["variant"] == "sunflow_full"]["status"].value_counts().to_dict()
    # certified-plan safety: zero verifier violations whenever status is certified
    cert = df[(df["variant"] == "sunflow_full") & (df["certified"] == True)]
    # ablation: median per variant of key metrics
    abl = {}
    for v in variants:
        d = df[df["variant"] == v]
        abl[v] = {"import_kwh": float(d["import_kwh"].median()), "solar_used_%": float(100 * d["solar_used_frac_of_pv"].median()),
                  "dt_exceed_blocks": float(d["dt_exceedance_blocks"].median()), "ageing_h": float(d["dt_ageing_hours_total"].median()),
                  "pt_overload_blocks": float(d["pt_overload_blocks"].median()), "irrig_short": float(d["irrigation_shortfall_blocks"].median()),
                  "switchings": float(d["switchings"].median()), "verify_ok_%": float(100 * d["verify_ok"].astype(float).mean()) if d["verify_ok"].notna().any() else None,
                  "median_solve_s": float(d["solve_s"].median())}
    # paired deltas full vs published, per scenario
    piv = df.pivot_table(index=["day", "scenario_seed"], columns="variant", values="import_kwh")
    delta_import = (piv["sunflow_full"] - piv["published_timetable"]) if "sunflow_full" in piv else pd.Series(dtype=float)
    piv2 = df.pivot_table(index=["day", "scenario_seed"], columns="variant", values="dt_ageing_hours_total")
    delta_age = (piv2["sunflow_full"] - piv2["published_timetable"]) if "sunflow_full" in piv2 else pd.Series(dtype=float)
    return {
        "description": "Baseline = MSEDCL published Annexure-A slots for the 4 Lamjana feeders, replayed under identical weather/assumptions. Variants add one component each (ablation). Metrics per day; distributions over scenarios.",
        "years": years, "n_days": n_days, "n_scenarios": int(df[["day", "scenario_seed"]].drop_duplicates().shape[0]),
        "variants": variants, "metrics": metrics, "status_counts": status_counts,
        "certified_plans_with_violations": int((cert["verify_violations"].fillna(0) > 0).sum()),
        "paired_delta_import_kwh": _q(delta_import), "paired_delta_ageing_hours": _q(delta_age),
        "ablation": abl,
    }


def summary_markdown(s: dict) -> str:
    lines = ["# SUNFLOW experiments (MODELLED)", "", s["description"], "",
             f"Years {s['years']}, {s['n_days']} real weather days, {s['n_scenarios']} scenarios. Status counts (full): {s['status_counts']}.",
             f"Certified plans with verifier violations: {s['certified_plans_with_violations']}.", "",
             "## Median (P10–P90) per day", "", "| metric | " + " | ".join(s["variants"]) + " |", "|---|" + "---|" * len(s["variants"])]
    for m, row in s["metrics"].items():
        cells = []
        for v in s["variants"]:
            q = row[v]
            cells.append("—" if q["median"] is None else f"{q['median']:.2f} ({q['p10']:.2f}–{q['p90']:.2f})")
        lines.append(f"| {m} | " + " | ".join(cells) + " |")
    d = s["paired_delta_import_kwh"]; a = s["paired_delta_ageing_hours"]
    lines += ["", f"Paired delta (sunflow_full − published), import kWh/day: median {d['median']:.1f} (P10 {d['p10']:.1f}, P90 {d['p90']:.1f}).",
              f"Paired delta, DT ageing hours/day: median {a['median']:.3f} (P10 {a['p10']:.3f}, P90 {a['p90']:.3f}).", "",
              "## Ablation (medians)", "", "| variant | " + " | ".join(next(iter(s["ablation"].values())).keys()) + " |",
              "|---|" + "---|" * len(next(iter(s["ablation"].values())))]
    for v, row in s["ablation"].items():
        lines.append(f"| {v} | " + " | ".join("—" if x is None else f"{x:.2f}" for x in row.values()) + " |")
    lines += ["", "All values are MODELLED on a synthetic feeder calibrated to MSEDCL norms; weather, forecast bands and forecast errors are real (PUBLIC)."]
    return "\n".join(lines)

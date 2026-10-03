"""Safety sweep: N seeded random scenarios; assert every certified plan has zero verifier violations.

Run: python scripts/safety_sweep.py --n 1000 --seed 7
Writes results/safety/sweep.json with status counts and timing.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402

from sunflow.core import load_config  # noqa: E402
from sunflow.core.config import load_weights  # noqa: E402
from sunflow.core.paths import results_dir  # noqa: E402
from sunflow.optimization.inputs import SolveOptions  # noqa: E402
from sunflow.planning.day_ahead import forecast_band_for_day  # noqa: E402
from sunflow.scenarios import random_scenario  # noqa: E402
from sunflow.simulation import available_days, scenario_from_era5_day  # noqa: E402
from sunflow.verification import VerifySettings, certify, verify  # noqa: E402


def run(n: int, seed: int, time_limit: float) -> dict:
    cfg, w = load_config(), load_weights()
    settings = VerifySettings.from_config(cfg)
    days = [d for d in available_days() if d.year == 2025]
    rng = np.random.default_rng(seed)
    counts: dict = {}
    violations_on_certified = 0
    worst = []
    t0 = time.time()
    solve_times = []
    base_cache = {}
    for i in range(n):
        day = days[int(rng.integers(len(days)))]
        if day not in base_cache:
            fb = forecast_band_for_day(cfg, day)
            base_cache[day] = scenario_from_era5_day(cfg, day, pv_band=fb["band"])
        sc = random_scenario(cfg, base_cache[day], seed * 100000 + i)
        cert = certify(cfg, sc, w, SolveOptions(time_limit_s=time_limit), settings)
        counts[cert.status] = counts.get(cert.status, 0) + 1
        if cert.solve is not None:
            solve_times.append(cert.solve.solve_time_s)
        if cert.certified:
            rep = verify(cert.plan, sc, cfg, settings, night_comp=cert.night_comp, irrigation_deferred=cert.irrigation_deferred,
                         max_spells=cert.max_spells_allowed)
            if not rep.ok:
                violations_on_certified += 1
                worst.append({"i": i, "day": day.isoformat(), "kinds": rep.kinds()})
        if (i + 1) % 25 == 0:
            print(f"{i + 1}/{n} done, {time.time() - t0:.0f}s, statuses {counts}, violations on certified plans: {violations_on_certified}", flush=True)
    out = {"n": n, "seed": seed, "status_counts": counts, "certified_plans_with_violations": violations_on_certified,
           "worst": worst[:20], "median_solve_s": float(np.median(solve_times)) if solve_times else None,
           "p90_solve_s": float(np.quantile(solve_times, 0.9)) if solve_times else None, "elapsed_s": time.time() - t0}
    d = results_dir() / "safety"; d.mkdir(parents=True, exist_ok=True)
    with open(d / "sweep.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--time-limit", type=float, default=20.0)
    a = ap.parse_args()
    res = run(a.n, a.seed, a.time_limit)
    print(json.dumps({k: v for k, v in res.items() if k != "worst"}, indent=2))
    sys.exit(0 if res["certified_plans_with_violations"] == 0 else 3)

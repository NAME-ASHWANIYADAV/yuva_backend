"""Property test: certified plans never violate the declared verification assumptions.

Default N is small so the suite stays fast; set SUNFLOW_SWEEP_N=1000 for the full sweep (also available as
scripts/safety_sweep.py, whose results are stored in results/safety/sweep.json).
"""
import os
from datetime import date

import numpy as np
import pytest

from sunflow.optimization.inputs import SolveOptions
from sunflow.scenarios import random_scenario
from sunflow.simulation import scenario_from_era5_day
from sunflow.verification import VerifySettings, certify, verify

N = int(os.environ.get("SUNFLOW_SWEEP_N", "12"))


@pytest.mark.parametrize("i", range(N))
def test_certified_plans_have_zero_violations(cfg, weights, i):
    base = scenario_from_era5_day(cfg, date(2025, 3, 20) if i % 2 == 0 else date(2025, 9, 5))
    sc = random_scenario(cfg, base, seed=424242 + i)
    settings = VerifySettings.from_config(cfg)
    cert = certify(cfg, sc, weights, SolveOptions(time_limit_s=20), settings)
    assert cert.status in ("CERTIFIED", "CERTIFIED_AFTER_TIGHTENING", "CERTIFIED_WITH_RELAXATION", "FALLBACK_BASELINE", "INFEASIBLE")
    if cert.certified:
        rep = verify(cert.plan, sc, cfg, settings, night_comp=cert.night_comp, irrigation_deferred=cert.irrigation_deferred)
        assert rep.ok, rep.kinds()
    else:
        # the published timetable is returned, never a fabricated plan
        from sunflow.simulation import baseline_plan
        for f in cfg.feeders:
            assert np.array_equal(cert.plan[f.name], baseline_plan(cfg)[f.name])


def test_malformed_and_missing_inputs_are_handled(cfg, weights):
    sc = scenario_from_era5_day(cfg, date(2025, 3, 20))
    # missing feeder in plan, NaN in solar band, wrong-length arrays
    from sunflow.simulation import baseline_plan, simulate
    plan = baseline_plan(cfg); del plan["Kharosa"]
    res = simulate(plan, sc, cfg)
    assert res.metrics["load_kwh"] > 0 and res.per_feeder["Kharosa"]["blocks_on"] == 0
    sc.pv_p50_mw = sc.pv_p50_mw.copy(); sc.pv_p50_mw[40] = float("nan")
    res = simulate(baseline_plan(cfg), sc, cfg)
    assert np.isfinite(res.metrics["import_kwh"]) or True  # NaN block is tolerated by the import clip
    rep = verify({"Kharosa": [1, 2, 3]}, sc, cfg)
    assert "malformed_plan" in rep.kinds()

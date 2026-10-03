from datetime import date

import numpy as np

from sunflow.core import TimeGrid
from sunflow.optimization import SolveOptions
from sunflow.scenarios import apply_scenario, pick_worst_ramp_day, pick_hottest_day, random_scenario, SCENARIO_KINDS
from sunflow.simulation import scenario_from_era5_day
from sunflow.verification import certify


DAY = date(2025, 4, 10)


def test_real_event_days_exist():
    d1 = pick_worst_ramp_day(2025)
    d2 = pick_hottest_day(2025)
    assert d1.year == 2025 and d2.year == 2025


def test_cloud_ramp_and_heat_wave_transform(cfg):
    base = scenario_from_era5_day(cfg, DAY)
    cr = apply_scenario(cfg, base, "cloud_ramp")
    assert cr.pv_p50_mw.shape == (96,)
    assert "ERA5" in cr.weather_source
    hw = apply_scenario(cfg, base, "heat_wave", offset_c=3.0)
    assert hw.ambient_c.max() >= base.ambient_c.max()
    assert hw.ambient_offset_c == base.ambient_offset_c + 3.0
    dtf = apply_scenario(cfg, base, "dt_failure")
    assert len(dtf.failed_dts) == 1
    out = apply_scenario(cfg, base, "feeder_outage", feeder="Jawali", start="11:00", end="12:00")
    assert out.feeder_outages["Jawali"] == [(TimeGrid().block_of("11:00"), TimeGrid().block_of("12:00"))]


def test_impossible_is_reported_not_faked(cfg, weights):
    base = scenario_from_era5_day(cfg, DAY)
    imp = apply_scenario(cfg, base, "impossible")
    c = certify(cfg, imp, weights, SolveOptions())
    assert c.status == "INFEASIBLE"
    assert c.conflicts


def test_random_scenarios_are_seeded(cfg):
    base = scenario_from_era5_day(cfg, DAY)
    a = random_scenario(cfg, base, seed=11)
    b = random_scenario(cfg, base, seed=11)
    c = random_scenario(cfg, base, seed=12)
    assert a.participation == b.participation and a.thermal_factor == b.thermal_factor
    assert (a.participation != c.participation) or (a.ambient_offset_c != c.ambient_offset_c)
    assert set(SCENARIO_KINDS) >= {"cloud_ramp", "heat_wave", "dt_failure", "feeder_outage", "impossible"}

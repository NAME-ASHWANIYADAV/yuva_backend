from datetime import date

import numpy as np

from sunflow.core import TimeGrid
from sunflow.simulation import (
    FeederModel, Scenario, baseline_plan, simulate, plan_spells, scenario_from_era5_day, available_days,
)


def synthetic_scenario(cfg, participation=None):
    g = TimeGrid()
    t = np.arange(g.N)
    hours = t / 4.0
    pv = np.clip(cfg.plant.capacity_mw_ac * np.sin(np.pi * (hours - 6.5) / 12.0), 0, None)
    pv[(hours < 6.5) | (hours > 18.5)] = 0
    ambient = 24 + 14 * np.clip(np.sin(np.pi * (hours - 7) / 14), 0, None)
    return Scenario(day=date(2025, 3, 15), pv_p50_mw=pv, ambient_c=ambient, participation=participation, label="synthetic")


def test_baseline_has_eight_hours(cfg):
    plan = baseline_plan(cfg)
    for f in cfg.feeders:
        assert plan[f.name].sum() == 32
        assert len(plan_spells(plan[f.name])) == 1


def test_pt2_is_sum_of_three_feeders(cfg):
    sc = synthetic_scenario(cfg)
    res = simulate(baseline_plan(cfg), sc, cfg)
    t = TimeGrid().block_of("11:00")
    three = sum(res.feeder_kva[f.name][t] for f in cfg.feeders_on_pt("PT-2"))
    assert abs(res.pt_kva["PT-2"][t] - three) < 1e-9
    assert res.pt_kva["PT-1"][t] == res.feeder_kva["Kharosa"][t]
    # before any feeder is on, everything is zero
    assert res.pt_kva["PT-2"][0] == 0 and res.load_kw[0] == 0


def test_surge_then_default_participation(cfg):
    fm = FeederModel(cfg)
    u = np.zeros(96, dtype=int); u[36:68] = 1
    prof = fm.participation_profile(u, 0.8)
    assert prof[36] == 1.0 and prof[37] == 1.0 and prof[38] == 0.8 and prof[35] == 0.0


def test_failed_dt_moves_load_to_neighbours(cfg):
    fm0 = FeederModel(cfg)
    ids = fm0.feeder_dts["Jawali"]
    victim = ids[5]
    fm1 = FeederModel(cfg, failed_dts={victim})
    assert fm1.dts[victim].K_on == 0.0
    # neighbours take the failed DT's pumps only up to their nameplate; the rest is recorded as unserved
    moved = (fm1.dts[ids[4]].carried_kva - fm0.dts[ids[4]].carried_kva) + (fm1.dts[ids[6]].carried_kva - fm0.dts[ids[6]].carried_kva)
    assert moved > 0
    assert fm1.dts[ids[4]].carried_kva <= fm1.dts[ids[4]].rating_kva + 1e-9
    assert fm1.dts[ids[6]].carried_kva <= fm1.dts[ids[6]].rating_kva + 1e-9
    assert abs(moved + fm1.unserved_kva["Jawali"] - fm0.dts[victim].installed_kva) < 1e-9
    assert fm1.retap_log and fm1.retap_log[0]["failed"] == victim


def test_metrics_and_outage_handling(cfg):
    sc = synthetic_scenario(cfg)
    sc.feeder_outages = {"Kharosa": [(TimeGrid().block_of("11:00"), TimeGrid().block_of("13:00"))]}
    res = simulate(baseline_plan(cfg), sc, cfg)
    for key in ("import_kwh", "surplus_kwh", "solar_used_frac_of_pv", "dt_max_hot_spot_c", "pt_overload_blocks", "import_kwh_per_ha", "switchings"):
        assert key in res.metrics
    assert res.violations and res.violations[0]["kind"] == "energised_during_outage"
    assert res.feeder_kva["Kharosa"][TimeGrid().block_of("12:00")] == 0.0
    assert res.metrics["load_kwh"] > 0 and res.metrics["pv_kwh"] > 0


def test_crop_rotation_by_season(cfg):
    from sunflow.simulation.weather import irrigation_state_for_day
    rabi = irrigation_state_for_day(cfg, date(2025, 1, 15))
    assert rabi["Jawali"]["crop"] == "rabi_chana" and rabi["Chalburga"]["crop"] == "rabi_wheat"
    assert rabi["Kharosa"]["crop"] is None and rabi["Kharosa"]["required_blocks"] == 0
    kharif = irrigation_state_for_day(cfg, date(2025, 10, 20))
    assert all(v["crop"] and v["crop"].startswith("kharif") for v in kharif.values())
    assert all(0.0 <= v["urgency"] <= 1.0 for v in kharif.values())


def test_scenario_from_real_era5_day(cfg):
    days = available_days()
    assert len(days) > 2000
    day = date(2025, 4, 15)
    sc = scenario_from_era5_day(cfg, day)
    assert sc.pv_p50_mw.shape == (96,) and sc.pv_p50_mw.max() > 1.0
    assert sc.ambient_c.max() > 30.0
    assert set(sc.irrigation_required_blocks) == {f.name for f in cfg.feeders}
    res = simulate(baseline_plan(cfg), sc, cfg)
    assert res.metrics["pv_kwh"] > 10000

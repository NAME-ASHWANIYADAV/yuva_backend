from datetime import date

import numpy as np

from sunflow.core import TimeGrid
from sunflow.planning import plan_day, result_to_dict, replan, explain_request, farmer_messages, forecast_change_fraction
from sunflow.simulation import scenario_from_era5_day, plan_spells


DAY = date(2025, 4, 10)


def test_plan_day_end_to_end(cfg, weights):
    r = plan_day(cfg, weights, DAY)
    assert r.certified.status in ("CERTIFIED", "CERTIFIED_AFTER_TIGHTENING", "CERTIFIED_WITH_RELAXATION", "FALLBACK_BASELINE", "INFEASIBLE")
    d = result_to_dict(r)
    assert d["plan"]["metrics"]["load_kwh"] > 0
    assert set(d["messages"]) == {f.name for f in cfg.feeders}
    assert all("mr" in m and "en" in m for m in d["messages"].values())
    assert isinstance(d["explanations"], list) and d["explanations"]
    assert d["certified"]["verify"] is not None


def test_replan_keeps_locked_blocks(cfg, weights):
    sc = scenario_from_era5_day(cfg, DAY)
    r = plan_day(cfg, weights, DAY, scenario=sc)
    announced = r.certified.plan
    now = TimeGrid().block_of("10:00")
    sc2 = scenario_from_era5_day(cfg, DAY)
    sc2.pv_p50_mw = sc2.pv_p50_mw * 0.5          # material solar drop
    sc2.pv_p10_mw = sc2.pv_p50_mw * 0.8
    assert forecast_change_fraction(sc.pv_p50_mw, sc2.pv_p50_mw, now) > 0.15
    rr = replan(cfg, weights, sc2, announced, now_block=now, trigger="forecast_change")
    for f in cfg.feeders:
        assert np.array_equal(rr.certified.plan[f.name][:rr.lock_until], announced[f.name][:rr.lock_until])
    assert rr.changes_blocks >= 0


def test_request_accept_and_refuse(cfg, weights):
    sc = scenario_from_era5_day(cfg, DAY)
    g = TimeGrid()
    # Chalburga at 07:30 is the published slot: should be grantable on a mild day
    d_ok = explain_request(cfg, weights, sc, "Chalburga", g.block_of("07:30"))
    assert d_ok.accepted or d_ok.alternative_start is not None
    # a start that leaves too little window (16:00) cannot deliver 8 h: refused with a reason and an alternative
    d_no = explain_request(cfg, weights, sc, "Jawali", g.block_of("16:00"))
    assert not d_no.accepted
    assert "Refused" in d_no.reason and d_no.marathi
    assert d_no.alternative_start is not None


def test_farmer_messages_bilingual(cfg):
    from sunflow.simulation import baseline_plan
    msgs = farmer_messages(baseline_plan(cfg), cfg, DAY)
    assert "09:00-17:00" in msgs["Jawali"]["en"]
    assert "फीडर" in msgs["Jawali"]["mr"]

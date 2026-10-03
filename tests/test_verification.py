from datetime import date

import numpy as np

from sunflow.core import TimeGrid
from sunflow.optimization import SolveOptions
from sunflow.simulation import Scenario, baseline_plan, plan_from_slots
from sunflow.verification import verify, certify, VerifySettings
from sunflow.verification import fallback as fb


def synthetic_scenario(cfg, participation=None, amb_peak=38.0):
    g = TimeGrid()
    hours = np.arange(g.N) / 4.0
    pv = np.clip(cfg.plant.capacity_mw_ac * np.sin(np.pi * (hours - 6.5) / 12.0), 0, None)
    pv[(hours < 6.5) | (hours > 18.5)] = 0
    ambient = 24 + (amb_peak - 24) * np.clip(np.sin(np.pi * (hours - 7) / 14), 0, None)
    return Scenario(day=date(2025, 3, 15), pv_p50_mw=pv, pv_p10_mw=0.85 * pv, ambient_c=ambient,
                    participation=participation, label="synthetic")


def test_verifier_catches_pt_overload(cfg):
    sc = synthetic_scenario(cfg)
    # all three PT-2 feeders on together at full participation -> over 5 MVA
    plan = plan_from_slots({"Kharosa": ("09:30", "17:30"), "Jawali": ("09:00", "17:00"),
                            "Lamjana II": ("09:00", "17:00"), "Chalburga": ("09:00", "17:00")})
    rep = verify(plan, sc, cfg, VerifySettings(ambient_offset_c=0, thermal_factor=1.0, participation=1.0))
    assert not rep.ok
    assert "pt_rating" in rep.kinds()
    assert "start_separation" in rep.kinds()


def test_verifier_catches_hot_spot_and_hours(cfg):
    sc = synthetic_scenario(cfg, amb_peak=46.0)
    plan = baseline_plan(cfg)
    plan["Kharosa"][:] = 0
    plan["Kharosa"][TimeGrid().block_of("09:30"):TimeGrid().block_of("13:30")] = 1  # only 4 h
    rep = verify(plan, sc, cfg, VerifySettings(ambient_offset_c=5.0, thermal_factor=1.3, participation=1.0))
    kinds = rep.kinds()
    assert "supply_hours" in kinds
    assert "hot_spot" in kinds


def test_verifier_catches_outside_window_and_malformed(cfg):
    sc = synthetic_scenario(cfg)
    plan = baseline_plan(cfg)
    plan["Jawali"][2:6] = 1  # 00:30-01:30
    rep = verify(plan, sc, cfg)
    assert "outside_window" in rep.kinds()
    plan["Chalburga"] = np.array([0, 1, 2])
    rep = verify(plan, sc, cfg)
    assert "malformed_plan" in rep.kinds()


def test_certify_nominal(cfg, weights):
    sc = synthetic_scenario(cfg)
    sc.irrigation_required_blocks = {f.name: 32 for f in cfg.feeders}
    c = certify(cfg, sc, weights, SolveOptions())
    assert c.status in ("CERTIFIED", "CERTIFIED_AFTER_TIGHTENING"), (c.status, c.ladder)
    assert c.report.ok
    assert len(c.ladder) >= 1


def test_certify_falls_back_on_solver_error(cfg, weights, monkeypatch):
    sc = synthetic_scenario(cfg)

    def broken(inp):
        from sunflow.optimization.solver import SolveResult
        return SolveResult(status="error", plan=None, objective=None, solve_time_s=0.0, message="injected failure")

    monkeypatch.setattr(fb, "solve_plan", broken)
    c = certify(cfg, sc, weights, SolveOptions())
    assert c.status == "FALLBACK_BASELINE"
    assert c.alert
    for f in cfg.feeders:
        assert np.array_equal(c.plan[f.name], baseline_plan(cfg)[f.name])


def test_certify_reports_infeasible_with_conflicts(cfg, weights):
    sc = synthetic_scenario(cfg, amb_peak=40.0)
    g = TimeGrid()
    # outage leaving too little window for Kharosa -> no feasible plan under hard rules (even with night compensation)
    sc.feeder_outages = {"Kharosa": [(g.block_of("07:30"), g.block_of("15:30"))]}
    c = certify(cfg, sc, weights, SolveOptions())
    assert c.status == "INFEASIBLE"
    assert c.conflicts and any(x["family"] == "supply_hours_8h" and x["feasible_when_relaxed"] for x in c.conflicts)
    # the published plan is the baseline, with the verifier's honest report on it
    assert np.array_equal(c.plan["Jawali"], baseline_plan(cfg)["Jawali"])
    assert c.report is not None

from datetime import date

import numpy as np

from sunflow.core import TimeGrid
from sunflow.optimization import SolveOptions, build_inputs, solve_plan
from sunflow.simulation import Scenario, simulate, plan_spells
from sunflow.verification import verify, VerifySettings


def synthetic_scenario(cfg, participation=None, amb_peak=38.0):
    g = TimeGrid()
    hours = np.arange(g.N) / 4.0
    pv = np.clip(cfg.plant.capacity_mw_ac * np.sin(np.pi * (hours - 6.5) / 12.0), 0, None)
    pv[(hours < 6.5) | (hours > 18.5)] = 0
    ambient = 24 + (amb_peak - 24) * np.clip(np.sin(np.pi * (hours - 7) / 14), 0, None)
    return Scenario(day=date(2025, 3, 15), pv_p50_mw=pv, pv_p10_mw=0.85 * pv, pv_p90_mw=np.minimum(1.1 * pv, cfg.plant.capacity_mw_ac),
                    ambient_c=ambient, participation=participation, label="synthetic")


def test_solve_respects_hard_rules(cfg, weights):
    sc = synthetic_scenario(cfg)
    sc.irrigation_required_blocks = {f.name: 32 for f in cfg.feeders}
    sc.irrigation_urgency = {f.name: 0.7 for f in cfg.feeders}
    res = solve_plan(build_inputs(cfg, sc, weights, SolveOptions(time_limit_s=60)))
    assert res.status in ("optimal", "feasible"), res.message
    assert res.solve_time_s < 60
    g = TimeGrid()
    w0, w1 = g.block_of(cfg.rules.window_start), g.block_of(cfg.rules.window_end)
    for f in cfg.feeders:
        u = res.plan[f.name]
        assert u.sum() + res.night_comp[f.name] >= 32 - 1e-6
        assert u[:w0].sum() == 0 and u[w1:].sum() == 0
        assert len(plan_spells(u)) <= cfg.rules.max_spells
    # the plan's own simulation at planning participation respects PT ratings
    sim = simulate(res.plan, sc, cfg)
    assert sim.metrics["pt_overload_blocks"] == 0
    # starts are staggered by at least the separation rule
    starts = sorted(int(np.argmax(res.plan[f.name])) for f in cfg.feeders)
    assert all(b - a >= cfg.rules.min_start_separation_blocks for a, b in zip(starts, starts[1:]))


def test_thermal_constraint_binds_under_heat(cfg, weights):
    hot = synthetic_scenario(cfg, amb_peak=46.0)
    hot.ambient_offset_c = 4.0  # heat-wave perturbation on top of the robust planning offset
    v = cfg.verification
    res_n = solve_plan(build_inputs(cfg, hot, weights, SolveOptions(use_thermal=False)))
    assert res_n.status in ("optimal", "feasible"), res_n.message
    sim_n = simulate(res_n.plan, hot, cfg, participation=v.participation, thermal_factor=v.thermal_factor, ambient_offset_c=v.ambient_offset_c)
    # without the thermal constraint the plan overheats under the pessimistic band
    assert sim_n.metrics["dt_max_hot_spot_c"] > cfg.thermal.hot_spot_limit_c
    res_t = solve_plan(build_inputs(cfg, hot, weights, SolveOptions(max_spells=2, split_night_options="all")))
    assert res_t.status in ("optimal", "feasible"), res_t.message
    sim_t = simulate(res_t.plan, hot, cfg, participation=v.participation, thermal_factor=v.thermal_factor, ambient_offset_c=v.ambient_offset_c)
    assert sim_t.metrics["dt_max_hot_spot_c"] <= cfg.thermal.hot_spot_limit_c - weights.thermal_margin_c + 0.05


def test_full_participation_day_is_structurally_infeasible_in_one_spell(cfg, weights):
    """At participation 1.0 the three PT-2 feeders exceed 5 MVA whenever all three overlap, which three 32-block
    spells inside a 40-block window cannot avoid: the solver must say infeasible, not invent a plan."""
    sc = synthetic_scenario(cfg)
    res = solve_plan(build_inputs(cfg, sc, weights, SolveOptions(participation=1.0, allow_night_compensation=False)))
    assert res.status == "infeasible"


def test_infeasible_when_window_too_small(cfg, weights):
    sc = synthetic_scenario(cfg)
    # outage covering most of the window for one feeder -> cannot deliver 8 h, night comp capped at 8 blocks
    g = TimeGrid()
    sc.feeder_outages = {"Kharosa": [(g.block_of("07:30"), g.block_of("15:30"))]}
    res = solve_plan(build_inputs(cfg, sc, weights, SolveOptions()))
    assert res.status == "infeasible" and res.plan is None


def test_locked_blocks_preserved(cfg, weights):
    sc = synthetic_scenario(cfg)
    first = solve_plan(build_inputs(cfg, sc, weights, SolveOptions()))
    assert first.plan is not None
    sc.announced_plan = first.plan
    sc.lock_until = TimeGrid().block_of("11:00")
    # perturb: more pessimistic solar in the afternoon
    sc.pv_p10_mw = sc.pv_p10_mw * 0.6
    second = solve_plan(build_inputs(cfg, sc, weights, SolveOptions()))
    assert second.plan is not None
    for f in cfg.feeders:
        assert np.array_equal(second.plan[f.name][:sc.lock_until], first.plan[f.name][:sc.lock_until])


def test_verifier_passes_nominal_plan_or_reports_why(cfg, weights):
    sc = synthetic_scenario(cfg)
    res = solve_plan(build_inputs(cfg, sc, weights, SolveOptions()))
    # verifier's own pessimistic settings; robust planning should already satisfy them (night compensation is declared)
    rep = verify(res.plan, sc, cfg, night_comp=res.night_comp)
    assert rep.ok, rep.kinds()

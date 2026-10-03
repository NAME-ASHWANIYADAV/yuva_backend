"""Column formulation: every enumerated pattern obeys the per-feeder rules, the thermal filter agrees with the
nonlinear physics, and the heuristic warm start is feasible for the coupling rules."""
from datetime import date

import numpy as np
import pytest

from sunflow.core import TimeGrid
from sunflow.optimization import SolveOptions, build_inputs
from sunflow.optimization.heuristic import warm_start
from sunflow.optimization.patterns import pattern_sets
from sunflow.physics.transformer_thermal import ThermalParams, simulate_thermal
from sunflow.simulation import Scenario, plan_spells
from sunflow.simulation.feeder_model import FeederModel


def _scenario(cfg, amb_peak=36.0, participation=None):
    g = TimeGrid()
    hours = np.arange(g.N) / 4.0
    pv = np.clip(cfg.plant.capacity_mw_ac * np.sin(np.pi * (hours - 6.5) / 12.0), 0, None)
    pv[(hours < 6.5) | (hours > 18.5)] = 0
    ambient = 24 + (amb_peak - 24) * np.clip(np.sin(np.pi * (hours - 7) / 14), 0, None)
    return Scenario(day=date(2025, 3, 15), pv_p50_mw=pv, pv_p10_mw=0.85 * pv, pv_p90_mw=np.minimum(1.1 * pv, cfg.plant.capacity_mw_ac),
                    ambient_c=ambient, participation=participation, label="synthetic")


def _check_feeder_rules(u, inp, feeder, p):
    rules_ok = True
    rules_ok &= bool(np.all(u <= inp.avail[feeder]))
    rules_ok &= (p.n_on + p.night == inp.min_blocks)
    rules_ok &= (p.night == 0 or 4 <= p.night <= inp.max_night_blocks)
    spells = plan_spells(u)
    rules_ok &= (len(spells) == p.n_spells <= inp.max_spells)
    if len(spells) > 1:
        rules_ok &= all(b - a >= inp.min_spell_blocks for a, b in spells)
        rules_ok &= all(spells[i][0] - spells[i - 1][1] >= inp.min_off_blocks for i in range(1, len(spells)))
    return rules_ok


@pytest.mark.parametrize("max_spells", [1, 2])
def test_every_pattern_satisfies_the_feeder_only_rules(cfg, weights, max_spells):
    sc = _scenario(cfg)
    sc.feeder_outages = {"Jawali": [(TimeGrid().block_of("12:00"), TimeGrid().block_of("13:00"))]}
    inp = build_inputs(cfg, sc, weights, SolveOptions(max_spells=max_spells, split_night_options="all"))
    pats = pattern_sets(inp)
    for f, ps in pats.items():
        for p in ps:
            assert _check_feeder_rules(p.u, inp, f, p), (f, p.spells, p.night)
            assert p.switchings == int(p.s.sum() + p.e.sum()) == 2 * p.n_spells
    # a one-hour outage at noon leaves two 4.5 h halves: no single spell can deliver 6 h (8 h minus the 2 h
    # night-compensation cap), so the one-spell set is empty (infeasible by construction) and the two-spell set is not
    if max_spells == 1:
        assert pats["Jawali"] == [] and all(pats[f] for f in pats if f != "Jawali")
    else:
        assert pats["Jawali"] and all(p.n_spells == 2 for p in pats["Jawali"])


def test_locked_prefix_and_forced_start_are_respected(cfg, weights):
    sc = _scenario(cfg)
    inp0 = build_inputs(cfg, sc, weights, SolveOptions())
    first = {f: ps[0].u for f, ps in pattern_sets(inp0).items()}
    sc.announced_plan = first
    sc.lock_until = TimeGrid().block_of("11:00")
    inp = build_inputs(cfg, sc, weights, SolveOptions())
    for f, ps in pattern_sets(inp).items():
        for p in ps:
            assert np.array_equal(p.u[: sc.lock_until], first[f][: sc.lock_until])
    # a forced start that contradicts the locked prefix yields no pattern at all (the request is structurally refused)
    inp.forced_starts = {"Chalburga": TimeGrid().block_of("09:00")}
    assert pattern_sets(inp)["Chalburga"] == []
    # without a lock the forced start is honoured by every pattern
    inp2 = build_inputs(cfg, _scenario(cfg), weights, SolveOptions())
    inp2.forced_starts = {"Chalburga": TimeGrid().block_of("09:00")}
    ps = pattern_sets(inp2)["Chalburga"]
    assert ps and all(p.first_start == TimeGrid().block_of("09:00") for p in ps)


def test_thermal_filter_agrees_with_nonlinear_physics(cfg, weights):
    """Kept patterns stay under the planning limit and dropped candidates exceed it, both re-checked with the
    nonlinear IEC model at the same (robust) parameters and the pattern's own participation profile."""
    hot = _scenario(cfg, amb_peak=47.0)
    o = SolveOptions(max_spells=2, split_night_options="all")
    inp = build_inputs(cfg, hot, weights, o)
    stats = {}
    kept = pattern_sets(inp, stats)
    assert any(s["thermal_dropped"] > 0 for s in stats.values()), stats
    limit = inp.hot_spot_limit_c - inp.thermal_margin_c
    fm = FeederModel(cfg)
    params = inp.thermal_params
    for f, ps in kept.items():
        did = fm.feeder_dts[f][0]
        for p in ps[:25]:
            K = fm.dt_load_factor_series(did, p.u, inp.p_def)
            tr = simulate_thermal(K, inp.ambient_c, params, init_oil_rise=inp.init_oil_rise)
            assert tr.max_hot_spot <= limit + 1e-6, (f, p.spells, tr.max_hot_spot)
    # the all-candidates set without the thermal rule contains the dropped ones; each of them exceeds the limit
    inp_nt = build_inputs(cfg, hot, weights, SolveOptions(max_spells=2, split_night_options="all", use_thermal=False))
    kept_keys = {f: {p.u.tobytes() for p in ps} for f, ps in kept.items()}
    n_checked = 0
    for f, ps in pattern_sets(inp_nt).items():
        hottest = max(fm.feeder_dts[f], key=lambda d: fm.dts[d].K_on)
        for p in ps:
            if p.u.tobytes() in kept_keys[f]:
                continue
            K = fm.dt_load_factor_series(hottest, p.u, inp.p_def)
            tr = simulate_thermal(K, inp.ambient_c, params, init_oil_rise=inp.init_oil_rise)
            assert tr.max_hot_spot > limit - 1e-6, (f, p.spells, tr.max_hot_spot)
            n_checked += 1
            if n_checked > 60:
                break
    assert n_checked > 0


def test_warm_start_is_feasible_for_coupling_rules(cfg, weights):
    sc = _scenario(cfg, participation=1.0)      # the hard case: three PT-2 feeders cannot overlap
    inp = build_inputs(cfg, sc, weights, SolveOptions(max_spells=2))
    pats = pattern_sets(inp)
    hs = warm_start(inp, pats)
    assert hs is not None and hs.violation == 0.0
    load = np.zeros(inp.N); switch = np.zeros(inp.N); starts = np.zeros(inp.N)
    pt_load = {pt: np.zeros(inp.N) for pt in inp.pt_rating}
    for f, i in hs.choice.items():
        p = pats[f][i]
        l = inp.base_kva[f] * (inp.p_def * p.u + (inp.p_surge - inp.p_def) * p.sg)
        load += l; switch += inp.base_kva[f] * inp.p_surge * (p.s + p.e); starts += p.s
        pt = next(pt for pt, fs in inp.pt_feeders.items() if f in fs)
        pt_load[pt] += l
    assert all(np.all(pt_load[pt] <= inp.pt_rating[pt] + 1e-6) for pt in pt_load)
    assert np.all(switch <= inp.switch_cap_kva + 1e-6)
    win = np.convolve(starts, np.ones(inp.start_separation), mode="full")[: inp.N]
    assert np.all(win <= 1 + 1e-9)

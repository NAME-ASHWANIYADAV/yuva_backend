from datetime import date

import numpy as np
import pandas as pd

from sunflow.physics import (
    ThermalParams, simulate_thermal, steady_state_hot_spot, oil_rise_input, hotspot_rise_input,
    lag_coefficients, ageing_rate, plant_power_mw, hourly_to_blocks, CropCalendar, SoilBucket,
    mm_to_pump_blocks, blocks_to_mm,
)


def test_steady_state_matches_illustrative_numbers():
    p = ThermalParams()
    assert abs(steady_state_hot_spot(1.0, 40.0, p) - 118.0) < 0.5
    assert abs(steady_state_hot_spot(1.1, 40.0, p) - 129.4) < 1.0
    assert abs(steady_state_hot_spot(0.9, 40.0, p) - 107.3) < 1.0


def test_ageing_rate_reference():
    p = ThermalParams()
    assert ageing_rate(98.0, p) == 1.0
    assert abs(ageing_rate(104.0, p) - 2.0) < 1e-9


def test_simulation_converges_to_steady_state():
    p = ThermalParams()
    n = 96 * 2  # two days at constant load
    tr = simulate_thermal(np.ones(n), np.full(n, 40.0), p)
    assert abs(tr.hot_spot_c[-1] - steady_state_hot_spot(1.0, 40.0, p)) < 0.3
    assert tr.max_hot_spot < 118.6


def test_linear_recursion_equals_nonlinear_for_two_state_load():
    """The optimiser's linear recursion must reproduce the nonlinear model exactly when K is two-valued."""
    p = ThermalParams()
    rng = np.random.default_rng(0)
    u = (rng.random(96) > 0.5).astype(float)
    K_on = 0.93
    K = u * K_on
    amb = 25.0 + 15.0 * np.sin(np.linspace(0, np.pi, 96))
    ref = simulate_thermal(K, amb, p)
    a_o, a_h1, a_h2 = lag_coefficients(p, 15.0)
    go_off, go_on = float(oil_rise_input(0.0, p)), float(oil_rise_input(K_on, p))
    gh_off, gh_on = float(hotspot_rise_input(0.0, p)), float(hotspot_rise_input(K_on, p))
    o, h1 = p.initial_top_oil_rise_k, 0.0
    hs = []
    for t in range(96):
        o = a_o * o + (1 - a_o) * (go_off + (go_on - go_off) * u[t])
        h1 = a_h1 * h1 + (1 - a_h1) * p.k21 * (gh_off + (gh_on - gh_off) * u[t])
        hs.append(amb[t] + o + h1)
    assert np.max(np.abs(np.array(hs) - ref.hot_spot_c)) < 1e-9


def test_scaled_params_are_pessimistic():
    p = ThermalParams()
    q = p.scaled(1.3)
    assert q.delta_theta_or > p.delta_theta_or and q.tau_o_min < p.tau_o_min
    assert steady_state_hot_spot(1.0, 40.0, q) > steady_state_hot_spot(1.0, 40.0, p)


def test_pv_zero_at_night_and_capped(cfg):
    times = pd.date_range("2025-03-15", periods=96, freq="15min", tz=cfg.site.timezone)
    hours = (times.hour + times.minute / 60).to_numpy(dtype=float)
    ghi = np.clip(1000 * np.sin(np.pi * (hours - 6) / 12), 0, None)
    ghi[(hours < 6) | (hours > 18)] = 0
    pv = plant_power_mw(times, ghi, np.full(96, 30.0), cfg.plant, cfg.site)
    assert pv[(hours < 6) | (hours > 18)].max() == 0.0
    assert 0 < pv.max() <= cfg.plant.capacity_mw_ac + 1e-9
    assert pv[48] > pv[30]  # noon above 07:30


def test_hourly_to_blocks_preserves_energy(cfg):
    # Open-Meteo convention: the value stamped hh:00 is the mean of the preceding hour (centre hh-0:30).
    # Build a day that follows the clear-sky shape scaled by 0.8 so the clear-sky-index interpolation is exact-ish.
    from sunflow.physics import clearsky_ghi
    hours = pd.date_range("2025-03-15", periods=24, freq="h", tz=cfg.site.timezone)
    cs_centred = clearsky_ghi(hours - pd.Timedelta(minutes=30), cfg.site)
    ghi_h = 0.8 * cs_centred
    bt, ghi_b, temp_b = hourly_to_blocks(hours, ghi_h, np.full(24, 30.0), cfg.site)
    assert len(bt) == 96 and ghi_b.min() >= 0
    e_h = ghi_h.sum() * 1.0
    e_b = ghi_b.sum() * 0.25
    assert abs(e_b - e_h) / e_h < 0.05
    assert abs(temp_b.mean() - 30.0) < 1e-9


def test_soil_bucket_and_conversion(cfg):
    cal = CropCalendar(cfg.crops["kharif_soybean"])
    b = SoilBucket.initial(cal, cfg.irrigation)
    rec = None
    for d in pd.date_range("2025-07-20", periods=12, freq="D"):
        rec = b.step_day(d.date(), et0_mm=6.0, rain_mm=0.0)
        assert 0 <= b.depletion_mm <= cal.taw_mm
    assert rec["requirement_mm"] > 0 and 0 < rec["urgency"] <= 1
    blocks = mm_to_pump_blocks(30.0, 16.0, 10, 25.0, 0.6)
    assert blocks == 128
    assert abs(blocks_to_mm(blocks, 16.0, 10, 25.0, 0.6) - 30.0) < 1e-9
    b.apply_irrigation(1000)
    assert b.depletion_mm == 0.0

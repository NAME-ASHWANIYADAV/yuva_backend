"""PV plant model (PHYSICS): irradiance -> AC power with pvlib's PVWatts chain.

Inputs are hourly or 15-minute irradiance series; outputs are MW AC at the plant capacity in config.
Plant parameters other than capacity are ASSUMED (see configs/lamjana.yaml).
"""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
import pandas as pd
import pvlib

from ..core.config import PlantConfig, SiteConfig
from ..core.timegrid import TimeGrid


def _location(site: SiteConfig) -> pvlib.location.Location:
    return pvlib.location.Location(site.latitude, site.longitude, tz=site.timezone, altitude=site.altitude_m)


def clearsky_ghi(times: pd.DatetimeIndex, site: SiteConfig) -> np.ndarray:
    loc = _location(site)
    try:
        cs = loc.get_clearsky(times, model="ineichen")
    except Exception:  # turbidity lookup unavailable offline: fall back to a simpler model
        cs = loc.get_clearsky(times, model="haurwitz")
    return np.asarray(cs["ghi"].values, dtype=float)


def plant_power_mw(times: pd.DatetimeIndex, ghi: np.ndarray, temp_air: np.ndarray, plant: PlantConfig,
                   site: SiteConfig, dni: Optional[np.ndarray] = None, dhi: Optional[np.ndarray] = None,
                   wind_ms: float = 1.0) -> np.ndarray:
    """AC power in MW for a fixed-tilt PVWatts plant. If DNI/DHI are missing they are decomposed from GHI (Erbs)."""
    ghi = np.clip(np.nan_to_num(np.asarray(ghi, dtype=float)), 0, None)
    temp_air = np.nan_to_num(np.asarray(temp_air, dtype=float), nan=25.0)
    loc = _location(site)
    solpos = loc.get_solarposition(times)
    zenith = solpos["apparent_zenith"].values
    if dni is None or dhi is None:
        erbs = pvlib.irradiance.erbs(ghi, zenith, times)
        dni = np.asarray(erbs["dni"].values, dtype=float)
        dhi = np.asarray(erbs["dhi"].values, dtype=float)
    dni = np.clip(np.nan_to_num(np.asarray(dni, dtype=float)), 0, None)
    dhi = np.clip(np.nan_to_num(np.asarray(dhi, dtype=float)), 0, None)
    dni_extra = pvlib.irradiance.get_extra_radiation(times)
    poa = pvlib.irradiance.get_total_irradiance(
        plant.tilt_deg, plant.azimuth_deg, zenith, solpos["azimuth"].values,
        dni=dni, ghi=ghi, dhi=dhi, dni_extra=dni_extra, model="haydavies",
    )
    poa_global = np.clip(np.nan_to_num(np.asarray(poa["poa_global"], dtype=float)), 0, None)
    cell_temp = pvlib.temperature.noct_sam(poa_global, temp_air, wind_ms, plant.noct_c, 0.18)
    pdc0_w = plant.capacity_mw_ac * plant.dc_ac_ratio * 1e6
    pdc = pvlib.pvsystem.pvwatts_dc(poa_global, cell_temp, pdc0_w, plant.gamma_pdc_per_c)
    pdc = pdc * (1.0 - plant.system_losses_frac)
    pac = pvlib.inverter.pvwatts(pdc, plant.capacity_mw_ac * 1e6 / 0.96, eta_inv_nom=0.96)
    pac = np.clip(np.nan_to_num(np.asarray(pac, dtype=float)), 0, plant.capacity_mw_ac * 1e6)
    return pac / 1e6


def hourly_to_blocks(hour_times: pd.DatetimeIndex, hourly_ghi: np.ndarray, hourly_temp: np.ndarray,
                     site: SiteConfig, grid: TimeGrid = TimeGrid()) -> Tuple[pd.DatetimeIndex, np.ndarray, np.ndarray]:
    """Interpolate hourly GHI/temperature to 15-minute blocks for ONE day using the clear-sky index.

    Open-Meteo hourly radiation is the mean of the preceding hour, so it is centred at hh:30 before interpolation.
    Temperature is instantaneous and interpolated linearly.
    """
    assert len(hour_times) == 24, "one local day of hourly data expected"
    day = hour_times[0].normalize()
    block_times = pd.date_range(day, periods=grid.N, freq=f"{grid.dt_min}min", tz=hour_times.tz)
    centred = hour_times - pd.Timedelta(minutes=30)
    cs_h = clearsky_ghi(centred, site)
    cs_b = clearsky_ghi(block_times, site)
    ghi_h = np.clip(np.nan_to_num(np.asarray(hourly_ghi, dtype=float)), 0, None)
    kt_h = np.where(cs_h > 10.0, ghi_h / np.maximum(cs_h, 1e-6), np.nan)
    kt_series = pd.Series(kt_h, index=centred).interpolate(method="time", limit_direction="both")
    kt_b = np.interp(block_times.astype("int64"), centred.astype("int64"), kt_series.values)
    kt_b = np.clip(np.nan_to_num(kt_b, nan=0.0), 0.0, 1.2)
    ghi_b = np.where(cs_b > 10.0, kt_b * cs_b, 0.0)
    temp_b = np.interp(block_times.astype("int64"), hour_times.astype("int64"), np.nan_to_num(np.asarray(hourly_temp, dtype=float), nan=25.0))
    return block_times, ghi_b, temp_b


def day_profile_from_hourly(day_df: pd.DataFrame, plant: PlantConfig, site: SiteConfig,
                            grid: TimeGrid = TimeGrid()) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """From one local day of hourly rows (columns time, ghi, temp) return (pv_mw[96], ambient_c[96], ghi_wm2[96])."""
    df = day_df.sort_values("time")
    times = pd.DatetimeIndex(df["time"])
    if times.tz is None:
        times = times.tz_localize(site.timezone)
    block_times, ghi_b, temp_b = hourly_to_blocks(times, df["ghi"].values, df["temp"].values, site, grid)
    pv = plant_power_mw(block_times, ghi_b, temp_b, plant, site)
    return pv, temp_b, ghi_b

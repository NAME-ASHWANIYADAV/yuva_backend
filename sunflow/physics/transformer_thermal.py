"""IEC 60076-7 exponential-equation thermal model for ONAN distribution transformers (PHYSICS).

Equations (IEC 60076-7:2018, clause 8.2 exponential form), discretised exactly for piecewise-constant load
(zero-order hold on each 15-minute block):

  top-oil rise      d(Dto)/dt  = (1/(k11*tau_o)) * [ Dtor * ((1 + K^2 R)/(1 + R))^x - Dto ]
  hot-spot rise 1   d(Dth1)/dt = (1/(k22*tau_w)) * [ k21 * Dthr * K^y - Dth1 ]
  hot-spot rise 2   d(Dth2)/dt = (1/(tau_o/k22)) * [ (k21 - 1) * Dthr * K^y - Dth2 ]
  hot-spot          theta_h = theta_ambient + Dto + Dth1 - Dth2
  relative ageing   V = 2^((theta_h - 98)/6)      (non-thermally-upgraded paper)

The default constants are the IEC Table 4 values for ONAN distribution transformers as reproduced in open
literature (the standard itself is paywalled). No transformer at Latur is instrumented; every result is MODELLED.

Key property used by the optimiser: for a block in which the transformer load K takes one of a small set of
values, the forcing terms g_o(K) and g_h(K) are constants, so the recursion is LINEAR in the on/off indicators.
The optimiser builds that linear recursion from `lag_coefficients` and the `*_input` helpers; the verifier uses
`simulate_thermal` (continuous K) and never shares code with the optimiser's constraint construction.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional

import numpy as np

from ..core.config import ThermalConfig


@dataclass(frozen=True)
class ThermalParams:
    delta_theta_or: float = 55.0
    delta_theta_hr: float = 23.0
    R: float = 5.0
    x: float = 0.8
    y: float = 1.6
    k11: float = 1.0
    k21: float = 1.0
    k22: float = 2.0
    tau_o_min: float = 180.0
    tau_w_min: float = 4.0
    hot_spot_limit_c: float = 120.0
    ageing_reference_c: float = 98.0
    initial_top_oil_rise_k: float = 5.0

    @classmethod
    def from_config(cls, c: ThermalConfig) -> "ThermalParams":
        return cls(
            delta_theta_or=c.delta_theta_or_k, delta_theta_hr=c.delta_theta_hr_k, R=c.ratio_r, x=c.x, y=c.y,
            k11=c.k11, k21=c.k21, k22=c.k22, tau_o_min=c.tau_o_min, tau_w_min=c.tau_w_min,
            hot_spot_limit_c=c.hot_spot_limit_c, ageing_reference_c=c.ageing_reference_c,
            initial_top_oil_rise_k=c.initial_top_oil_rise_k,
        )

    def scaled(self, factor: float) -> "ThermalParams":
        """Pessimistic (factor > 1) or optimistic band: rises scale up, time constants scale down."""
        return replace(
            self,
            delta_theta_or=self.delta_theta_or * factor,
            delta_theta_hr=self.delta_theta_hr * factor,
            tau_o_min=self.tau_o_min / factor,
            tau_w_min=self.tau_w_min / factor,
        )


def oil_rise_input(K: np.ndarray | float, p: ThermalParams) -> np.ndarray | float:
    K = np.asarray(K, dtype=float)
    return p.delta_theta_or * ((1.0 + (K ** 2) * p.R) / (1.0 + p.R)) ** p.x


def hotspot_rise_input(K: np.ndarray | float, p: ThermalParams) -> np.ndarray | float:
    K = np.asarray(K, dtype=float)
    return p.delta_theta_hr * (K ** p.y)


def lag_coefficients(p: ThermalParams, dt_min: float) -> tuple[float, float, float]:
    """Exact ZOH decay factors (a_o, a_h1, a_h2) for one block of dt_min minutes."""
    a_o = float(np.exp(-dt_min / (p.k11 * p.tau_o_min)))
    a_h1 = float(np.exp(-dt_min / (p.k22 * p.tau_w_min)))
    a_h2 = float(np.exp(-dt_min / (p.tau_o_min / p.k22)))
    return a_o, a_h1, a_h2


def ageing_rate(theta_h: np.ndarray | float, p: ThermalParams) -> np.ndarray | float:
    return 2.0 ** ((np.asarray(theta_h, dtype=float) - p.ageing_reference_c) / 6.0)


def steady_state_hot_spot(K: float, ambient_c: float, p: ThermalParams) -> float:
    return float(ambient_c + oil_rise_input(K, p) + p.k21 * hotspot_rise_input(K, p) - (p.k21 - 1.0) * hotspot_rise_input(K, p))


@dataclass
class ThermalTrace:
    top_oil_c: np.ndarray
    hot_spot_c: np.ndarray
    ageing_rate: np.ndarray
    dt_h: float

    @property
    def ageing_hours(self) -> float:
        return float(np.sum(self.ageing_rate) * self.dt_h)

    @property
    def max_hot_spot(self) -> float:
        return float(np.max(self.hot_spot_c))

    def exceedance_blocks(self, limit_c: float) -> int:
        return int(np.sum(self.hot_spot_c > limit_c + 1e-9))


def simulate_thermal(K: np.ndarray, ambient_c: np.ndarray, p: ThermalParams, dt_min: float = 15.0,
                     init_oil_rise: Optional[float] = None, init_h1: float = 0.0, init_h2: float = 0.0) -> ThermalTrace:
    """Simulate the full nonlinear IEC model for a load-factor series K (per-unit of rating) and ambient series."""
    K = np.clip(np.nan_to_num(np.asarray(K, dtype=float)), 0.0, None)
    amb = np.asarray(ambient_c, dtype=float)
    n = len(K)
    a_o, a_h1, a_h2 = lag_coefficients(p, dt_min)
    g_o = oil_rise_input(K, p)
    g_h = hotspot_rise_input(K, p)
    d_o = np.empty(n); d_h1 = np.empty(n); d_h2 = np.empty(n)
    o = p.initial_top_oil_rise_k if init_oil_rise is None else init_oil_rise
    h1, h2 = init_h1, init_h2
    for t in range(n):
        o = a_o * o + (1.0 - a_o) * g_o[t]
        h1 = a_h1 * h1 + (1.0 - a_h1) * p.k21 * g_h[t]
        h2 = a_h2 * h2 + (1.0 - a_h2) * (p.k21 - 1.0) * g_h[t]
        d_o[t], d_h1[t], d_h2[t] = o, h1, h2
    top_oil = amb + d_o
    hot_spot = amb + d_o + d_h1 - d_h2
    return ThermalTrace(top_oil_c=top_oil, hot_spot_c=hot_spot, ageing_rate=ageing_rate(hot_spot, p), dt_h=dt_min / 60.0)

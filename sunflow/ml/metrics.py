"""Probabilistic forecast metrics."""
from __future__ import annotations

from typing import Dict

import numpy as np


def pinball(y: np.ndarray, q: np.ndarray, alpha: float) -> float:
    d = y - q
    return float(np.mean(np.maximum(alpha * d, (alpha - 1) * d)))


def point_metrics(y: np.ndarray, yhat: np.ndarray) -> Dict[str, float]:
    e = yhat - y
    return {"mae": float(np.mean(np.abs(e))), "rmse": float(np.sqrt(np.mean(e ** 2))), "bias": float(np.mean(e))}


def band_metrics(y: np.ndarray, p10: np.ndarray, p50: np.ndarray, p90: np.ndarray) -> Dict[str, float]:
    out = point_metrics(y, p50)
    out["pinball_10"] = pinball(y, p10, 0.1)
    out["pinball_50"] = pinball(y, p50, 0.5)
    out["pinball_90"] = pinball(y, p90, 0.9)
    out["pinball_mean"] = (out["pinball_10"] + out["pinball_50"] + out["pinball_90"]) / 3.0
    out["coverage_80"] = float(np.mean((y >= p10) & (y <= p90)))
    out["below_p10"] = float(np.mean(y < p10))
    out["above_p90"] = float(np.mean(y > p90))
    out["mean_width"] = float(np.mean(p90 - p10))
    # CRPS approximated from the three quantiles (coarse; reported as such)
    out["crps_approx_3q"] = float(2.0 * out["pinball_mean"])
    return out

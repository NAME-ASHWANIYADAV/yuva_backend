"""Train the quantile forecast-error model (LightGBM q10/q50/q90) on real archived NWP vs ERA5.

Time-based split: train 2023-2024, test 2025 (2026 to date as an extra hold-out). Baselines are evaluated on the
same test rows. If LightGBM does not beat the best baseline on mean pinball loss, the best baseline is shipped
and the decision is written to models/forecast_meta.json.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from ..core.config import SunflowConfig
from ..core.logging import get_logger
from ..core.paths import models_dir
from .features import FEATURES, TRAIN_YEARS, TEST_YEARS, build_dataset, split
from .metrics import band_metrics, point_metrics

log = get_logger("sunflow.ml")
QUANTILES = (0.1, 0.5, 0.9)


@dataclass
class TrainedModels:
    boosters: Dict[float, lgb.Booster]
    linear: LinearRegression
    linear_resid_q: Dict[float, float]
    conformal: Dict[str, float] = None   # additive calibration offsets for p10/p50/p90 from blocked out-of-fold residuals


LGB_PARAMS = dict(learning_rate=0.05, num_leaves=15, min_data_in_leaf=80, feature_fraction=0.9,
                  bagging_fraction=0.9, bagging_freq=1, lambda_l2=5.0, verbose=-1)
N_ROUNDS = 250


def _fit_lgbm(train: pd.DataFrame, seed: int = 7) -> Dict[float, lgb.Booster]:
    boosters = {}
    X, y = train[FEATURES].values, train["y_era5"].values
    for q in QUANTILES:
        params = dict(LGB_PARAMS, objective="quantile", alpha=q, seed=seed)
        boosters[q] = lgb.train(params, lgb.Dataset(X, y), num_boost_round=N_ROUNDS)
    return boosters


def _blocked_oof_conformal(train: pd.DataFrame, n_folds: int = 4, seed: int = 7) -> Dict[str, float]:
    """Split-conformal offsets from blocked (by calendar month) out-of-fold predictions on the training years.

    p10' = p10 + d10 with d10 = 10th percentile of (y - p10_oof); p90' = p90 + d90 with d90 = 90th percentile of
    (y - p90_oof); p50' = p50 + median(y - p50_oof). Coverage is then calibrated on data the model did not fit.
    """
    months = train["time"].dt.to_period("M").astype(str)
    uniq = sorted(months.unique())
    folds = [uniq[i::n_folds] for i in range(n_folds)]
    r10, r50, r90 = [], [], []
    for hold in folds:
        mask = months.isin(hold)
        tr, ho = train[~mask], train[mask]
        if len(ho) == 0 or len(tr) == 0:
            continue
        b = _fit_lgbm(tr, seed)
        p10, p50, p90 = predict_lgbm(b, ho[FEATURES].values, ho["cs_ghi"].values, conformal=None)
        y = ho["y_era5"].values
        r10.append(y - p10); r50.append(y - p50); r90.append(y - p90)
    r10, r50, r90 = np.concatenate(r10), np.concatenate(r50), np.concatenate(r90)
    return {"d10": float(np.quantile(r10, 0.10)), "d50": float(np.median(r50)), "d90": float(np.quantile(r90, 0.90)),
            "n_oof": int(len(r10))}


def _fit_linear(train: pd.DataFrame) -> Tuple[LinearRegression, Dict[float, float]]:
    lr = LinearRegression().fit(train[["nwp_mean_ghi", "cs_ghi"]].values, train["y_era5"].values)
    resid = train["y_era5"].values - lr.predict(train[["nwp_mean_ghi", "cs_ghi"]].values)
    return lr, {q: float(np.quantile(resid, q)) for q in QUANTILES}


def predict_lgbm(boosters: Dict[float, lgb.Booster], X: np.ndarray, cs: np.ndarray,
                 conformal: Dict[str, float] | None = None) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    qs = np.column_stack([boosters[q].predict(X) for q in QUANTILES])
    if conformal:
        qs = qs + np.array([conformal["d10"], conformal["d50"], conformal["d90"]])[None, :]
    qs = np.sort(np.clip(qs, 0, None), axis=1)            # enforce p10 <= p50 <= p90 and non-negativity
    qs = np.minimum(qs, cs[:, None] * 1.15)                # physical cap near clear sky
    return qs[:, 0], qs[:, 1], qs[:, 2]


def evaluate_all(models: TrainedModels, test: pd.DataFrame, truth: str = "y_era5") -> Dict[str, Dict[str, float]]:
    t = test.dropna(subset=[truth])
    y = t[truth].values
    cs = t["cs_ghi"].values
    res: Dict[str, Dict[str, float]] = {}
    res["raw_icon"] = point_metrics(y, t["icon_ghi"].values)
    res["raw_gfs"] = point_metrics(y, t["gfs_ghi"].values)
    res["raw_nwp_mean"] = point_metrics(y, t["nwp_mean_ghi"].values)
    if t["persist_ghi"].notna().any():
        tp = t.dropna(subset=["persist_ghi"])
        res["persistence"] = point_metrics(tp[truth].values, tp["persist_ghi"].values)
    lin = models.linear.predict(t[["nwp_mean_ghi", "cs_ghi"]].values)
    res["linear_correction"] = band_metrics(y, np.clip(lin + models.linear_resid_q[0.1], 0, None), np.clip(lin, 0, None),
                                            np.clip(lin + models.linear_resid_q[0.9], 0, None))
    # naive band around the raw NWP mean using the same residual quantiles (what you'd do without a model)
    res["raw_nwp_mean_band"] = band_metrics(y, np.clip(t["nwp_mean_ghi"].values + models.linear_resid_q[0.1], 0, None),
                                            t["nwp_mean_ghi"].values, np.clip(t["nwp_mean_ghi"].values + models.linear_resid_q[0.9], 0, None))
    p10, p50, p90 = predict_lgbm(models.boosters, t[FEATURES].values, cs, conformal=None)
    res["lgbm_quantile_raw"] = band_metrics(y, p10, p50, p90)
    p10, p50, p90 = predict_lgbm(models.boosters, t[FEATURES].values, cs, conformal=models.conformal)
    res["lgbm_quantile"] = band_metrics(y, p10, p50, p90)
    return res


def by_hour(models: TrainedModels, test: pd.DataFrame) -> pd.DataFrame:
    t = test.copy()
    p10, p50, p90 = predict_lgbm(models.boosters, t[FEATURES].values, t["cs_ghi"].values, conformal=models.conformal)
    t["p50"] = p50; t["p10"] = p10; t["p90"] = p90
    g = t.groupby("hour")
    return pd.DataFrame({
        "mae_lgbm": g.apply(lambda d: np.mean(np.abs(d["p50"] - d["y_era5"]))),
        "mae_icon": g.apply(lambda d: np.mean(np.abs(d["icon_ghi"] - d["y_era5"]))),
        "mae_gfs": g.apply(lambda d: np.mean(np.abs(d["gfs_ghi"] - d["y_era5"]))),
        "coverage_80": g.apply(lambda d: np.mean((d["y_era5"] >= d["p10"]) & (d["y_era5"] <= d["p90"]))),
        "n": g.size(),
    })


def train_and_save(cfg: SunflowConfig, out_dir: Path | None = None) -> dict:
    out = out_dir or models_dir()
    out.mkdir(parents=True, exist_ok=True)
    df = build_dataset(cfg)
    train, test, extra = split(df)
    assert train["time"].max() < test["time"].min(), "leakage: train/test overlap in time"
    log.info(f"dataset rows={len(df)} train={len(train)} test={len(test)} extra={len(extra)} nwp_source={df['nwp_source'].iloc[0]}")
    conformal = _blocked_oof_conformal(train)
    log.info(f"conformal offsets (blocked OOF, n={conformal['n_oof']}): d10={conformal['d10']:.1f} d50={conformal['d50']:.1f} d90={conformal['d90']:.1f}")
    boosters = _fit_lgbm(train)
    lin, resq = _fit_linear(train)
    models = TrainedModels(boosters, lin, resq, conformal)
    metrics = {"test_vs_era5": evaluate_all(models, test, "y_era5")}
    if test["y_nasa"].notna().sum() > 100:
        metrics["test_vs_nasa_power"] = evaluate_all(models, test, "y_nasa")
    if len(extra) > 100:
        metrics["extra_holdout_vs_era5"] = evaluate_all(models, extra, "y_era5")
    # proxy disagreement floor: ERA5 vs NASA POWER on the test rows
    tt = test.dropna(subset=["y_nasa"])
    if len(tt):
        metrics["proxy_disagreement_era5_vs_nasa"] = point_metrics(tt["y_era5"].values, tt["y_nasa"].values)
    lg = metrics["test_vs_era5"]["lgbm_quantile"]["pinball_mean"]
    lg_cov = metrics["test_vs_era5"]["lgbm_quantile"]["coverage_80"]
    lin_p = metrics["test_vs_era5"]["linear_correction"]["pinball_mean"]
    raw_p = metrics["test_vs_era5"]["raw_nwp_mean_band"]["pinball_mean"]
    best_baseline = min(lin_p, raw_p)
    # ship the learned model only if it beats the best baseline on pinball AND its 80% band is reasonably calibrated
    if lg < best_baseline and 0.70 <= lg_cov <= 0.90:
        ship = "lgbm_quantile"
    else:
        ship = "linear_correction" if lin_p <= raw_p else "raw_nwp_mean_band"
    for q, b in boosters.items():
        b.save_model(str(out / f"forecast_lgbm_q{int(q * 100)}.txt"))
    meta = {
        "features": FEATURES, "train_years": TRAIN_YEARS, "test_years": TEST_YEARS,
        "n_train": int(len(train)), "n_test": int(len(test)), "n_extra": int(len(extra)),
        "nwp_source": str(df["nwp_source"].iloc[0]),
        "truth": "ERA5 reanalysis GHI (proxy, not ground measurement); NASA POWER as second proxy",
        "shipped_model": ship, "conformal": conformal, "lgb_params": LGB_PARAMS, "n_rounds": N_ROUNDS,
        "ship_rule": "lgbm if pinball < best baseline and 0.70 <= coverage80 <= 0.90 on test year",
        "linear_coef": lin.coef_.tolist(), "linear_intercept": float(lin.intercept_),
        "linear_resid_quantiles": {str(k): v for k, v in resq.items()}, "metrics": metrics,
        "by_hour": by_hour(models, test).reset_index().to_dict(orient="list"),
    }
    with open(out / "forecast_meta.json", "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, default=float)
    log.info(f"shipped_model={ship} lgbm_pinball={lg:.2f} linear={lin_p:.2f} raw_band={raw_p:.2f}")
    return meta

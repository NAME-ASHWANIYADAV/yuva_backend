from datetime import date

import numpy as np
import pytest

from sunflow.ml import build_dataset, FEATURES, ForecastModel, band_for_day
from sunflow.ml.features import split, TRAIN_YEARS, TEST_YEARS
from sunflow.ml.metrics import pinball, band_metrics


def test_dataset_and_split_have_no_time_leakage(cfg):
    df = build_dataset(cfg)
    assert len(df) > 5000
    assert set(FEATURES).issubset(df.columns)
    train, test, extra = split(df)
    assert train["time"].max() < test["time"].min()
    assert train["year"].min() >= TRAIN_YEARS[0] and test["year"].max() <= TEST_YEARS[1]
    assert (df["cs_ghi"] > 20).all()


def test_metrics_basic():
    y = np.array([100.0, 200.0, 300.0])
    assert pinball(y, y, 0.5) == 0.0
    m = band_metrics(y, y - 10, y, y + 10)
    assert m["coverage_80"] == 1.0 and m["mae"] == 0.0


@pytest.mark.skipif(not ForecastModel.available(), reason="model not trained yet (run scripts/train_forecast.py)")
def test_inference_band_for_real_day(cfg):
    band = band_for_day(cfg, date(2025, 4, 10))
    for k in ("p10", "p50", "p90"):
        assert band[k].shape == (96,)
    assert np.all(band["p10"] <= band["p50"] + 1e-9) and np.all(band["p50"] <= band["p90"] + 1e-9)
    assert band["p50"].max() > 1.0 and band["p50"][:20].max() == 0.0

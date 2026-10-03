import pandas as pd

from sunflow.data import cache as cache_mod
from sunflow.data import cached_frame


def test_cached_frame_hits_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_mod, "_raw_dir", lambda: tmp_path)
    calls = {"n": 0}

    def producer():
        calls["n"] += 1
        return pd.DataFrame({"time": pd.to_datetime(["2025-01-01 00:00", "2025-01-01 01:00"]), "ghi": [0.0, 10.0]})

    a = cached_frame("unit_test_frame", producer)
    b = cached_frame("unit_test_frame", producer)
    assert calls["n"] == 1
    assert list(b.columns) == ["time", "ghi"]
    assert str(b["time"].dtype).startswith("datetime64")
    assert len(a) == len(b) == 2


def test_best_match_is_refused():
    import pytest
    from sunflow.data.openmeteo import fetch_nwp_hourly
    from datetime import date
    with pytest.raises(ValueError):
        fetch_nwp_hourly("best_match", date(2024, 1, 1), date(2024, 1, 2))

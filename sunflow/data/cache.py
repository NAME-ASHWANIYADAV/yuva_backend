"""Tiny file cache for downloaded frames (parquet if available, else CSV)."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import pandas as pd

from ..core.paths import data_dir


def _raw_dir() -> Path:
    d = data_dir() / "raw"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_file(name: str) -> Path:
    return _raw_dir() / f"{name}.csv"


def cached_frame(name: str, producer: Callable[[], pd.DataFrame], refresh: bool = False) -> pd.DataFrame:
    """Return the cached frame for `name`, producing and storing it if absent."""
    path = cache_file(name)
    if path.exists() and not refresh:
        df = pd.read_csv(path)
        for col in ("time", "date"):
            if col in df.columns:
                df[col] = pd.to_datetime(df[col])
        return df
    df = producer()
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return df

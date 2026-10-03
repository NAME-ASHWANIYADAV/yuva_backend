"""Repository-relative paths. Nothing in the code base uses an absolute path."""
from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _dir(env: str, default: str) -> Path:
    p = Path(os.environ.get(env, default))
    if not p.is_absolute():
        p = repo_root() / p
    p.mkdir(parents=True, exist_ok=True)
    return p


def data_dir() -> Path:
    return _dir("SUNFLOW_DATA_DIR", "data")


def models_dir() -> Path:
    return _dir("SUNFLOW_MODELS_DIR", "models")


def results_dir() -> Path:
    return _dir("SUNFLOW_RESULTS_DIR", "results")


def config_path() -> Path:
    p = Path(os.environ.get("SUNFLOW_CONFIG", "configs/lamjana.yaml"))
    return p if p.is_absolute() else repo_root() / p


def weights_path() -> Path:
    return repo_root() / "configs" / "weights.yaml"

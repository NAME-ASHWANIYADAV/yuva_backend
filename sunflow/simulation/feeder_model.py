"""Feeder / transformer load model (SYNTHETIC inventory from ASSUMED config values).

Loads aggregate radially: pumps -> distribution transformer (DT) -> feeder -> power transformer (PT).
No AC power flow is run (voltage is not modelled; stated limitation). A failed DT's pump load is carried by its
two neighbouring DTs on the same feeder (ASSUMED operating practice when a DT burns out and farmers are re-tapped).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Set

import numpy as np

from ..core.config import SunflowConfig, DTConfig


@dataclass
class DTState:
    id: str
    feeder: str
    rating_kva: float
    installed_kva: float        # own pumps
    carried_kva: float          # own + reallocated from failed neighbours (0 if failed)
    failed: bool = False

    @property
    def K_on(self) -> float:
        """Per-unit load factor at participation 1.0 when the feeder is energised."""
        return 0.0 if self.failed else self.carried_kva / self.rating_kva


class FeederModel:
    def __init__(self, cfg: SunflowConfig, failed_dts: Set[str] | None = None):
        self.cfg = cfg
        self.failed = set(failed_dts or set())
        self.dts: Dict[str, DTState] = {}
        self.feeder_dts: Dict[str, List[str]] = {}
        for f in cfg.feeders:
            ids = []
            for d in f.dts:
                inst = cfg.dt_installed_kva(d)
                self.dts[d.id] = DTState(d.id, f.name, d.rating_kva, inst, inst, failed=d.id in self.failed)
                ids.append(d.id)
            self.feeder_dts[f.name] = ids
        self._reallocate_failed()

    def _reallocate_failed(self) -> None:
        for fname, ids in self.feeder_dts.items():
            for i, did in enumerate(ids):
                dt = self.dts[did]
                if not dt.failed:
                    continue
                dt.carried_kva = 0.0
                neighbours = [ids[j] for j in (i - 1, i + 1) if 0 <= j < len(ids) and not self.dts[ids[j]].failed]
                if not neighbours:
                    continue
                share = dt.installed_kva / len(neighbours)
                for nid in neighbours:
                    self.dts[nid].carried_kva += share

    def feeder_installed_kva(self, feeder: str) -> float:
        """kVA drawn by the feeder at participation 1.0 (failed DTs' pumps carried by neighbours)."""
        return float(sum(self.dts[d].carried_kva for d in self.feeder_dts[feeder]))

    def participation_profile(self, u: np.ndarray, participation: float) -> np.ndarray:
        """Per-block participation: surge level in the first blocks after each energisation, default afterwards."""
        p = self.cfg.participation
        u = np.asarray(u, dtype=int)
        prof = np.zeros(len(u), dtype=float)
        since_start = None
        for t in range(len(u)):
            if u[t] == 1:
                since_start = 0 if (t == 0 or u[t - 1] == 0) else since_start + 1
                prof[t] = p.surge_level if since_start < p.surge_blocks else participation
            else:
                since_start = None
        return prof

    def feeder_kva_series(self, feeder: str, u: np.ndarray, participation: float) -> np.ndarray:
        return self.feeder_installed_kva(feeder) * self.participation_profile(u, participation)

    def dt_load_factor_series(self, dt_id: str, u: np.ndarray, participation: float) -> np.ndarray:
        dt = self.dts[dt_id]
        return dt.K_on * self.participation_profile(u, participation)

    def pt_feeders(self) -> Dict[str, List[str]]:
        return {p.name: [f.name for f in self.cfg.feeders_on_pt(p.name)] for p in self.cfg.power_transformers}

    def irrigated_ha(self, feeder: str) -> float:
        return float(sum(d.irrigated_ha for d in self.cfg.feeder(feeder).dts))

    def n_pumps(self, feeder: str) -> int:
        return int(sum(d.n_pumps for d in self.cfg.feeder(feeder).dts))

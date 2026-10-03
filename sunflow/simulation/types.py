"""Shared data types: Plan, Scenario, SimResult."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

from ..core.timegrid import TimeGrid

Plan = Dict[str, np.ndarray]  # feeder name -> int array[96] of 0/1


def plan_from_slots(slots: Dict[str, Tuple[str, str]], grid: TimeGrid = TimeGrid()) -> Plan:
    plan: Plan = {}
    for f, (s, e) in slots.items():
        u = np.zeros(grid.N, dtype=int)
        u[grid.block_of(s):grid.block_of(e)] = 1
        plan[f] = u
    return plan


def plan_starts(u: np.ndarray) -> List[int]:
    u = np.asarray(u, dtype=int)
    prev = np.concatenate([[0], u[:-1]])
    return [int(t) for t in np.where((u == 1) & (prev == 0))[0]]


def plan_spells(u: np.ndarray) -> List[Tuple[int, int]]:
    """List of (start_block, end_block_exclusive)."""
    u = np.asarray(u, dtype=int)
    spells = []
    start = None
    for t, v in enumerate(u):
        if v == 1 and start is None:
            start = t
        if v == 0 and start is not None:
            spells.append((start, t))
            start = None
    if start is not None:
        spells.append((start, len(u)))
    return spells


def plan_copy(plan: Plan) -> Plan:
    return {f: np.array(u, dtype=int, copy=True) for f, u in plan.items()}


@dataclass
class Scenario:
    """Everything the simulator, optimiser and verifier need for one operating day."""
    day: date
    pv_p50_mw: np.ndarray                      # [96] expected plant output
    ambient_c: np.ndarray                      # [96]
    pv_p10_mw: Optional[np.ndarray] = None
    pv_p90_mw: Optional[np.ndarray] = None
    participation: Optional[float] = None      # overrides config default when set
    thermal_factor: float = 1.0                # multiplies IEC rises / divides time constants
    ambient_offset_c: float = 0.0
    failed_dts: Set[str] = field(default_factory=set)
    feeder_outages: Dict[str, List[Tuple[int, int]]] = field(default_factory=dict)  # feeder -> [(t0, t1 exclusive)]
    irrigation_required_blocks: Dict[str, int] = field(default_factory=dict)       # feeder -> min blocks today
    irrigation_urgency: Dict[str, float] = field(default_factory=dict)             # feeder -> 0..1
    preferred_start: Dict[str, int] = field(default_factory=dict)                  # feeder -> block (fairness rotation)
    announced_plan: Optional[Plan] = None
    now_block: int = 0                          # intra-day: blocks < lock_until are locked to the announced plan
    lock_until: int = 0
    label: str = "day"
    weather_source: str = "unspecified"

    def pv(self, quantile: str = "p50") -> np.ndarray:
        if quantile == "p10" and self.pv_p10_mw is not None:
            return self.pv_p10_mw
        if quantile == "p90" and self.pv_p90_mw is not None:
            return self.pv_p90_mw
        return self.pv_p50_mw

    def feeder_available(self, feeder: str) -> np.ndarray:
        avail = np.ones(len(self.pv_p50_mw), dtype=int)
        for t0, t1 in self.feeder_outages.get(feeder, []):
            avail[t0:t1] = 0
        return avail


@dataclass
class SimResult:
    plan: Plan
    blocks: List[str]
    pv_mw: np.ndarray
    load_kw: np.ndarray
    import_kw: np.ndarray
    surplus_kw: np.ndarray
    feeder_kva: Dict[str, np.ndarray]
    pt_kva: Dict[str, np.ndarray]
    pt_rating_kva: Dict[str, float]
    dt_hot_spot_c: Dict[str, np.ndarray]
    dt_rating_kva: Dict[str, float]
    dt_feeder: Dict[str, str]
    dt_ageing_hours: Dict[str, float]
    metrics: Dict[str, float]
    per_feeder: Dict[str, Dict[str, float]]
    violations: List[dict] = field(default_factory=list)   # informational (rule checks done by the verifier)

"""Baseline = MSEDCL's published Annexure-A slots (PUBLIC), replayed as a plan."""
from __future__ import annotations

from ..core.config import SunflowConfig
from ..core.timegrid import TimeGrid
from .types import Plan, plan_from_slots


def baseline_plan(cfg: SunflowConfig, grid: TimeGrid = TimeGrid()) -> Plan:
    return plan_from_slots({f.name: tuple(f.published_slot) for f in cfg.feeders}, grid)

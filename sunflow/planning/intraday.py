"""Receding-horizon re-planning: announced blocks stay locked; only future blocks may move."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from ..core.config import SunflowConfig, Weights
from ..optimization.inputs import SolveOptions
from ..simulation.types import Plan, Scenario, plan_copy
from ..verification import Certified, VerifySettings, certify


@dataclass
class ReplanResult:
    certified: Certified
    changes_blocks: int
    changed_feeders: List[str]
    trigger: str
    now_block: int
    lock_until: int
    note: str = ""


def forecast_change_fraction(old_p50: np.ndarray, new_p50: np.ndarray, from_block: int) -> float:
    """Relative change of remaining expected solar energy; used as a re-plan trigger."""
    a = np.asarray(old_p50, dtype=float)[from_block:]
    b = np.asarray(new_p50, dtype=float)[from_block:]
    denom = max(float(a.sum()), 1e-6)
    return float(np.abs(b - a).sum() / denom)


def replan(cfg: SunflowConfig, weights: Weights, scenario: Scenario, announced: Plan, now_block: int,
           trigger: str, lock_blocks: int = 4, options: Optional[SolveOptions] = None,
           settings: Optional[VerifySettings] = None) -> ReplanResult:
    """Re-solve from `now_block` with the next `lock_blocks` announced blocks (and the past) frozen."""
    sc = scenario
    sc.announced_plan = plan_copy(announced)
    sc.now_block = int(now_block)
    sc.lock_until = int(min(96, now_block + lock_blocks))
    cert = certify(cfg, sc, weights, options, settings)
    changes = 0
    changed: List[str] = []
    for f in cfg.feeders:
        new = np.asarray(cert.plan[f.name], dtype=int)
        old = np.asarray(announced[f.name], dtype=int)
        diff = int(np.sum(new[sc.lock_until:] != old[sc.lock_until:]))
        if diff:
            changed.append(f.name)
        changes += diff
    note = "" if cert.certified else "re-plan not certified; announced plan or published timetable retained"
    return ReplanResult(certified=cert, changes_blocks=changes, changed_feeders=changed, trigger=trigger,
                        now_block=sc.now_block, lock_until=sc.lock_until, note=note)

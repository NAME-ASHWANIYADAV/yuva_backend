"""In-memory demo state: one substation, one operating day, a current scenario and an action log."""
from __future__ import annotations

import copy
import threading
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

import numpy as np

from ..core.config import SunflowConfig, Weights, load_config, load_weights
from ..core.logging import get_logger
from ..core.timegrid import TimeGrid
from ..optimization.inputs import SolveOptions
from ..planning import plan_day, result_to_dict, replan, explain_request
from ..scenarios import apply_scenario
from ..simulation import Scenario, scenario_from_era5_day
from ..simulation.types import plan_copy

log = get_logger("sunflow.api")
DEFAULT_DAY = date(2025, 10, 20)   # post-monsoon kharif day: dry soil (high irrigation urgency), clear skies (real ERA5)


@dataclass
class DemoState:
    cfg: SunflowConfig
    weights: Weights
    day: date = DEFAULT_DAY
    base_scenario: Optional[Scenario] = None
    scenario: Optional[Scenario] = None
    base_result: Optional[dict] = None
    current: Optional[dict] = None
    announced_plan: Optional[dict] = None
    now_block: int = 0
    max_spells_allowed: int = 1          # spells the current certified plan was allowed (farmer requests reuse it)
    log: List[dict] = field(default_factory=list)
    cache: Dict[str, dict] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)
    grid: TimeGrid = field(default_factory=TimeGrid)

    @classmethod
    def create(cls, warm: bool = True) -> "DemoState":
        st = cls(cfg=load_config(), weights=load_weights())
        if warm:
            threading.Thread(target=st.warm_up, name="sunflow-warmup", daemon=True).start()
        return st

    WARM_KINDS = (("cloud_ramp", {}), ("heat_wave", {"offset_c": 3}), ("dt_failure", {}),
                  ("feeder_outage", {"feeder": "Kharosa", "start": "11:00", "end": "13:00"}),
                  ("full_participation", {}), ("impossible", {}))

    def warm_up(self) -> None:
        """Precompute the default day and the named what-if scenarios so demo buttons answer from cache.
        Every cached answer is a real computation; the action log reports it as 'cached' with its original time."""
        try:
            self.reset()
            for kind, params in self.WARM_KINDS:
                self.run_scenario(kind, dict(params))
            self.current = self.base_result
            self.scenario = copy.deepcopy(self.base_scenario)
            log.info("warm-up complete")
        except Exception as exc:  # warm-up is best effort
            log.warning(f"warm-up failed: {exc!r}")

    # ------------------------------------------------------------------ core actions
    def reset(self, day: Optional[date] = None) -> dict:
        with self.lock:
            new_day = day or self.day
            if new_day != self.day:
                self.cache = {}           # precomputed scenarios belong to one operating day
            self.day = new_day
            t0 = time.time()
            r = plan_day(self.cfg, self.weights, self.day)
            self.base_scenario = r.scenario
            self.scenario = copy.deepcopy(r.scenario)
            self.base_result = result_to_dict(r)
            self.current = self.base_result
            self.announced_plan = plan_copy(r.certified.plan)
            self.max_spells_allowed = int(getattr(r.certified, 'max_spells_allowed', 1))
            self.now_block = 0
            self.log = [self._entry("reset", f"day {self.day.isoformat()} planned", t0, r.certified.status)]
            return self.current

    def _entry(self, action: str, detail: str, t0: float, status: str = "") -> dict:
        return {"action": action, "detail": detail, "status": status, "seconds": round(time.time() - t0, 2), "ts": time.time()}

    def ensure(self) -> None:
        if self.current is None:
            self.reset()

    def baseline(self) -> dict:
        self.ensure()
        return {"baseline": self.current["baseline"], "baseline_verify": self.current["baseline_verify"], "day": self.day.isoformat()}

    def certify(self) -> dict:
        self.ensure()
        with self.lock:
            t0 = time.time()
            r = plan_day(self.cfg, self.weights, self.day, scenario=copy.deepcopy(self.scenario))
            self.current = result_to_dict(r)
            # the band inside the scenario is the one chosen at reset (learned model when available); keep its label
            self.current["forecast_source"] = (self.base_result or {}).get("forecast_source", self.current["forecast_source"])                 if (self.current.get("scenario_kind") in (None, "base")) else self.current["forecast_source"]
            self.announced_plan = plan_copy(r.certified.plan)
            self.max_spells_allowed = int(getattr(r.certified, 'max_spells_allowed', 1))
            self.log.append(self._entry("certify", r.certified.status, t0, r.certified.status))
            return self.current

    def run_scenario(self, kind: str, params: Optional[dict] = None, intraday: bool = False, now: str = "11:00") -> dict:
        self.ensure()
        params = params or {}
        key = f"{kind}:{sorted(params.items())}:{intraday}:{now}"
        if key in self.cache:
            cached = self.cache[key]
            self.log.append(self._entry(kind, f"cached (computed in {cached.get('compute_seconds', '?')} s)", time.time(), cached["certified"]["status"]))
            self.current = cached
            self.scenario = apply_scenario(self.cfg, self.base_scenario, kind, **params)
            self.max_spells_allowed = int(cached.get("max_spells_allowed", 1))
            return self.current
        with self.lock:
            t0 = time.time()
            sc = apply_scenario(self.cfg, self.base_scenario, kind, **params)
            if intraday and self.announced_plan is not None:
                now_block = self.grid.block_of(now)
                rr = replan(self.cfg, self.weights, sc, self.announced_plan, now_block=now_block, trigger=kind)
                r = plan_day(self.cfg, self.weights, self.day, scenario=sc)
                out = result_to_dict(r)
                out["replan"] = {"changes_blocks": rr.changes_blocks, "changed_feeders": rr.changed_feeders,
                                 "now_block": rr.now_block, "lock_until": rr.lock_until, "note": rr.note,
                                 "status": rr.certified.status, "plan": {f: v.tolist() for f, v in rr.certified.plan.items()}}
            else:
                r = plan_day(self.cfg, self.weights, self.day, scenario=sc)
                out = result_to_dict(r)
            out["diff_vs_base"] = self._diff(self.base_result, out)
            out["scenario_kind"] = kind
            out["scenario_params"] = params
            out["forecast_source"] = self.base_result["forecast_source"] + (" · rescaled to the scenario's solar day" if kind == "cloud_ramp" else "")
            out["compute_seconds"] = round(time.time() - t0, 1)
            out["max_spells_allowed"] = int(getattr(r.certified, "max_spells_allowed", 1))
            self.scenario = sc
            self.current = out
            self.max_spells_allowed = out["max_spells_allowed"]
            self.cache[key] = out
            self.log.append(self._entry(kind, str(params), t0, r.certified.status))
            return out

    def request_slot(self, feeder: str, start: str) -> dict:
        self.ensure()
        with self.lock:
            t0 = time.time()
            sc = copy.deepcopy(self.scenario)
            opts = SolveOptions(max_spells=self.max_spells_allowed) if self.max_spells_allowed > 1 else None
            d = explain_request(self.cfg, self.weights, sc, feeder, self.grid.block_of(start), options=opts)
            out = {"feeder": d.feeder, "requested": d.requested_label, "accepted": d.accepted, "reason": d.reason,
                   "marathi": d.marathi, "blocking_families": d.blocking_families, "facts": d.facts,
                   "alternative": d.alternative_label, "cost_delta_inr": d.cost_delta_inr,
                   "plan": ({f: v.tolist() for f, v in d.plan.items()} if d.plan is not None else None)}
            self.log.append(self._entry("request_slot", f"{feeder} at {start}: {'granted' if d.accepted else 'refused'}", t0))
            return out

    def _diff(self, base: dict, new: dict) -> dict:
        bm, nm = base["plan"]["metrics"], new["plan"]["metrics"]
        keys = ["import_kwh", "import_nonsolar_kwh", "surplus_kwh", "solar_used_frac_of_pv", "pt2_max_loading_frac",
                "dt_max_hot_spot_c", "dt_exceedance_blocks", "dt_ageing_hours_total", "switchings", "import_kwh_per_ha"]
        return {k: {"base": bm.get(k), "new": nm.get(k)} for k in keys}

    def summary(self) -> dict:
        self.ensure()
        c = self.current
        return {"day": self.day.isoformat(), "status": c["certified"]["status"], "alert": c["certified"]["alert"],
                "metrics_baseline": c["baseline"]["metrics"], "metrics_plan": c["plan"]["metrics"],
                "forecast_source": c["forecast_source"], "weather_source": c["weather_source"],
                "scenario_kind": c.get("scenario_kind", "base"), "log": self.log[-25:]}

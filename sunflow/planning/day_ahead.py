"""Day-ahead planning: forecast band -> scenario -> baseline replay -> certify -> simulate -> messages."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Optional

import numpy as np

from ..core.config import SunflowConfig, Weights
from ..core.logging import get_logger
from ..core.timegrid import TimeGrid
from ..optimization.inputs import SolveOptions
from ..simulation import Scenario, SimResult, baseline_plan, scenario_from_era5_day, simulate
from ..verification import Certified, VerifySettings, certify, verify
from .explanations import explain_plan
from .messages import farmer_messages, operator_table

log = get_logger("sunflow.plan")


def forecast_band_for_day(cfg: SunflowConfig, day: date) -> Dict[str, object]:
    """P10/P50/P90 plant MW per block from the trained forecast-error model; falls back honestly if unavailable."""
    try:
        from ..ml.inference import ForecastModel, band_for_day
        if ForecastModel.available():
            band = band_for_day(cfg, day)
            return {"band": band, "source": "learned forecast-error model on archived day-ahead NWP (ICON+GFS) [MODELLED from PUBLIC data]"}
    except KeyError:
        pass
    except Exception as exc:  # model/data problem: never crash the planner
        log.warning(f"forecast model unavailable for {day}: {exc!r}")
    sc = scenario_from_era5_day(cfg, day, with_irrigation=False)
    pv = sc.pv_p50_mw
    return {"band": {"p10": 0.8 * pv, "p50": pv, "p90": np.minimum(1.1 * pv, cfg.plant.capacity_mw_ac)},
            "source": "NO forecast model: band derived from ERA5 actuals (+/-20%); not a forecast [LABELLED PROXY]"}


@dataclass
class DayPlanResult:
    day: date
    scenario: Scenario
    forecast_source: str
    baseline: SimResult
    baseline_report: object
    certified: Certified
    plan_sim: SimResult
    explanations: list = field(default_factory=list)
    messages: Dict[str, Dict[str, str]] = field(default_factory=dict)
    operator: list = field(default_factory=list)


def plan_day(cfg: SunflowConfig, weights: Weights, day: date, scenario: Optional[Scenario] = None,
             options: Optional[SolveOptions] = None, settings: Optional[VerifySettings] = None,
             grid: TimeGrid = TimeGrid()) -> DayPlanResult:
    if scenario is None:
        fb = forecast_band_for_day(cfg, day)
        scenario = scenario_from_era5_day(cfg, day, pv_band=fb["band"])
        source = fb["source"]
    else:
        source = scenario.weather_source
    settings = settings or VerifySettings.from_config(cfg)
    bl = baseline_plan(cfg)
    base_sim = simulate(bl, scenario, cfg)                     # expected conditions
    base_rep = verify(bl, scenario, cfg, settings)              # pessimistic check of today's practice
    cert = certify(cfg, scenario, weights, options, settings, baseline=bl)
    plan_sim = simulate(cert.plan, scenario, cfg, night_comp=cert.night_comp)
    expl = explain_plan(cert, cfg, base_sim, plan_sim, grid)
    msgs = farmer_messages(cert.plan, cfg, day, grid)
    op = operator_table(cert.plan, cfg, grid)
    return DayPlanResult(day=day, scenario=scenario, forecast_source=source, baseline=base_sim, baseline_report=base_rep,
                         certified=cert, plan_sim=plan_sim, explanations=expl, messages=msgs, operator=op)


def _sim_to_dict(sim: SimResult) -> dict:
    return {
        "blocks": sim.blocks,
        "pv_mw": sim.pv_mw.round(3).tolist(),
        "load_kw": sim.load_kw.round(1).tolist(),
        "import_kw": sim.import_kw.round(1).tolist(),
        "surplus_kw": sim.surplus_kw.round(1).tolist(),
        "feeder_kva": {f: v.round(1).tolist() for f, v in sim.feeder_kva.items()},
        "pt_kva": {p: v.round(1).tolist() for p, v in sim.pt_kva.items()},
        "pt_rating_kva": sim.pt_rating_kva,
        "dt_hot_spot_c": {d: [None if np.isnan(x) else round(float(x), 2) for x in v] for d, v in sim.dt_hot_spot_c.items()},
        "dt_rating_kva": sim.dt_rating_kva,
        "dt_feeder": sim.dt_feeder,
        "dt_ageing_hours": {d: round(v, 3) for d, v in sim.dt_ageing_hours.items()},
        "plan": {f: v.tolist() for f, v in sim.plan.items()},
        "metrics": {k: (round(float(v), 4) if isinstance(v, (int, float, np.floating, np.integer)) else v) for k, v in sim.metrics.items()},
        "per_feeder": sim.per_feeder,
        "violations": sim.violations,
    }


def result_to_dict(r: DayPlanResult) -> dict:
    sc = r.scenario
    return {
        "day": r.day.isoformat(),
        "forecast_source": r.forecast_source,
        "weather_source": sc.weather_source,
        "scenario": {
            "label": sc.label, "participation": sc.participation, "thermal_factor": sc.thermal_factor,
            "ambient_offset_c": sc.ambient_offset_c, "failed_dts": sorted(sc.failed_dts),
            "feeder_outages": sc.feeder_outages, "irrigation_required_blocks": sc.irrigation_required_blocks,
            "irrigation_urgency": sc.irrigation_urgency, "preferred_start": sc.preferred_start,
            "now_block": sc.now_block, "lock_until": sc.lock_until,
            "pv_p10_mw": (sc.pv_p10_mw.round(3).tolist() if sc.pv_p10_mw is not None else None),
            "pv_p50_mw": sc.pv_p50_mw.round(3).tolist(),
            "pv_p90_mw": (sc.pv_p90_mw.round(3).tolist() if sc.pv_p90_mw is not None else None),
            "ambient_c": sc.ambient_c.round(2).tolist(),
        },
        "baseline": _sim_to_dict(r.baseline),
        "baseline_verify": r.baseline_report.as_dict(),
        "certified": {
            "status": r.certified.status, "certified": r.certified.certified, "rung": r.certified.rung,
            "alert": r.certified.alert, "ladder": r.certified.ladder, "conflicts": r.certified.conflicts,
            "night_comp": r.certified.night_comp, "irrigation_deferred": r.certified.irrigation_deferred,
            "verify": (r.certified.report.as_dict() if r.certified.report else None),
            "solve": ({"status": r.certified.solve.status, "objective": r.certified.solve.objective,
                       "solve_time_s": round(r.certified.solve.solve_time_s, 2), "binding": r.certified.solve.binding,
                       "model_size": r.certified.solve.model_size, "gap": r.certified.solve.gap} if r.certified.solve else None),
        },
        "plan": _sim_to_dict(r.plan_sim),
        "explanations": r.explanations,
        "messages": r.messages,
        "operator": r.operator,
    }

"""FastAPI application: JSON API under /api plus the built frontend (frontend/dist) at /."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..core.paths import repo_root, results_dir
from ..scenarios import SCENARIO_KINDS, describe_kinds
from .schemas import ResetRequest, ScenarioRequest, SlotRequest
from .state import DemoState


def create_app() -> FastAPI:
    app = FastAPI(title="SUNFLOW API", version=__version__,
                  description="Constraint-verified switching planner for solarised agricultural feeders (Lamjana case).")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    import os
    state = DemoState.create(warm=os.environ.get("SUNFLOW_WARMUP", "1") != "0")
    app.state.demo = state

    @app.api_route("/api/health", methods=["GET", "HEAD"])
    def health():
        from ..ml.inference import ForecastModel
        return {"ok": True, "version": __version__, "forecast_model": ForecastModel.available(), "day": state.day.isoformat(),
                "warm_up": state.warm_status, "commit": (os.environ.get("RENDER_GIT_COMMIT") or "")[:7] or None}

    @app.get("/api/config")
    def config():
        cfg = state.cfg
        return {
            "site": cfg.site.model_dump(), "plant": cfg.plant.model_dump(), "sources": cfg.sources,
            "power_transformers": [p.model_dump() for p in cfg.power_transformers],
            "feeders": [{"name": f.name, "pt": f.pt, "published_slot": list(f.published_slot), "n_dts": f.n_dts,
                         "crop_group": f.crop_group, "rabi_crop_group": f.rabi_crop_group,
                         "installed_kva": round(cfg.feeder_installed_kva(f), 0),
                         "irrigated_ha": round(f.irrigated_ha, 1),
                         "dts": [d.model_dump() for d in f.dts]} for f in cfg.feeders],
            "rules": cfg.rules.model_dump(), "thermal": cfg.thermal.model_dump(), "verification": cfg.verification.model_dump(),
            "participation": cfg.participation.model_dump(), "pumps": cfg.pumps.model_dump(), "economics": cfg.economics.model_dump(),
            "provenance": {"PUBLIC": ["plant capacity", "PT ratings", "feeder-PT map", "published slots", "window", "8 h rule", "50 MW cap"],
                           "ASSUMED": ["DT counts and ratings", "pumps per DT", "pump kVA", "participation", "IEC constants", "crop mix", "soil"],
                           "SYNTHETIC": ["DT inventory expanded from the assumptions"]},
            "scenario_kinds": describe_kinds(),
        }

    @app.get("/api/days")
    def days():
        from ..simulation import available_days
        return {"days": [d.isoformat() for d in available_days() if d.year >= 2025]}

    @app.get("/api/demo/state")
    def demo_state():
        return state.summary()

    @app.get("/api/demo/current")
    def demo_current():
        state.ensure()
        return state.current

    @app.post("/api/demo/reset")
    def demo_reset(req: ResetRequest):
        d = None
        if req.day:
            try:
                d = date.fromisoformat(req.day)
            except ValueError:
                raise HTTPException(400, "day must be ISO format")
        try:
            return state.reset(d)
        except KeyError as exc:
            raise HTTPException(404, str(exc))

    @app.post("/api/plan/baseline")
    def plan_baseline():
        return state.baseline()

    @app.post("/api/plan/certify")
    def plan_certify():
        return state.certify()

    @app.post("/api/scenario/{kind}")
    def scenario(kind: str, req: ScenarioRequest):
        if kind not in SCENARIO_KINDS:
            raise HTTPException(404, f"unknown scenario {kind}; choose from {SCENARIO_KINDS}")
        try:
            return state.run_scenario(kind, req.params, req.intraday, req.now)
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/request-slot")
    def request_slot(req: SlotRequest):
        if req.feeder not in [f.name for f in state.cfg.feeders]:
            raise HTTPException(404, f"unknown feeder {req.feeder}")
        try:
            state.grid.block_of(req.start)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        return state.request_slot(req.feeder, req.start)

    @app.get("/api/explain/last")
    def explain_last():
        state.ensure()
        return {"explanations": state.current["explanations"], "certified": state.current["certified"]}

    @app.get("/api/forecast")
    def forecast(day: str | None = None):
        from ..planning import forecast_band_for_day
        d = date.fromisoformat(day) if day else state.day
        fb = forecast_band_for_day(state.cfg, d)
        meta_path = repo_root() / "models" / "forecast_meta.json"
        meta = json.load(open(meta_path, encoding="utf-8")) if meta_path.exists() else None
        return {"day": d.isoformat(), "source": fb["source"], "band": {k: v.round(3).tolist() for k, v in fb["band"].items()},
                "model": ({"shipped_model": meta["shipped_model"], "test_metrics": meta["metrics"]["test_vs_era5"],
                           "train_years": meta["train_years"], "test_years": meta["test_years"], "nwp_source": meta["nwp_source"]} if meta else None)}

    @app.get("/api/impact/summary")
    def impact_summary():
        p = results_dir() / "experiments" / "summary.json"
        sweep_p = results_dir() / "safety" / "sweep.json"
        sweep = None
        if sweep_p.exists():
            raw = json.load(open(sweep_p, encoding="utf-8"))
            sweep = {k: raw.get(k) for k in ("n", "seed", "status_counts", "certified_plans_with_violations", "median_solve_s", "p90_solve_s", "elapsed_s")}
        if not p.exists():
            return {"available": False, "note": "run scripts/run_experiments.py to generate results/experiments/summary.json", "sweep": sweep}
        return {"available": True, "sweep": sweep, **json.load(open(p, encoding="utf-8"))}

    dist = repo_root() / "frontend" / "dist"
    if dist.exists():
        from fastapi.responses import FileResponse
        if (dist / "assets").exists():
            app.mount("/assets", StaticFiles(directory=str(dist / "assets")), name="assets")
        index = dist / "index.html"

        @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)   # HEAD: platform health probes
        def root():
            return FileResponse(str(index))

        @app.api_route("/demo", methods=["GET", "HEAD"], include_in_schema=False)
        def demo():
            return FileResponse(str(index))

        @app.get("/{asset:path}", include_in_schema=False)
        def spa(asset: str):
            p = dist / asset
            if p.is_file():
                return FileResponse(str(p))
            return FileResponse(str(index))
    return app


app = create_app()

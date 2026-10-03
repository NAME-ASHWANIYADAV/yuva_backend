import pytest
from fastapi.testclient import TestClient

from sunflow.api import create_app


@pytest.fixture(scope="module")
def client():
    import os
    os.environ["SUNFLOW_WARMUP"] = "0"   # tests drive the state explicitly; no background warm-up thread
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_health_and_config(client):
    r = client.get("/api/health"); assert r.status_code == 200 and r.json()["ok"]
    c = client.get("/api/config").json()
    assert [f["name"] for f in c["feeders"]] == ["Kharosa", "Jawali", "Lamjana II", "Chalburga"]
    assert c["power_transformers"][1]["name"] == "PT-2"


def test_reset_baseline_certify(client):
    r = client.post("/api/demo/reset", json={"day": "2025-04-10"}); assert r.status_code == 200
    d = r.json()
    assert d["certified"]["status"] in ("CERTIFIED", "CERTIFIED_AFTER_TIGHTENING", "CERTIFIED_WITH_RELAXATION", "FALLBACK_BASELINE", "INFEASIBLE")
    b = client.post("/api/plan/baseline").json()
    assert b["baseline"]["metrics"]["load_kwh"] > 0
    s = client.get("/api/demo/state").json()
    assert s["day"] == "2025-04-10" and s["log"]


def test_scenarios_and_request(client):
    r = client.post("/api/scenario/cloud_ramp", json={}); assert r.status_code == 200
    d = r.json(); assert "diff_vs_base" in d and d["scenario_kind"] == "cloud_ramp"
    r = client.post("/api/scenario/dt_failure", json={}); assert r.status_code == 200
    assert r.json()["scenario"]["failed_dts"]
    r = client.post("/api/scenario/impossible", json={}); assert r.status_code == 200
    assert r.json()["certified"]["status"] == "INFEASIBLE"
    r = client.post("/api/scenario/not_a_scenario", json={}); assert r.status_code == 404
    r = client.post("/api/request-slot", json={"feeder": "Jawali", "start": "16:00"}); assert r.status_code == 200
    j = r.json(); assert j["accepted"] is False and j["reason"].startswith("Refused")
    r = client.post("/api/request-slot", json={"feeder": "Nope", "start": "07:30"}); assert r.status_code == 404
    r = client.post("/api/request-slot", json={"feeder": "Jawali", "start": "07:37"}); assert r.status_code == 400
    f = client.get("/api/forecast?day=2025-04-10").json(); assert "band" in f and len(f["band"]["p50"]) == 96


def test_precompute_leaves_visible_plan_alone(client):
    """Warm-up fills the cache without changing what viewers see; a later click serves the cached answer, and
    re-planning while a what-if is active keeps the what-if's identity."""
    from datetime import date
    st = client.app.state.demo
    st.reset(date(2025, 4, 11))
    base = st.current
    out = st.run_scenario("cloud_ramp", {}, activate=False)
    assert st.current is base and out["scenario_kind"] == "cloud_ramp"
    cur = client.get("/api/demo/current").json()
    assert cur["day"] == "2025-04-11" and cur.get("scenario_kind") in (None, "base")
    shown = client.post("/api/scenario/cloud_ramp", json={}).json()
    assert shown["scenario_kind"] == "cloud_ramp" and shown["compute_seconds"] == out["compute_seconds"]   # served from cache
    replanned = client.post("/api/plan/certify").json()
    assert replanned["scenario_kind"] == "cloud_ramp" and "diff_vs_base" in replanned


def test_health_reports_warm_up_and_answers_head(client):
    h = client.get("/api/health").json()
    assert h["warm_up"] == "off" and "commit" in h
    assert client.head("/api/health").status_code == 200

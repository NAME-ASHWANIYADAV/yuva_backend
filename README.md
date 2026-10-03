# SUNFLOW

**A constraint-verified day-ahead and intra-day switching planner for solarised agricultural feeders.**
Case: Lamjana 33/11 kV substation, Latur (MSEDCL, PM-KUSUM Component C / MSKVY 2.0). Built for Yuva Yodha 2026, Challenge 01, Sustainable Agriculture.

> Same eight hours. Better eight hours.

MSEDCL gives every agricultural feeder 8 hours of 3-phase supply a day on a monthly, manually executed timetable. Its own circular tells substation operators to switch feeders "depending upon availability of solar power, loading on Power Transformers and Ag feeders", but gives them no forecast, no transformer temperature, no crop-water deadline and no feasibility check. SUNFLOW produces, verifies and publishes that plan every evening, re-plans only when it must, explains itself from solver facts, and can never do worse than the published timetable because that timetable is its last fallback.

## What is where (layers)

| Layer | What it does | Code |
|---|---|---|
| **LEARNED** | Site-specific solar forecast-error band (P10/P50/P90) from archived day-ahead ICON/GFS vs ERA5 at Latur. LightGBM quantile regression with blocked split-conformal calibration. Trained 2023–2024, tested 2025. The only learned component; it never touches a safety rule. | `sunflow/ml` |
| **PHYSICS** | pvlib PVWatts plant model; IEC 60076-7 transformer top-oil/hot-spot/ageing (exact zero-order-hold discretisation, ±30 % band); FAO-56 soil-water bucket per feeder crop group; radial feeder/DT load model with start surge and DT-failure re-tap. | `sunflow/physics`, `sunflow/simulation` |
| **OPTIMISATION** | Exact MILP (Pyomo + HiGHS) in column form. Every admissible daily on/off pattern of a feeder is enumerated (07:30–17:30 window, outages, 8 h rule with the night-compensation clause, spells, off-time, locked announced blocks, forced start, irrigation minimum) and each candidate's distribution-transformer hot-spot trajectory is computed exactly with the IEC 60076-7 difference equations; a DT's temperature depends only on its own feeder's pattern, so patterns that would breach the limit never enter the model. The MILP picks one pattern per feeder under the coupling rules: per-PT rating (with cover cuts), switching cap, 30-min start separation, plant import/surplus, plus fairness and plan-stability costs. A seeded coordinate-descent heuristic supplies a feasible warm start. Nominal days solve in under a second; split-spell relaxations run to a 15 s limit with the optimality gap reported. | `sunflow/optimization` |
| **VERIFICATION** | Independent verifier (imports no optimiser code) replays every plan with the full nonlinear thermal model under pessimistic settings (P90 participation, ×1.3 thermal constants, +3 °C, P10 solar) and checks every rule. Ladder: nominal → split spells → feasibility focus → **published timetable + alert**. | `sunflow/verification` |
| **COMMUNICATION** | Operator table; Marathi/English farmer messages; slot requests answered by contrastive re-solve (yes / no + rule family + numbers / nearest feasible start); explanations from binding constraints and conflict attribution. | `sunflow/planning` |

The verifier and the optimiser share only the physics helpers; the verifier uses the nonlinear model with continuous load factors, the optimiser evaluates the zero-order-hold recursion per candidate pattern, which is exact because each DT's load takes one of three values per block (`tests/test_physics.py::test_linear_recursion_equals_nonlinear_for_two_state_load`). Two further guards sit in `certify()`: an infeasibility verdict from HiGHS is only believed after a second run with presolve off (HiGHS 1.15 presolve mis-declared one of our nominal models infeasible), and if the published timetable itself passes verification and is not more expensive under expected conditions, it is issued unchanged.

## Quick start
See [RUN_DEMO.md](RUN_DEMO.md). In short:
```bash
pip install -r requirements.txt && (cd frontend && npm install && npm run build)
python scripts/fetch_data.py && python scripts/train_forecast.py
python scripts/run_backend.py        # http://127.0.0.1:8000/demo
python -m pytest -q
```
Demo sequence: [DEMO_SCRIPT.md](DEMO_SCRIPT.md). Data provenance: [DATA_SOURCES.md](DATA_SOURCES.md). Claims register: [CLAIMS.md](CLAIMS.md). Architecture: [docs/architecture.md](docs/architecture.md).

## Baseline and the "never worse than today" mechanism
Baseline = MSEDCL's published Annexure-A slots for Lamjana (PT-1: Kharosa 09:30–17:30; PT-2: Jawali 09:00–17:00, Lamjana II 07:30–15:30, Chalburga 08:30–16:30), replayed through the same simulation under the same scenario. `certify()` solves, verifies, tightens on model mismatch, relaxes only what the circular allows (two spells, night compensation, deferred irrigation) and otherwise returns the published timetable with an alert and the verifier's report on it. Status values: `CERTIFIED`, `CERTIFIED_AFTER_TIGHTENING`, `CERTIFIED_WITH_RELAXATION`, `FALLBACK_BASELINE`, `INFEASIBLE` (with conflict attribution: which single rule family, when relaxed, restores feasibility).

Measured (this machine, `scripts/safety_sweep.py --n 1000`): over 1,000 seeded random stress scenarios (participation 0.5–1.0, thermal constants ±30 %, ambient −2 to +6 °C, random DT failures and feeder outages), 760 plans were certified with **zero** verifier violations, 228 scenarios were reported INFEASIBLE with conflict attribution (no plan fabricated), and 12 fell back to the published timetable within the 120 s budget; median certification 2.0 s, P90 23 s. Details in [CLAIMS.md](CLAIMS.md).

What "never worse" means, precisely: SUNFLOW never issues a plan that fails the independent verifier, and it never issues a plan that is more expensive (import incl. night hours, lost surplus, switching, night penalty) than the published timetable when that timetable itself passes the verifier. When the timetable fails the pessimistic check (28 % of experiment scenarios), the only rule-compliant plans can cost more import than today's non-compliant practice, typically because of split spells or night compensation; the experiments report that honestly rather than hiding it.

## What-if engine (all real backend computations)
cloud ramp (worst real midday ramp day of 2025 from ERA5) · heat wave (hottest 2025 day + offset) · DT failure (pumps re-tapped to neighbours) · feeder outage · everyone switches on (participation 1.0) · impossible case (outage + heat: must return INFEASIBLE) · farmer slot request (contrastive re-solve).

## Honesty
- Weather, archived forecasts and forecast errors are real (Open-Meteo ERA5/ICON/GFS, NASA POWER).
- Feeder, DT and pump inventory are **synthetic**, generated from stated assumptions calibrated to MSEDCL norms (`configs/lamjana.yaml`, every line tagged).
- Transformer temperatures are **modelled** (IEC 60076-7 with default constants; no DT at Latur is instrumented).
- No percentage in this repository is a measured field result. The M&V boundary for a pilot is the substation feeder meters that already exist.
- No LLM, no reinforcement learning, no surrogate model. The forecast band is the only learned quantity.

## Repository
```
configs/  sunflow/{core,data,ml,physics,simulation,optimization,verification,planning,scenarios,evaluation,api}
frontend/ (React + Vite + Recharts)  scripts/  tests/  docs/  results/ (generated)  models/ (generated)  data/ (generated)
```
Licence: MIT. Open-Meteo data is for non-commercial use under its terms.

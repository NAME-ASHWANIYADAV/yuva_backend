# SUNFLOW architecture

```mermaid
flowchart LR
  subgraph INPUTS[Inputs]
    W[Open-Meteo archives<br/>ERA5 · ICON/GFS day-ahead · daily ET0/rain<br/>PUBLIC]
    N[NASA POWER<br/>PUBLIC]
    R[MSEDCL circulars<br/>rules · slots · PT structure<br/>PUBLIC]
    C[configs/lamjana.yaml<br/>DT inventory · pumps · crops · IEC constants<br/>ASSUMED → SYNTHETIC]
  end
  subgraph LEARNED[LEARNED]
    F[Forecast-error model<br/>LightGBM quantile q10/q50/q90<br/>+ blocked conformal offsets]
  end
  subgraph PHYSICS[PHYSICS]
    PV[PV plant model<br/>pvlib PVWatts]
    TH[IEC 60076-7 thermal<br/>top-oil · hot-spot · ageing]
    IR[FAO-56 soil-water bucket<br/>requirement · urgency]
    FM[Feeder/DT load model<br/>surge participation · DT failure re-tap]
  end
  subgraph OPT[OPTIMISATION]
    M[MILP · Pyomo + HiGHS<br/>u f,t ∈ {0,1} · exact linear thermal recursion<br/>hours · window · spells · PT rating · cap<br/>separation · irrigation · locks · fairness · stability]
  end
  subgraph VER[VERIFICATION]
    V[Independent verifier<br/>nonlinear replay · pessimistic settings<br/>P90 participation · ×1.3 thermal · +3 °C · P10 solar]
    L[Fallback ladder<br/>nominal → split spells → feasibility focus<br/>→ published timetable + alert]
  end
  subgraph COMM[COMMUNICATION]
    O[Operator table + screen]
    FA[Farmer SMS/IVR text<br/>Marathi + English · request → yes/no/why/alternative]
    EX[Explanations<br/>binding constraints · conflict attribution · contrastive re-solve]
  end
  W --> F --> M
  W --> PV --> M
  W --> IR --> M
  R --> M
  C --> FM --> M
  C --> TH --> M
  M --> V --> L --> O
  L --> FA
  L --> EX
  V -. never imports .-> M
```

## Layer contract
| Layer | Decides | Never does |
|---|---|---|
| LEARNED | the width and centre of tomorrow's solar band | touch any safety rule |
| PHYSICS | transformer temperatures, PV output, crop water need | choose a schedule |
| OPTIMISATION | the switching plan (exact MILP) | approximate a hard rule |
| VERIFICATION | whether a plan is published | share code with the optimiser |
| COMMUNICATION | how operator and farmers see it | invent reasoning |

## Energy and money flows (Lamjana)
Plant 5 MW → 33/11 kV bus → PT-1 (5 MVA) → Kharosa; PT-2 (5 MVA) → Jawali, Lamjana II, Chalburga → DTs (63/100 kVA) → pumps. Import/export at the substation.
Value to the DISCOM: avoided grid import (priced at APPC in `configs/weights.yaml`), transformer ageing hours avoided, PM-KUSUM DISCOM incentive (₹6.6 lakh/MW/yr, PUBLIC), MERC demand-flexibility incentive (₹0.20 crore/MW, PUBLIC; held at zero). Farmers pay nothing; their currency is a predictable daytime slot.

## Key modelling property
When a feeder is on, each DT's load takes one of a small set of values (off / default participation / surge). The IEC 60076-7 forcing terms are therefore constants per state, so the top-oil and hot-spot recursions are exactly linear in the on/off binaries (see `sunflow/optimization/constraints.py`, `test_linear_recursion_equals_nonlinear_for_two_state_load`). The verifier uses the full nonlinear model with continuous load factors.

## Repository map
```
sunflow/
  configs/            lamjana.yaml (topology, rules, assumptions), weights.yaml (objective weights)
  sunflow/core        config models, time grid, paths, logging
  sunflow/data        Open-Meteo and NASA POWER clients, CSV cache
  sunflow/ml          features, training, metrics, evaluation plots, inference
  sunflow/physics     pv, transformer_thermal, irrigation
  sunflow/simulation  feeder model, truth engine, baseline, weather scenarios
  sunflow/optimization inputs, model, constraints, objective, solver
  sunflow/verification verifier, fallback ladder
  sunflow/planning    day-ahead, intra-day, explanations, messages
  sunflow/scenarios   real-event library, what-if engine, random scenarios
  sunflow/evaluation  experiments, ablations, plots
  sunflow/api         FastAPI app, demo state, schemas
  frontend/           React + Vite + Recharts dashboard and /demo
  scripts/            fetch_data, train_forecast, run_backend, run_experiments, safety_sweep
  tests/              unit, integration, property (safety sweep)
  results/            forecast, experiments, safety (generated)
```

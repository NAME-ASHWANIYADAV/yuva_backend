# CLAIMS

Every statement we make about SUNFLOW, with its label. **PUBLIC** = read from a public document or dataset; **MODELLED** = produced by our physics/optimisation/ML from public inputs and stated assumptions; **ASSUMED** = our assumption with range; **MEASURED** = measured on real equipment (none in this repository); **LITERATURE** = someone else's published result.

## Operating context (Lamjana, Latur)
| Claim | Label | Source |
|---|---|---|
| Each agricultural feeder gets 8 h of 3-phase supply per day; daytime, staggered 07:30–17:30 on solarised feeders; ≤ 50 MW switched per 15-minute block; switching is manual | PUBLIC | MSEDCL AgLM circular 31.07.2026 |
| Operators are instructed to switch "depending upon availability of solar power, loading on Power Transformers and Ag feeders"; hours lost to PT overload are compensated at night | PUBLIC | MSEDCL KUSUM-C Latur circular 06.08.2024, clauses 1 and 3 |
| Lamjana: 5 MW plant; PT-1 (5 MVA) → Kharosa 09:30–17:30; PT-2 (5 MVA) → Jawali 09:00–17:00, Lamjana II 07:30–15:30, Chalburga 08:30–16:30 | PUBLIC | Same circular, Annexure A |
| The three PT-2 feeders' published slots overlap 09:00–15:30 (6.5 h) | PUBLIC (derived) | Arithmetic on Annexure A |
| DT counts (18/24/28/24), 63/100 kVA mix, 9/15 pumps per DT, 5 HP pumps at 5.8 kVA, participation 0.8 expected / 0.9 P90 / 1.0 surge, 1.6 ha per pump, 25 m³/h discharge, application efficiency 0.6 | ASSUMED (SYNTHETIC inventory) | `configs/lamjana.yaml` |
| At participation 1.0 the three PT-2 feeders exceed 5 MVA when all three are on; at 0.9 they fit | MODELLED from ASSUMED inventory | `tests/test_core.py::test_dt_expansion`, `test_full_participation_day_is_structurally_infeasible_in_one_spell` |

## Learned component (forecast-error model)
| Claim | Label | Evidence |
|---|---|---|
| The forecast band is learned from archived day-ahead ICON and GFS forecasts (Open-Meteo Previous-Runs API) against ERA5 reanalysis GHI at the Latur coordinate; NASA POWER is a second proxy | PUBLIC inputs, MODELLED output | `sunflow/ml/features.py`; `models/forecast_meta.json` |
| Train 2023–2024 (3,910 daytime rows), test 2025 (4,106 rows), extra hold-out 2026 to date; no time overlap | MODELLED | `test_dataset_and_split_have_no_time_leakage` |
| On the 2025 test year the corrected P50 has MAE 62.6 W/m² vs 73.9 (raw ICON), 108.5 (raw GFS), 70.0 (persistence), 66.9 (linear correction); mean pinball 21.8 vs 23.5 (linear) and 28.0 (raw band) | MODELLED (against a reanalysis proxy) | `results/forecast/SUMMARY.md` |
| 80 % interval coverage on the test year is 0.75 after blocked split-conformal calibration (target 0.80) | MODELLED | same |
| LightGBM is shipped only because it beat the best baseline on pinball loss and its coverage fell within 0.70–0.90; otherwise the linear correction would be shipped | rule, pre-registered in code | `train_forecast_model.py::train_and_save` |
| ERA5 and NASA POWER disagree with each other; the floor is reported next to the skill | MODELLED | `forecast_meta.json` → `proxy_disagreement_era5_vs_nasa` |
| The learned component never sees the feeder simulator and never affects a safety constraint; it only sets the P10/P50/P90 band | design | `optimization/inputs.py` (band enters only the import/surplus terms) |
| Plant-level forecast error is not learned separately: GHI quantiles are passed through the deterministic PV model | limitation | `ml/inference.py` |

## Physics
| Claim | Label | Evidence |
|---|---|---|
| Transformer temperatures follow the IEC 60076-7 exponential-equation model with default ONAN distribution-transformer constants (Δθor 55 K, Δθhr 23 K, R 5, x 0.8, y 1.6, k11 1, k21 1, k22 2, τo 180 min, τw 4 min) and a 120 °C hot-spot limit | PUBLIC constants via open reproductions; MODELLED temperatures | `physics/transformer_thermal.py`; `test_steady_state_matches_illustrative_numbers` |
| Steady-state hot-spot at 40 °C ambient is ≈ 107 / 118 / 129 °C at 0.9 / 1.0 / 1.1 pu | MODELLED (illustrative) | same test |
| For a transformer whose load takes one of three values per block, the IEC recursion is exactly linear in the switching binaries (max abs. difference < 1e-9 against the nonlinear model) | MODELLED (proved by test) | `test_linear_recursion_equals_nonlinear_for_two_state_load` |
| No transformer at Latur is instrumented; constants carry a ±30 % band; "transformer failures avoided" is never claimed (IEC yields ageing, not failure probability; CEA attributes ~90 % of DT failures to moisture ingress) | limitation | README, DATA_SOURCES |
| Crop water need follows FAO-56 (single Kc, soil bucket, RAW/TAW) with Maharashtra-calibrated coefficients; kharif crops rotate to rabi chana/wheat on two feeders | PUBLIC method; ASSUMED crop assignment | `physics/irrigation.py`, `simulation/weather.py` |
| Supply hours are fixed at 8 h by rule; the irrigation model sets today's minimum blocks and an urgency that orders feeders. **We do not claim that staggering pumps saves water.** | design statement | `IrrigationPanel.jsx`, README |
| No AC power flow is run; loads aggregate radially; voltage is not modelled | limitation | `simulation/feeder_model.py` |

## Optimisation and verification
| Claim | Label | Evidence |
|---|---|---|
| The plan is an exact MILP in column form (Pyomo + HiGHS): 84 admissible patterns per feeder on a nominal day (336 binaries, ~330 constraints), 591 per feeder when split spells are allowed (1,407 when every night-compensation value is enumerated); nominal days solve in < 1 s on a laptop, split-spell rungs run to a 15 s limit and report their optimality gap (observed 0.6–9 %) | MODELLED (timings on this machine) | solver logs; ladder tables in the UI; `optimization/patterns.py` |
| Hard constraints: 8 h per feeder (equality, with the night-compensation clause capped at 2 h and used only in ≥ 1 h blocks), window, ≤ 1 spell (2 when relaxed, ≥ 2 h each, ≥ 1 h apart), per-PT kVA rating, switching cap, ≥ 30 min start separation, DT hot-spot ≤ 120 °C − margin, irrigation minimum, locked announced blocks | design | per-feeder rules and the hot-spot filter in `optimization/patterns.py`; coupling rules in `optimization/constraints.py` |
| A seeded coordinate-descent heuristic over the pattern sets finds a feasible assignment in < 0.5 s whenever the demo scenarios have one and is handed to HiGHS as a MIP start; the MILP then improves it (e.g. 60,947 → 60,455 ₹/day on the reference day) | MODELLED | `optimization/heuristic.py`; solver log `warm_start_objective` |
| HiGHS 1.15.1 presolve declared one of our nominal models infeasible although it solves to optimality with presolve off (and from an LP file); every infeasibility verdict is therefore re-run with presolve off before it is believed | observed, mitigated | `solver.py::solve_plan` |
| Two-spell patterns that also use night compensation are enumerated on a 30-min lattice and, by default, only at the 2 h cap; the feasibility rung enumerates every allowed value. Feasibility is exact; optimality is over the enumerated pattern set | limitation | `patterns.py::enumerate_patterns`, `SolveOptions.split_night_options` |
| Night-compensation hours are counted as 100 % grid import in every metric and cost, so a plan cannot look cheaper by moving supply to night | design | `truth_engine.simulate(night_comp=…)`, `fallback.economic_cost_inr` |
| If the published timetable itself passes verification and is not more expensive than the certified plan under expected conditions, the timetable is issued unchanged (status CERTIFIED, rung `baseline_guard`) | design | `fallback.certify` |
| Planner and verifier use the same participation: robust planning plans at max(scenario participation, P90 default) and the verifier replays at that value (full-participation stress is planned and verified at 1.0) | design (a 0.74-vs-0.9 mismatch was found and fixed while timing the sweep) | `optimization/inputs.py`, `truth_engine.simulate` |
| Any certification finishes within a 120 s budget or returns the published timetable with an alert | design | `fallback.certify(time_budget_s=120)` |
| An independent verifier (no import of optimiser code) replays every plan with the nonlinear thermal model under P90 participation, ×1.3 thermal constants, +3 °C ambient and P10 solar, and checks every rule | design | `verification/verifier.py`; `test_verifier_catches_*` |
| If no plan is certified, the published MSEDCL timetable is returned with an alert and the verifier's report on it; the system therefore cannot do worse than today's practice *within the model* | design (proved by tests) | `test_certify_falls_back_on_solver_error`, `test_certify_reports_infeasible_with_conflicts` |
| An intentionally impossible scenario returns INFEASIBLE with a list of which single rule family would restore feasibility; no plan is fabricated | design (proved by test) | `test_impossible_is_reported_not_faked` |
| Over N seeded random scenarios, every certified plan has zero verifier violations | MODELLED property | `tests/test_safety_sweep.py`; `results/safety/sweep.json` (1,000-scenario run; see Experiment results below) |

## What we do NOT claim
- Any measured field saving, any transformer failure avoided, any water saved, any farmer behaviour.
- That "AI" decides or guarantees anything: the forecast model sets a band; the optimiser decides; the verifier checks.
- That the Lamjana inventory is real: it is a synthetic calibration to MSEDCL norms, labelled on every screen.
- That MERC's ₹0.20 crore/MW demand-flexibility incentive is revenue: it accrues to the DISCOM and is held at zero in any economics.

## Experiment results (appended after `scripts/run_experiments.py` and `scripts/safety_sweep.py` complete)
See `results/experiments/SUMMARY.md` and `results/safety/sweep.json`. Numbers there are MODELLED on the synthetic feeder over real weather days; they are distributions, not single headline percentages.

<!-- generated-results:start -->

### Measured on this machine (generated by `scripts/append_results_to_claims.py`)

**Experiments** (`results/experiments/`): years [2025], 16 real weather days, 32 scenarios; status counts of the full system: `{'CERTIFIED': 25, 'FALLBACK_BASELINE': 3, 'INFEASIBLE': 3, 'CERTIFIED_WITH_RELAXATION': 1}`; certified plans with verifier violations: **0**.

| variant | import kWh/day, median (P10–P90) | solar used % of PV, median | PT-2 peak % of rating, median | max DT hot-spot °C, median | DT ageing h/day, median | verify-ok % | median solve s |
|---|---|---|---|---|---|---|---|
| published_timetable | 6,730 (2,187–20,880) | 96.3 | 91 | 76.6 | 32.0 | 72 | 0.0 |
| solar_only | 6,504 (2,561–20,880) | 97.1 | 91 | 76.6 | 32.0 | 81 | 0.8 |
| +transformer_limits | 6,504 (2,561–20,880) | 97.1 | 91 | 76.6 | 32.0 | 81 | 0.8 |
| +irrigation | 6,495 (2,561–20,880) | 97.1 | 91 | 76.6 | 32.0 | 84 | 0.7 |
| +forecast_band_robust | 6,531 (2,561–20,880) | 97.0 | 91 | 76.6 | 31.9 | 81 | 0.7 |
| +fairness | 6,516 (2,561–20,880) | 97.0 | 91 | 76.6 | 31.9 | 81 | 0.7 |
| sunflow_full | 6,516 (2,561–20,880) | 97.0 | 91 | 76.6 | 31.9 | 81 | 0.8 |

Paired per-scenario delta (sunflow_full − published timetable): import -80 kWh/day median (P10 -399, P90 0); DT ageing 0.00 h/day median (P10 -0.43, P90 0.01). A negative number means SUNFLOW is lower.

Distributions over scenarios, MODELLED on the synthetic Lamjana feeder with real weather; the published-timetable row is the same scenarios replayed with MSEDCL's Annexure-A slots (its verify-ok % shows how often today's practice would pass the pessimistic check). Import includes night-compensation energy. No single headline percentage is claimed.

**Safety sweep** (`results/safety/sweep.json`): 1000 seeded random scenarios (seed 7; participation 0.5–1.0, thermal ±30 %, ambient −2…+6 °C, random DT failures and feeder outages, random irrigation needs); status counts `{'CERTIFIED': 504, 'CERTIFIED_WITH_RELAXATION': 256, 'INFEASIBLE': 228, 'FALLBACK_BASELINE': 12}`; certified plans with verifier violations: **0**; median solve 2.0 s, P90 23.4 s; wall time 3,366 s.

<!-- generated-results:end -->

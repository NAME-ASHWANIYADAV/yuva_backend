# DEMO_SCRIPT (5 minutes)

Before starting: backend running, browser at http://127.0.0.1:8000/demo, day 2025-04-10 (default). Say once at the start: "Everything on screen is computed live by the backend; the feeder is modelled from MSEDCL norms, the weather and forecasts are real archives."

| Time | Click | What the audience sees | Say |
|---|---|---|---|
| 00:00 | **Replay published timetable** | Grey dashed load line and grey Gantt bars = MSEDCL's Annexure-A slots. PT-2 line near 99% when Lamjana II starts at 09:30 while Jawali and Chalburga are on. Verifier line shows whether today's practice passes the pessimistic check. | "This is the timetable MSEDCL publishes for Lamjana. Three feeders on one 5 MVA transformer overlap for six and a half hours." |
| 00:45 | **Certify SUNFLOW plan** | Status badge CERTIFIED. Green Gantt bars shift; metrics strip shows import, solar used, PT-2 peak, max hot-spot, ageing vs published. "Why this plan" lists the binding constraints. | "Same eight hours per feeder. The optimiser moved the starts so PT-2 never crosses its rating and the hottest transformers stay under the IEC limit, under pessimistic assumptions, and an independent verifier confirmed it." |
| 01:30 | **Cloud ramp** | Solar band collapses mid-afternoon (a real ERA5 day, the worst midday ramp of 2025). Plan re-solves; import counter rises honestly; badge stays CERTIFIED. Tick "intra-day" first to show locked blocks before 11:00. | "This is the worst real cloud day of 2025. The plan moves what it can; what it cannot save shows up as import, not as a hidden number." |
| 02:15 | **Fail a transformer** | One DT tile turns grey; its two neighbours heat up; the plan shifts that feeder; explanation names the binding DT class. | "A 63 kVA transformer burns out; its pumps are re-tapped to the neighbours. The plan protects the neighbours." |
| 03:00 | **Farmer request** Chalburga @ 07:30, then Jawali @ 09:30 | Decision card: GRANTED or REFUSED with the rule family (PT rating / hot-spot / separation), the PT numbers, the nearest feasible alternative, and the Marathi message. | "A farmer presses 1 on the IVR and asks for seven-thirty. The answer is yes, or no with the exact reason and the nearest slot that works." |
| 03:45 | **Impossible case** | Badge INFEASIBLE. Alert says no plan satisfies every hard rule; conflict attribution lists which single rule family would restore feasibility; the published timetable is shown as the fallback. | "Ask for the impossible and it says so. It never invents a plan; it falls back to today's timetable with an alert." |
| 04:30 | **Show impact** | Table of median (P10–P90) per-day metrics over real weather days: published vs ablation variants vs full; ablation shows what each component adds. | "Every number here is modelled, labelled, and reproducible with one script." |
| 05:00 | Close on the footer | Honesty footer. | "The physics and the optimiser are real; the load is modelled; the field test is at the feeder meters that already exist." |

Recovery: if any action errors, click **Reset day**. If the solver is slow (two-spell days can take 20–30 s), the spinner shows the action and the log records the real time taken.

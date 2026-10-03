# SUNFLOW frontend

Operator screen for SUNFLOW, the constraint-verified switching planner for solarised agricultural feeders
(Yuva Yodha 2026, Challenge 01). React 19 + Vite + Recharts; fonts self-hosted (Archivo, IBM Plex Sans, IBM Plex Mono).

The backend lives in [yuva_backend](https://github.com/NAME-ASHWANIYADAV/yuva_backend) (FastAPI, Pyomo + HiGHS). This
folder is also kept inside that repository as `frontend/`; the backend serves the production build from `frontend/dist`.

## Run
```bash
npm install
npm run dev          # http://localhost:5173, proxies /api to http://127.0.0.1:8000 (start the backend first)
npm run build        # writes dist/, which the backend serves at http://127.0.0.1:8000/
```
Hosted at https://yuva-frntend.vercel.app. On any `*.vercel.app` host (or any Vercel build) the screen calls the Render API at https://yuva-backend-2i5n.onrender.com; when the backend serves the build itself it uses the same origin. To point a build at a different backend, set `VITE_API_BASE=https://your-backend` before `npm run build` (in Vercel: Project Settings, Environment Variables). `vercel.json` adds the single-page-app fallback and long-lived caching for hashed assets.

## Screen
One shared time axis runs through solar band, feeder spells, power-transformer loading and transformer heat; the
operating window 07:30-17:30 is shaded in every row. The right rail holds every action: plan, six stress scenarios, a
farmer slot request, and the activity log with real backend timings. Every number on screen is computed live by the
backend; labels PUBLIC / SYNTHETIC / MODELLED / ASSUMED say where each one comes from.

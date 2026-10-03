# RUN_DEMO

Tested on Windows 11 with Python 3.12 and Node 22. Commands are run from the `sunflow/` repository root.

## 1. Install
```bash
python -m pip install -r requirements.txt
cd frontend && npm install && cd ..
```
(or `pip install -e .[dev]`)

## 2. Setup
```bash
copy .env.example .env        # optional; defaults are repo-relative
```

## 3. Download / load data (public, key-free; ~8 MB; cached in data/raw)
```bash
python scripts/fetch_data.py
```

## 4. Train the forecast-error model (about 1 minute; writes models/ and results/forecast/)
```bash
python scripts/train_forecast.py
```

## 5. Build the frontend (once, or after UI changes)
```bash
cd frontend && npm run build && cd ..
```

## 6. Run the backend (serves the API and the built UI)
```bash
python scripts/run_backend.py
```
Open http://127.0.0.1:8000/demo (operator console at http://127.0.0.1:8000/, API docs at http://127.0.0.1:8000/docs).

For UI development instead: `cd frontend && npm run dev` (proxies /api to port 8000).

## 7. Run tests
```bash
python -m pytest -q                       # unit + integration (~10 min, many MILP solves; 65 tests)
set SUNFLOW_SWEEP_N=1000 && python -m pytest tests/test_safety_sweep.py -q   # full property sweep via pytest (slow)
python scripts/safety_sweep.py --n 1000   # same sweep as a script; writes results/safety/sweep.json
```

## 8. Run experiments and ablations (writes results/experiments/; about 45 min on a laptop)
```bash
python scripts/run_experiments.py --days 16 --per-day 2 --time-limit 15
```
Then copy the measured numbers into the claims register (idempotent):
```bash
python scripts/append_results_to_claims.py
```

## 9. Launch the demo
See DEMO_SCRIPT.md for the 5-minute sequence. Every button calls the real backend; the first action after start takes a few seconds (plan + certification).

## One-command alternative (Docker)
```bash
docker build -t sunflow . && docker run -p 8000:8000 sunflow
```

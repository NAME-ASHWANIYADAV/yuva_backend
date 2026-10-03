# SUNFLOW: backend + built frontend in one image.
# Build:  docker build -t sunflow .
# Run:    docker run -p 8000:8000 sunflow      (then open http://localhost:8000/)
# The cached public weather data, the trained forecast model and the measured results are committed in the repo and
# copied into the image, so the build needs no internet beyond package installs. If they are missing (e.g. a trimmed
# checkout), the build fetches and trains them.
FROM node:22-slim AS web
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 SUNFLOW_HOST=0.0.0.0 SUNFLOW_PORT=8000
# libgomp: OpenMP runtime needed by LightGBM's shared library
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt
COPY configs/ configs/
COPY sunflow/ sunflow/
COPY scripts/ scripts/
COPY data/ data/
COPY models/ models/
COPY results/ results/
COPY --from=web /app/frontend/dist frontend/dist
RUN test -f models/forecast_lgbm_q50.txt || (python scripts/fetch_data.py && python scripts/train_forecast.py)
EXPOSE 8000
# Platforms such as Render or Railway inject PORT; the start script honours it.
CMD ["python", "scripts/run_backend.py"]

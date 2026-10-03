# SUNFLOW: backend + built frontend in one image.
# Build:  docker build -t sunflow .
# Run:    docker run -p 8000:8000 sunflow      (then open http://localhost:8000/demo)
# Data and the trained model are fetched/trained at build time (needs internet during build).
FROM node:22-slim AS web
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 SUNFLOW_HOST=0.0.0.0 SUNFLOW_PORT=8000
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt
COPY configs/ configs/
COPY sunflow/ sunflow/
COPY scripts/ scripts/
COPY --from=web /app/frontend/dist frontend/dist
RUN python scripts/fetch_data.py && python scripts/train_forecast.py
EXPOSE 8000
CMD ["python", "scripts/run_backend.py"]

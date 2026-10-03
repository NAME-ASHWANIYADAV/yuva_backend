"""Start the SUNFLOW API (and the built frontend if frontend/dist exists).  Run: python scripts/run_backend.py"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn  # noqa: E402

if __name__ == "__main__":
    host = os.environ.get("SUNFLOW_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT") or os.environ.get("SUNFLOW_PORT", "8000"))   # PORT: Render/Railway/Heroku convention
    uvicorn.run("sunflow.api.app:app", host=host, port=port, reload=False, log_level="info")

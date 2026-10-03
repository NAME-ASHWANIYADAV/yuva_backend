"""Structured logging setup (JSON-ish key=value lines)."""
from __future__ import annotations

import logging
import os
import sys


def get_logger(name: str = "sunflow") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    level = os.environ.get("SUNFLOW_LOG_LEVEL", "INFO").upper()
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s level=%(levelname)s module=%(name)s msg=%(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger

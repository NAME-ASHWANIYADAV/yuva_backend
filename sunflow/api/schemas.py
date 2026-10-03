from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel, Field


class ResetRequest(BaseModel):
    day: Optional[str] = Field(default=None, description="ISO date inside the ERA5 archive, e.g. 2025-04-10")


class ScenarioRequest(BaseModel):
    params: Dict[str, object] = Field(default_factory=dict)
    intraday: bool = False
    now: str = "11:00"


class SlotRequest(BaseModel):
    feeder: str
    start: str = Field(description="HH:MM on the 15-minute grid, e.g. 07:30")

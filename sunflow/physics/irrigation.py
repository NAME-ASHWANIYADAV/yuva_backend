"""FAO-56 single-crop-coefficient soil-water balance (PHYSICS) and pump-hour conversion.

Per feeder crop group: ETc = Kc(stage) * ET0; depletion grows by ETc and falls with effective rain and irrigation;
irrigation is required when depletion reaches the readily available water (RAW = p * TAW). The requirement in mm
is converted to pump-hours with the pump discharge and application efficiency (ASSUMED values in config).

What the model is used for: (1) a daily minimum number of supply blocks a feeder needs (capped by the 8-hour rule),
(2) an urgency score in [0, 1] that orders feeders when constraints force staggering, (3) a deficit flag when
supply cannot keep depletion below TAW. It is NOT used to claim water savings.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List

import numpy as np

from ..core.config import CropConfig, IrrigationConfig


@dataclass(frozen=True)
class CropCalendar:
    crop: CropConfig

    def kc(self, day: date) -> float:
        doy = day.timetuple().tm_yday
        start = self.crop.sowing_doy
        d = (doy - start) % 365
        ini, dev, mid, late = self.crop.stage_days
        if d < ini:
            return self.crop.kc_ini
        if d < ini + dev:
            return self.crop.kc_ini + (self.crop.kc_mid - self.crop.kc_ini) * (d - ini) / max(dev, 1)
        if d < ini + dev + mid:
            return self.crop.kc_mid
        if d < ini + dev + mid + late:
            return self.crop.kc_mid + (self.crop.kc_end - self.crop.kc_mid) * (d - ini - dev - mid) / max(late, 1)
        return 0.0  # no crop in the field

    def in_season(self, day: date) -> bool:
        return self.kc(day) > 0.0

    @property
    def taw_mm(self) -> float:
        return self.crop.taw_mm_per_m * self.crop.root_depth_m

    @property
    def raw_mm(self) -> float:
        return self.crop.depletion_p * self.taw_mm


@dataclass
class SoilBucket:
    calendar: CropCalendar
    settings: IrrigationConfig
    depletion_mm: float = 0.0
    history: List[dict] = field(default_factory=list)

    @classmethod
    def initial(cls, calendar: CropCalendar, settings: IrrigationConfig) -> "SoilBucket":
        return cls(calendar, settings, depletion_mm=settings.initial_depletion_frac * calendar.taw_mm)

    def step_day(self, day: date, et0_mm: float, rain_mm: float) -> dict:
        """Advance one day BEFORE irrigation. Returns requirement and urgency for the day."""
        kc = self.calendar.kc(day)
        etc = kc * max(float(et0_mm), 0.0)
        eff_rain = self.settings.effective_rain_fraction * max(float(rain_mm), 0.0)
        self.depletion_mm = float(np.clip(self.depletion_mm + etc - eff_rain, 0.0, self.calendar.taw_mm))
        raw = self.calendar.raw_mm
        # Requirement = water needed today to keep root-zone depletion at or below RAW after today's crop use
        # (continuous near the threshold instead of an all-or-nothing trigger). Zero when the soil is comfortably wet.
        requirement_mm = max(0.0, self.depletion_mm - raw + etc) if kc > 0 else 0.0
        urgency = float(np.clip(self.depletion_mm / raw, 0.0, 1.0)) if kc > 0 else 0.0
        critical = bool(kc > 0 and self.depletion_mm >= 0.95 * self.calendar.taw_mm)
        rec = {"date": day, "kc": kc, "etc_mm": etc, "eff_rain_mm": eff_rain, "depletion_mm": self.depletion_mm,
               "requirement_mm": requirement_mm, "urgency": urgency, "critical": critical}
        self.history.append(rec)
        return rec

    def apply_irrigation(self, mm: float) -> None:
        self.depletion_mm = float(np.clip(self.depletion_mm - max(mm, 0.0), 0.0, self.calendar.taw_mm))


def mm_to_pump_blocks(mm: float, area_ha: float, n_pumps: int, discharge_m3_per_h: float,
                      application_efficiency: float, dt_min: int = 15) -> int:
    if mm <= 0 or area_ha <= 0 or n_pumps <= 0:
        return 0
    volume_m3 = mm * area_ha * 10.0 / max(application_efficiency, 1e-6)
    hours = volume_m3 / (n_pumps * discharge_m3_per_h)
    return int(math.ceil(hours * 60.0 / dt_min))


def blocks_to_mm(blocks: int, area_ha: float, n_pumps: int, discharge_m3_per_h: float,
                 application_efficiency: float, dt_min: int = 15) -> float:
    if blocks <= 0 or area_ha <= 0:
        return 0.0
    hours = blocks * dt_min / 60.0
    volume_m3 = hours * n_pumps * discharge_m3_per_h * application_efficiency
    return volume_m3 / (area_ha * 10.0)


@dataclass
class FeederIrrigation:
    """Irrigation state for one feeder (all its DTs share a crop group)."""
    feeder: str
    bucket: SoilBucket
    area_ha: float
    n_pumps: int
    discharge_m3_per_h: float
    application_efficiency: float
    deficit_days: int = 0

    def plan_for_day(self, day: date, et0_mm: float, rain_mm: float, max_blocks: int = 32) -> Dict[str, float]:
        rec = self.bucket.step_day(day, et0_mm, rain_mm)
        needed_blocks = mm_to_pump_blocks(rec["requirement_mm"], self.area_ha, self.n_pumps,
                                          self.discharge_m3_per_h, self.application_efficiency)
        return {
            "required_blocks": int(min(needed_blocks, max_blocks)),
            "needed_blocks_total": int(needed_blocks),
            "urgency": float(rec["urgency"]),
            "critical": bool(rec["critical"]),
            "depletion_mm": float(rec["depletion_mm"]),
            "requirement_mm": float(rec["requirement_mm"]),
        }

    def deliver(self, blocks: int) -> float:
        mm = blocks_to_mm(blocks, self.area_ha, self.n_pumps, self.discharge_m3_per_h, self.application_efficiency)
        before = self.bucket.depletion_mm
        self.bucket.apply_irrigation(mm)
        if self.bucket.depletion_mm >= 0.95 * self.bucket.calendar.taw_mm:
            self.deficit_days += 1
        return before - self.bucket.depletion_mm

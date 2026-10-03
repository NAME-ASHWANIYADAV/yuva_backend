"""Typed configuration for a SUNFLOW site (loaded from configs/*.yaml).

The YAML carries provenance comments (PUBLIC / ASSUMED / SYNTHETIC). The loader expands the
per-feeder DT inventory deterministically from the assumed patterns so every DT has an id, a
rating, a pump count and an irrigated area.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml
from pydantic import BaseModel, Field, model_validator

from .paths import config_path, weights_path


class SiteConfig(BaseModel):
    name: str
    district: str
    state: str
    latitude: float
    longitude: float
    altitude_m: float = 0.0
    timezone: str = "Asia/Kolkata"


class PlantConfig(BaseModel):
    capacity_mw_ac: float
    dc_ac_ratio: float = 1.25
    tilt_deg: float = 18.0
    azimuth_deg: float = 180.0
    system_losses_frac: float = 0.14
    gamma_pdc_per_c: float = -0.004
    noct_c: float = 45.0


class PTConfig(BaseModel):
    name: str
    rating_kva: float


class DTConfig(BaseModel):
    id: str
    feeder: str
    rating_kva: float
    n_pumps: int
    irrigated_ha: float


class FeederConfig(BaseModel):
    name: str
    pt: str
    published_slot: Tuple[str, str]
    n_dts: int
    dt_kva_pattern: List[float]
    crop_group: str
    dts: List[DTConfig] = Field(default_factory=list)

    @property
    def installed_kva(self) -> float:
        return sum(d.n_pumps for d in self.dts)  # scaled by kva_per_pump in the feeder model

    @property
    def irrigated_ha(self) -> float:
        return sum(d.irrigated_ha for d in self.dts)


class PumpConfig(BaseModel):
    hp: float
    kva_per_pump: float
    power_factor: float
    discharge_m3_per_h: float


class ParticipationConfig(BaseModel):
    default: float = 0.8
    surge_blocks: int = 2
    surge_level: float = 1.0
    sweep_range: Tuple[float, float] = (0.5, 1.0)


class RulesConfig(BaseModel):
    window_start: str
    window_end: str
    min_blocks_per_feeder: int = 32
    max_spells: int = 1
    min_spell_blocks: int = 8
    min_off_blocks_between_spells: int = 4
    min_start_separation_blocks: int = 2
    substation_switch_cap_kva: float = 2500.0
    max_night_compensation_blocks: int = 8


class ThermalConfig(BaseModel):
    delta_theta_or_k: float = 55.0
    delta_theta_hr_k: float = 23.0
    ratio_r: float = 5.0
    x: float = 0.8
    y: float = 1.6
    k11: float = 1.0
    k21: float = 1.0
    k22: float = 2.0
    tau_o_min: float = 180.0
    tau_w_min: float = 4.0
    hot_spot_limit_c: float = 120.0
    ageing_reference_c: float = 98.0
    uncertainty_band: float = 0.30
    initial_top_oil_rise_k: float = 5.0


class VerificationConfig(BaseModel):
    ambient_offset_c: float = 3.0
    thermal_factor: float = 1.3
    participation: float = 1.0
    solar_quantile: str = "p10"


class EconomicsConfig(BaseModel):
    appc_inr_per_kwh: float = 4.5
    surplus_value_inr_per_kwh: float = 2.5
    dt_repair_inr: float = 250000.0


class CropConfig(BaseModel):
    kc_ini: float
    kc_mid: float
    kc_end: float
    stage_days: List[int]
    sowing_doy: int
    root_depth_m: float
    depletion_p: float
    taw_mm_per_m: float


class IrrigationConfig(BaseModel):
    application_efficiency: float = 0.6
    effective_rain_fraction: float = 0.8
    initial_depletion_frac: float = 0.3


class Weights(BaseModel):
    import_inr_per_kwh: float = 4.5
    surplus_inr_per_kwh: float = 2.0
    ageing_inr_per_deg_block: float = 2.0
    switching_inr_per_event: float = 200.0
    deviation_inr_per_block: float = 60.0
    urgency_inr_per_block: float = 15.0
    fairness_inr_per_block: float = 8.0
    night_comp_inr_per_block: float = 500.0
    thermal_margin_c: float = 4.0
    solar_quantile_for_import: str = "p10"
    solar_quantile_for_surplus: str = "p50"


class SunflowConfig(BaseModel):
    site: SiteConfig
    sources: Dict[str, str] = Field(default_factory=dict)
    plant: PlantConfig
    power_transformers: List[PTConfig]
    feeders: List[FeederConfig]
    distribution_transformers: dict
    pumps: PumpConfig
    participation: ParticipationConfig
    rules: RulesConfig
    thermal: ThermalConfig
    verification: VerificationConfig
    economics: EconomicsConfig
    crops: Dict[str, CropConfig]
    irrigation: IrrigationConfig

    @model_validator(mode="after")
    def _expand_dts(self) -> "SunflowConfig":
        pumps_per_dt = {str(k): int(v) for k, v in self.distribution_transformers["pumps_per_dt"].items()}
        ha_per_pump = float(self.distribution_transformers["irrigated_ha_per_pump"])
        pt_names = {p.name for p in self.power_transformers}
        for f in self.feeders:
            if f.pt not in pt_names:
                raise ValueError(f"feeder {f.name} references unknown PT {f.pt}")
            if f.crop_group not in self.crops:
                raise ValueError(f"feeder {f.name} references unknown crop group {f.crop_group}")
            if not f.dts:
                dts = []
                for i in range(f.n_dts):
                    kva = float(f.dt_kva_pattern[i % len(f.dt_kva_pattern)])
                    n_pumps = pumps_per_dt[str(int(kva))]
                    dts.append(DTConfig(
                        id=f"{f.name.replace(' ', '')}-DT{i + 1:02d}",
                        feeder=f.name,
                        rating_kva=kva,
                        n_pumps=n_pumps,
                        irrigated_ha=n_pumps * ha_per_pump,
                    ))
                f.dts = dts
        return self

    # convenience accessors
    def feeder(self, name: str) -> FeederConfig:
        for f in self.feeders:
            if f.name == name:
                return f
        raise KeyError(name)

    def pt(self, name: str) -> PTConfig:
        for p in self.power_transformers:
            if p.name == name:
                return p
        raise KeyError(name)

    def feeders_on_pt(self, pt_name: str) -> List[FeederConfig]:
        return [f for f in self.feeders if f.pt == pt_name]

    @property
    def all_dts(self) -> List[DTConfig]:
        return [d for f in self.feeders for d in f.dts]

    def dt_installed_kva(self, dt: DTConfig) -> float:
        return dt.n_pumps * self.pumps.kva_per_pump

    def feeder_installed_kva(self, f: FeederConfig) -> float:
        return sum(self.dt_installed_kva(d) for d in f.dts)


def load_config(path: Optional[Path | str] = None) -> SunflowConfig:
    p = Path(path) if path else config_path()
    with open(p, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return SunflowConfig(**raw)


def load_weights(path: Optional[Path | str] = None) -> Weights:
    p = Path(path) if path else weights_path()
    with open(p, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return Weights(**raw)

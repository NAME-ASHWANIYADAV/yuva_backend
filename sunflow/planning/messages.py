"""Operator table and farmer messages (Marathi + English templates). Messages are generated and logged, not sent."""
from __future__ import annotations

from datetime import date
from typing import Dict, List

from ..core.config import SunflowConfig
from ..core.timegrid import TimeGrid
from ..simulation.types import Plan, plan_spells

MARATHI_DAYS = {0: "सोमवार", 1: "मंगळवार", 2: "बुधवार", 3: "गुरुवार", 4: "शुक्रवार", 5: "शनिवार", 6: "रविवार"}


def _spell_text(spells, grid: TimeGrid, sep: str = " and ") -> str:
    return sep.join(f"{grid.label(a)}-{grid.label(b)}" for a, b in spells)


def farmer_messages(plan: Plan, cfg: SunflowConfig, day: date, grid: TimeGrid = TimeGrid()) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    for f in cfg.feeders:
        spells = plan_spells(plan[f.name])
        if not spells:
            en = f"{f.name} feeder: no daytime supply planned for {day.isoformat()}; night compensation applies. Press 1 to raise a request."
            mr = f"{f.name} फीडर: {day.strftime('%d-%m-%Y')} रोजी दिवसा वीज नियोजित नाही; रात्री भरपाई मिळेल. विनंतीसाठी 1 दाबा."
        else:
            en = (f"Namaskar. Tomorrow {day.strftime('%d-%m-%Y')} ({day.strftime('%A')}) the {f.name} feeder gets 3-phase supply "
                  f"{_spell_text(spells, grid)}. Please be at your pump then. Press 1 to request a different slot.")
            mr = (f"नमस्कार. उद्या {day.strftime('%d-%m-%Y')} ({MARATHI_DAYS[day.weekday()]}) {f.name} फीडरला थ्री-फेज वीज "
                  f"{_spell_text(spells, grid, ' आणि ')} या वेळेत मिळेल. कृपया त्या वेळी पंपाजवळ रहा. वेळ बदलायची असल्यास 1 दाबा.")
        out[f.name] = {"en": en, "mr": mr, "ivr_keypad": "1 = request different slot, 2 = repeat, 0 = operator"}
    return out


def operator_table(plan: Plan, cfg: SunflowConfig, grid: TimeGrid = TimeGrid()) -> List[dict]:
    rows = []
    for f in cfg.feeders:
        spells = plan_spells(plan[f.name])
        rows.append({"feeder": f.name, "pt": f.pt, "spells": [(grid.label(a), grid.label(b)) for a, b in spells],
                     "blocks": int(sum(b - a for a, b in spells)), "hours": sum(b - a for a, b in spells) * grid.dt_h,
                     "published": list(f.published_slot)})
    return rows

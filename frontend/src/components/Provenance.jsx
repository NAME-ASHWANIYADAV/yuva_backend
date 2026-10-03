import React from 'react'

export default function Provenance() {
  return (
    <footer className="prov">
      <div className="prov__in">
        <span className="eyebrow">Provenance</span>
        <span><span className="tagchip tagchip--public">PUBLIC</span> weather, archived day-ahead forecasts and forecast errors (Open-Meteo ERA5, ICON, GFS; NASA POWER), MSEDCL rules and Annexure-A slots</span>
        <span><span className="tagchip tagchip--synthetic">SYNTHETIC</span> feeder, transformer and pump inventory, generated from stated assumptions calibrated to MSEDCL norms</span>
        <span><span className="tagchip tagchip--modelled">MODELLED</span> transformer temperatures (IEC 60076-7), crop water (FAO-56), every percentage on this screen</span>
        <span><span className="tagchip tagchip--assumed">ASSUMED</span> thermal constants ±30 %, P90 participation 0.9, switching-cap share, crop calendar</span>
        <span>No learned component decides safety. Measurement boundary for any field trial: the substation feeder meters that already exist.</span>
      </div>
    </footer>
  )
}

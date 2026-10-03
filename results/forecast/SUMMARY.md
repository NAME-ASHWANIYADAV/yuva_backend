# Forecast-error model: evaluation (test year 2025, daytime hours)

NWP source: `nwp_day1_icon_seamless_latur`; truth proxy: ERA5 reanalysis GHI (proxy, not ground measurement); NASA POWER as second proxy; shipped model: **lgbm_quantile**

Train 2023-2024 (n=3910), test 2025 (n=4106); split-conformal offsets from blocked out-of-fold residuals: d10=-7.7, d50=9.6, d90=49.1 W/m2.

| model | MAE | RMSE | bias | pinball mean | coverage 80 | width |
|---|---|---|---|---|---|---|
| raw_icon | 73.9 | 115.3 | -20.3 | nan | nan | nan |
| raw_gfs | 108.5 | 165.3 | 6.5 | nan | nan | nan |
| raw_nwp_mean | 76.4 | 120.3 | -6.9 | nan | nan | nan |
| persistence | 70.0 | 125.1 | -0.0 | nan | nan | nan |
| linear_correction | 66.9 | 99.6 | -14.0 | 23.5 | 0.81 | 205 |
| raw_nwp_mean_band | 76.4 | 120.3 | -6.9 | 28.0 | 0.77 | 201 |
| lgbm_quantile_raw | 62.6 | 97.5 | -18.5 | 21.5 | 0.61 | 152 |
| lgbm_quantile | 62.6 | 97.0 | -10.2 | 21.8 | 0.75 | 197 |

## Same test rows scored against NASA POWER (second proxy)

| model | MAE | RMSE | pinball mean | coverage 80 |
|---|---|---|---|---|
| raw_icon | 131.4 | 157.3 | nan | nan |
| raw_gfs | 161.7 | 200.3 | nan | nan |
| raw_nwp_mean | 134.5 | 163.0 | nan | nan |
| persistence | 145.5 | 175.5 | nan | nan |
| linear_correction | 143.9 | 166.2 | 49.4 | 0.37 |
| raw_nwp_mean_band | 134.5 | 163.0 | 46.5 | 0.43 |
| lgbm_quantile_raw | 141.3 | 166.2 | 56.9 | 0.28 |
| lgbm_quantile | 144.9 | 169.8 | 56.7 | 0.35 |

Proxy disagreement floor (ERA5 vs NASA POWER on test rows): MAE 136.4 W/m2, bias -43.2 W/m2.

Extra hold-out 2026 (to date): corrected MAE 63.5, coverage 0.75.

All numbers are MODELLED against reanalysis/satellite proxies; the plant's own meter is not public.

Plots: raw_vs_corrected_scatter.png, sample_week_band.png, error_by_hour.png, error_by_month.png
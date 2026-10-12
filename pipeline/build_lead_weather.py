"""
Phase 2: weather available at the forecast date, not the whole season.

    python pipeline/build_lead_weather.py

Reads  data/processed/weather_daily.parquet
Writes data/processed/season_weather_lead.parquet   shape_id, year, window, lead, wl_<features>

For each fixed window (Kharif opens Jun 1, Rabi opens Nov 1 of `year`) and lead L in 60, 90, 120, the features use
only days from the window opening up to day L. This is the weather a forecast issued L days into the season could
actually have seen; it does not include any forecast of the rest of the season (no historical forecasts were
collected), so it is a conservative stand-in for the weather input of a live forecast.
`wl_rain_pre60` is rainfall in the 60 days before the window opens (soil moisture at sowing).
"""

import os
import warnings

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
OPEN = {"Kharif": (6, 1), "Rabi": (11, 1)}
LEADS = (60, 90, 120)
RAIN_DAY_MM, HOT_C = 2.5, 35.0


def max_run(b):
    if not b.any():
        return 0
    edges = np.flatnonzero(np.diff(np.concatenate(([0], b.astype(np.int8), [0]))))
    return int((edges[1::2] - edges[::2]).max())


def main():
    w = pd.read_parquet(os.path.join(PROC, "weather_daily.parquet")).sort_values(["shape_id", "date"])
    dates = pd.DatetimeIndex(sorted(w.date.unique()))
    ids = list(dict.fromkeys(w.shape_id))
    a = {c: w[c].to_numpy(dtype="float32").reshape(len(ids), len(dates)) for c in ["rain_mm", "tmax_c", "tmin_c", "rh_pct", "sw_mj"]}
    rows = []
    for y in range(dates[0].year, dates[-1].year + 1):
        for name, (m, d) in OPEN.items():
            s = pd.Timestamp(y, m, d)
            for lead in LEADS:
                e = s + pd.Timedelta(days=lead - 1)
                if e > dates[-1]:
                    continue
                i0, i1 = dates.get_loc(s), dates.get_loc(e) + 1
                r, tx, tn = a["rain_mm"][:, i0:i1], a["tmax_c"][:, i0:i1], a["tmin_c"][:, i0:i1]
                pre = a["rain_mm"][:, max(0, i0 - 60):i0]
                have = ~np.isnan(r).all(axis=1)
                dry = np.array([max_run(~(r[k] >= RAIN_DAY_MM) & ~np.isnan(r[k])) for k in range(len(ids))])
                rows.append(pd.DataFrame({
                    "shape_id": ids, "year": y, "window": name, "lead": lead,
                    "wl_rain_sum": np.where(have, np.nansum(r, axis=1), np.nan),
                    "wl_rain_days": np.where(have, np.nansum(r >= RAIN_DAY_MM, axis=1), np.nan),
                    "wl_rain_pre60": np.where(have & (pre.shape[1] > 0), np.nansum(pre, axis=1), np.nan),
                    "wl_dry_spell_max": np.where(have, dry, np.nan),
                    "wl_tmax_mean": np.nanmean(tx, axis=1), "wl_tmin_mean": np.nanmean(tn, axis=1),
                    "wl_hot_days": np.where(np.isnan(tx).all(axis=1), np.nan, np.nansum(tx >= HOT_C, axis=1)),
                    "wl_rh_mean": np.nanmean(a["rh_pct"][:, i0:i1], axis=1), "wl_sw_mean": np.nanmean(a["sw_mj"][:, i0:i1], axis=1)}))
    out = pd.concat(rows, ignore_index=True)
    out.to_parquet(os.path.join(PROC, "season_weather_lead.parquet"), index=False)
    print("rows %d | windows x leads present: %s" % (len(out), sorted(out.groupby(["window", "lead"]).size().index.tolist())))
    print(out.groupby(["window", "lead"])[["wl_rain_sum", "wl_tmax_mean", "wl_hot_days"]].mean().round(1).to_string())


if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    main()

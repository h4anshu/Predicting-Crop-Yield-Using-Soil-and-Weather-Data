"""
Phase 1A: weather over each district's own planting-to-harvest window, from the SAGE crop calendar.

    python pipeline/build_calendar_weather.py

Reads  data/raw/crop_calendar/<crop>.crop.calendar.fill.nc   (SAGE, Sacks et al. 2010, 0.5 deg, gunzipped)
       data/processed/weather_daily.parquet, district_geo.parquet
Writes data/processed/calendar_weather.parquet   shape_id, year, crop, kind, plant_doy, harvest_doy, c_<features>

The earlier windows were fixed national ones (Rabi = Nov-Mar). For wheat that ends before the April-May
harvest SAGE gives for most districts, so it left out the grain-filling heat. Here the window runs from the
district's mean planting day to its mean harvest day (wrapping into the next year when harvest falls
earlier in the calendar than planting):

  (Rice, main)    <- Rice          (Rice, second) <- Rice.2 (only where SAGE has it: West Bengal, Tamil Nadu, ...)
  (Wheat, main)   <- Wheat.Winter  (Maize, main)  <- Maize

SAGE values come from sparse observations spatially extrapolated to 0.5 degrees (its README calls the
extrapolated start/end dates the least certain), so they are district-scale approximations. A window
shorter than 60 or longer than 330 days is treated as invalid (NaN) rather than trusted. The extra
features are the last 30 days before harvest: mean tmax (c_tmax_last30) and days >= 35 C (c_hot_last30).
"""

import os

import numpy as np
import pandas as pd
import xarray as xr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAL = os.path.join(ROOT, "data", "raw", "crop_calendar")
PROC = os.path.join(ROOT, "data", "processed")
COMBOS = {("Rice", "main"): "Rice", ("Rice", "second"): "Rice.2", ("Wheat", "main"): "Wheat.Winter", ("Maize", "main"): "Maize"}
RAIN_DAY_MM, HOT_C = 2.5, 35.0
MIN_DAYS, MAX_DAYS = 60, 330


def max_run(b):
    """Longest run of True in a 1-D bool array."""
    if not b.any():
        return 0
    edges = np.flatnonzero(np.diff(np.concatenate(([0], b.astype(np.int8), [0]))))
    return int((edges[1::2] - edges[::2]).max())


def calendar_table(geo):
    """plant/harvest day of year at each district centroid, for every (crop, kind)."""
    rows = []
    for (crop, kind), name in COMBOS.items():
        ds = xr.open_dataset(os.path.join(CAL, "%s.crop.calendar.fill.nc" % name))
        for sid, r in geo.iterrows():
            s = ds.sel(latitude=float(r.lat), longitude=float(r.lon), method="nearest")
            rows.append((sid, crop, kind, float(s["plant"]), float(s["harvest"])))
    return pd.DataFrame(rows, columns=["shape_id", "crop", "kind", "plant_doy", "harvest_doy"])


def load_daily(geo):
    w = pd.read_parquet(os.path.join(PROC, "weather_daily.parquet")).sort_values(["shape_id", "date"])
    dates = pd.DatetimeIndex(sorted(w.date.unique()))
    ids = list(dict.fromkeys(w.shape_id))
    a = {c: w[c].to_numpy(dtype="float32").reshape(len(ids), len(dates)) for c in ["rain_mm", "tmax_c", "tmin_c", "rh_pct", "sw_mj"]}
    return ids, dates, a


def features(a, i, i0, i1):
    r, tx, tn = a["rain_mm"][i, i0:i1], a["tmax_c"][i, i0:i1], a["tmin_c"][i, i0:i1]
    pre = a["rain_mm"][i, max(0, i0 - 60):i0]
    last = tx[-30:]
    has_r, has_t = not np.isnan(r).all(), not np.isnan(tx).all()
    return {
        "c_rain_sum": np.nansum(r) if has_r else np.nan,
        "c_rain_days": np.nansum(r >= RAIN_DAY_MM) if has_r else np.nan,
        "c_rain_first30": np.nansum(r[:30]) if has_r else np.nan,
        "c_rain_pre60": np.nansum(pre) if has_r and len(pre) else np.nan,
        "c_dry_spell_max": max_run(~(r >= RAIN_DAY_MM) & ~np.isnan(r)) if has_r else np.nan,
        "c_tmax_mean": np.nanmean(tx) if has_t else np.nan,
        "c_tmin_mean": np.nanmean(tn) if not np.isnan(tn).all() else np.nan,
        "c_hot_days": np.nansum(tx >= HOT_C) if has_t else np.nan,
        "c_rh_mean": np.nanmean(a["rh_pct"][i, i0:i1]) if not np.isnan(a["rh_pct"][i, i0:i1]).all() else np.nan,
        "c_sw_mean": np.nanmean(a["sw_mj"][i, i0:i1]) if not np.isnan(a["sw_mj"][i, i0:i1]).all() else np.nan,
        "c_tmax_last30": np.nanmean(last) if has_t and not np.isnan(last).all() else np.nan,
        "c_hot_last30": np.nansum(last >= HOT_C) if has_t else np.nan,
    }


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    geo = pd.read_parquet(os.path.join(PROC, "district_geo.parquet"))
    geo = geo[geo.shape_id.notna()].drop_duplicates("shape_id").set_index("shape_id")
    ids, dates, a = load_daily(geo)
    pos = {s: k for k, s in enumerate(ids)}
    cal = calendar_table(geo.loc[ids])
    years = range(dates[0].year, dates[-1].year + 1)
    out = []
    for r in cal.itertuples():
        if np.isnan(r.plant_doy) or np.isnan(r.harvest_doy):
            continue
        span = int((r.harvest_doy - r.plant_doy) % 365)
        if not MIN_DAYS <= span <= MAX_DAYS:
            continue
        for y in years:
            start = pd.Timestamp(y, 1, 1) + pd.Timedelta(days=int(r.plant_doy) - 1)
            end = start + pd.Timedelta(days=span)
            if start < dates[0] or end > dates[-1]:
                continue
            i0, i1 = dates.get_loc(start), dates.get_loc(end) + 1
            out.append({"shape_id": r.shape_id, "year": y, "crop": r.crop, "kind": r.kind,
                        "plant_doy": r.plant_doy, "harvest_doy": r.harvest_doy, "window_days": span,
                        **features(a, pos[r.shape_id], i0, i1)})
    res = pd.DataFrame(out)
    res.to_parquet(os.path.join(PROC, "calendar_weather.parquet"), index=False)
    print("rows %d | districts %d" % (len(res), res.shape_id.nunique()))
    print(res.groupby(["crop", "kind"]).agg(districts=("shape_id", "nunique"), plant=("plant_doy", "median"),
                                              harvest=("harvest_doy", "median"), days=("window_days", "median")).to_string())

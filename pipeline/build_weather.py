"""
Phase 1A: district weather, from the raw IMD grids and NASA POWER files.

    python pipeline/build_weather.py [first_year] [last_year]     (default 1997 2024)

Reads  data/processed/district_geo.parquet, data/raw/boundaries/*ADM2*.geojson
       data/raw/imd/{rain,tmax,tmin}/<year>.*        (pipeline/fetch_imd.py)
       data/raw/power/*.json.gz                      (pipeline/fetch_power.py)
Writes data/processed/weather_daily.parquet    shape_id, date, rain_mm, tmax_c, tmin_c, rh_pct, sw_mj
       data/processed/season_weather.parquet   shape_id, year, window, <features>

District value = mean over the grid cells whose centre lies inside the polygon. Where none does
(common on the 1-degree temperature grid) the nearest cell with data is used. A year or variable
that has not been downloaded is NaN, never filled.

Season windows (year is the START year of the agricultural year, as in the yield panel):
  Kharif Jun-Oct | Rabi Nov-Mar(next year) | Summer Mar-Jun(next year) | Whole Year Jun-May(next year)
These are fixed calendar windows for the whole country. Real sowing dates vary by district and
year, so this is a first approximation (a ponytail: per-district crop calendars if it matters).
"""

import glob
import gzip
import json
import os
import sys

import imdlib as imd
import numpy as np
import pandas as pd
from scipy import sparse
from shapely import contains_xy
from shapely.geometry import shape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
PROC = os.path.join(ROOT, "data", "processed")
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from fetch_power import cell  # noqa: E402

WINDOWS = {"Kharif": ((6, 1), (10, 31), 0), "Rabi": ((11, 1), (3, 31), 1),
           "Summer": ((3, 1), (6, 30), 1), "Whole Year": ((6, 1), (5, 31), 1)}
RAIN_DAY_MM = 2.5
HOT_C = 35.0


def polygons(shape_ids):
    want = set(shape_ids)
    gj = json.load(open(os.path.join(RAW, "boundaries", "geoBoundaries-IND-ADM2_simplified.geojson"), encoding="utf-8"))
    return {f["properties"]["shapeID"]: shape(f["geometry"]) for f in gj["features"] if f["properties"]["shapeID"] in want}


def weights(polys, lat, lon, valid):
    """Sparse (n_shapes x n_cells) matrix of 1s for cells inside each polygon (nearest valid cell if none)."""
    LON, LAT = np.meshgrid(lon, lat)
    flat_lon, flat_lat, flat_ok = LON.ravel(), LAT.ravel(), valid.ravel()
    rows, cols = [], []
    for i, (sid, geom) in enumerate(polys.items()):
        inside = np.flatnonzero(contains_xy(geom, flat_lon, flat_lat) & flat_ok)
        if len(inside) == 0:
            c = geom.centroid
            d = np.where(flat_ok, (flat_lon - c.x) ** 2 + (flat_lat - c.y) ** 2, np.inf)
            inside = [int(np.argmin(d))]
        rows += [i] * len(inside)
        cols += list(inside)
    return sparse.csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(polys), flat_ok.size))


def load_year(var, year):
    if not glob.glob(os.path.join(RAW, "imd", var, "%d.*" % year)):
        return None
    ds = imd.open_data(var, year, year, "yearwise", os.path.join(RAW, "imd")).get_xarray()
    return ds[var].values.astype("float32"), ds.lat.values, ds.lon.values


def district_series(var, years, polys):
    """(n_shapes x n_days) daily district means for one IMD variable, NaN for undownloaded years."""
    out, W = [], None
    for y in years:
        got = load_year(var, y)
        ndays = 366 if pd.Timestamp(y, 12, 31).dayofyear == 366 else 365
        if got is None:
            out.append(np.full((len(polys), ndays), np.nan, dtype="float32"))
            continue
        X, lat, lon = got
        if W is None:
            W = weights(polys, lat, lon, ~np.isnan(X).all(axis=0))
        flat = X.reshape(X.shape[0], -1)
        ok = ~np.isnan(flat)
        num = W @ np.where(ok, flat, 0.0).T
        den = W @ ok.T.astype("float32")
        with np.errstate(invalid="ignore", divide="ignore"):
            out.append((num / den).astype("float32"))
        print("  %s %d done" % (var, y), flush=True)
    return np.concatenate(out, axis=1)


def power_series(shape_ids, geo, dates):
    """(n_shapes x n_days) RH and shortwave radiation from the POWER cell each district falls in."""
    rh = np.full((len(shape_ids), len(dates)), np.nan, dtype="float32")
    sw = rh.copy()
    pos = {d: i for i, d in enumerate(dates.strftime("%Y%m%d"))}
    cache = {}
    for i, sid in enumerate(shape_ids):
        r = geo.loc[sid]
        key = cell(float(r.lat), float(r.lon))
        if key not in cache:
            p = os.path.join(RAW, "power", "%s_%s.json.gz" % key)
            cache[key] = json.load(gzip.open(p, "rt", encoding="utf-8")) if os.path.exists(p) else None
        rec = cache[key]
        if rec is None:
            continue
        idx = [pos[d] for d in rec["dates"] if d in pos]
        sel = [j for j, d in enumerate(rec["dates"]) if d in pos]
        rh[i, idx] = np.array([np.nan if rec["RH2M"][j] is None else rec["RH2M"][j] for j in sel], dtype="float32")
        sw[i, idx] = np.array([np.nan if rec["ALLSKY_SFC_SW_DWN"][j] is None else rec["ALLSKY_SFC_SW_DWN"][j] for j in sel], dtype="float32")
    return rh, sw


def window_features(daily, dates, years):
    """Per (shape, year, window): season totals and stress indicators from the daily arrays."""
    rain, tmax, tmin, rh, sw = daily
    recs = []
    for y in years:
        for name, ((m0, d0), (m1, d1), carry) in WINDOWS.items():
            s, e = pd.Timestamp(y, m0, d0), pd.Timestamp(y + carry, m1, d1)
            if e > dates[-1]:
                continue
            i0, i1 = dates.get_loc(s), dates.get_loc(e) + 1
            r = rain[:, i0:i1]
            pre = rain[:, max(0, i0 - 60):i0]
            dry = r < RAIN_DAY_MM
            run = np.zeros(r.shape[0]); longest = np.zeros(r.shape[0])
            for t in range(r.shape[1]):
                run = (run + 1) * dry[:, t]
                longest = np.maximum(longest, run)
            first30 = r[:, :30]
            f = {
                "rain_sum": np.nansum(r, axis=1) * np.where(np.isnan(r).all(axis=1), np.nan, 1),
                "rain_days": np.nansum(r >= RAIN_DAY_MM, axis=1) * np.where(np.isnan(r).all(axis=1), np.nan, 1),
                "rain_first30": np.nansum(first30, axis=1),
                "rain_pre60": np.nansum(pre, axis=1) if pre.shape[1] else np.full(r.shape[0], np.nan),
                "dry_spell_max": longest,
                "tmax_mean": np.nanmean(tmax[:, i0:i1], axis=1),
                "tmin_mean": np.nanmean(tmin[:, i0:i1], axis=1),
                "hot_days": np.nansum(tmax[:, i0:i1] >= HOT_C, axis=1),
                "rh_mean": np.nanmean(rh[:, i0:i1], axis=1),
                "sw_mean": np.nanmean(sw[:, i0:i1], axis=1),
            }
            have = ~np.isnan(r).all(axis=1)
            for k in ("rain_first30", "rain_pre60", "dry_spell_max"):
                f[k] = np.where(have, f[k], np.nan)
            f["hot_days"] = np.where(np.isnan(tmax[:, i0:i1]).all(axis=1), np.nan, f["hot_days"])
            recs.append(pd.DataFrame({"year": y, "window": name, **f}))
    return recs


if __name__ == "__main__":
    import warnings
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 1997
    last = int(sys.argv[2]) if len(sys.argv) > 2 else 2024
    geo = pd.read_parquet(os.path.join(PROC, "district_geo.parquet"))
    geo = geo[geo.shape_id.notna()].drop_duplicates("shape_id").set_index("shape_id")
    polys = polygons(geo.index)
    shape_ids = list(polys)
    years = list(range(first, last + 1))
    dates = pd.date_range("%d-01-01" % first, "%d-12-31" % last)
    print("%d districts (polygons), %d days" % (len(shape_ids), len(dates)), flush=True)

    rain = district_series("rain", years, polys)
    tmax = district_series("tmax", years, polys)
    tmin = district_series("tmin", years, polys)
    rh, sw = power_series(shape_ids, geo, dates)

    daily = pd.DataFrame({"shape_id": np.repeat(shape_ids, len(dates)), "date": np.tile(dates, len(shape_ids)),
                          "rain_mm": rain.ravel(), "tmax_c": tmax.ravel(), "tmin_c": tmin.ravel(),
                          "rh_pct": rh.ravel(), "sw_mj": sw.ravel()})
    daily.to_parquet(os.path.join(PROC, "weather_daily.parquet"), index=False)

    parts = window_features((rain, tmax, tmin, rh, sw), dates, years)
    sw_df = pd.concat([p.assign(shape_id=shape_ids) for p in parts], ignore_index=True)
    sw_df.to_parquet(os.path.join(PROC, "season_weather.parquet"), index=False)
    print("\nweather_daily %d rows | season_weather %d rows" % (len(daily), len(sw_df)))
    print("share of season rows with each feature present:")
    print(sw_df.drop(columns=["shape_id", "year", "window"]).notna().mean().round(3).to_string())

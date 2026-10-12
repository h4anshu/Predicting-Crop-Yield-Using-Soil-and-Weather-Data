"""
The small files the service reads about the data, derived from the master table (22 MB, not shipped).

    python pipeline/export_serving.py

Reads  data/processed/master_panel.parquet, data/processed/master_reconciliation.json, data/master_columns.csv
Writes serving/state_view.parquet   state x crop x season x year: area, production, yield (= sum production / sum area)
       serving/crop_summary.json    per crop: records, spread of district yields, histogram
       serving/soil_climate.json    per state: Soil Health Card shares; per state-year: season-window weather
       serving/dataset_stats.json   what the master table holds, by column group

The dashboard, the trend, crop and soil pages and the model page all read these, so there is one dataset behind every
number the app shows. The model files are written by district_forecast.py.
"""

import json
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
SERVING = os.path.join(ROOT, "serving")
SPECIAL_UNITS = {"Coconut": "nuts/ha"}
SOIL = ["n", "p", "k", "oc"]
SOIL_OTHER = ["ph_acidic", "ph_alkaline", "ec_saline", "zn_deficient", "fe_deficient", "b_deficient", "s_deficient"]
SOURCES = ("DES district area-production-yield (APY, to 2022-23) and UPAG (2013-14 to 2024-25), the original state-level dataset, "
           "IMD gridded rain and temperature, NASA POWER, MODIS NDVI/EVI (Google Earth Engine), Soil Health Card, ICRISAT")


def dump(name, obj):
    with open(os.path.join(SERVING, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, separators=(",", ":"))


def state_view(m):
    """One row per state, crop, season and year. District rows are summed (production / area, not a mean of yields); the
    few series only the original state dataset holds are added as they are."""
    ok = m[m.valid_yield & ~m.flag_outlier]
    d = ok[ok.level == "district"].groupby(["state_name", "crop", "season", "year"]).agg(
        area=("area", "sum"), production=("production", "sum"), districts=("district_code", "nunique")).reset_index()
    d["yield"] = d["production"] / d["area"]
    s = ok[ok.level == "state"][["state_name", "crop", "season", "year", "area", "production", "yield"]].assign(districts=0)
    out = pd.concat([d, s], ignore_index=True)
    out[["area", "production", "yield"]] = out[["area", "production", "yield"]].astype("float32")
    out.to_parquet(os.path.join(SERVING, "state_view.parquet"), index=False, compression="zstd")
    return out


def crop_summary(m):
    d = m[(m.level == "district") & m.valid_yield & ~m.flag_outlier]
    out = {}
    for crop, g in d.groupby("crop"):
        y = g["yield"].to_numpy()
        lo, hi = np.quantile(y, [0.005, 0.995])
        counts, edges = np.histogram(np.clip(y, lo, hi), bins=40, range=(lo, hi))
        out[crop] = {"unit": SPECIAL_UNITS.get(crop, "tonnes/ha"), "records": int(len(g)), "districts": int(g.district_code.nunique()),
                     "states": int(g.state_name.nunique()), "year_min": int(g.year.min()), "year_max": int(g.year.max()),
                     "avg": round(float(g.production.sum() / g.area.sum()), 3), "p5": round(float(np.quantile(y, 0.05)), 3),
                     "p50": round(float(np.median(y)), 3), "p95": round(float(np.quantile(y, 0.95)), 3),
                     "histogram": {"edges": [round(float(e), 3) for e in edges], "counts": counts.tolist()}}
    dump("crop_summary.json", out)
    return out


def soil_climate(m):
    d = m[m.level == "district"]
    pc = d.drop_duplicates("district_code")                    # soil is one value per district
    cols = ["soil_%s_%s" % (a, b) for a in SOIL for b in ("low", "high")] + ["soil_" + c for c in SOIL_OTHER]
    soil = {}
    for st, g in pc.dropna(subset=["soil_samples"]).groupby("state_name"):
        w = g["soil_samples"].to_numpy()
        row = {c[5:]: round(float(np.average(g[c].fillna(g[c].mean()), weights=w)), 4) for c in cols if g[c].notna().any()}
        row["samples"] = int(w.sum())
        row["districts"] = int(len(g))
        soil[st] = row
    w = d.drop_duplicates(["district_code", "year", "season"])
    w = w[w.season.isin(["Kharif", "Rabi"])].dropna(subset=["wx_rain_sum"])
    weather = {}
    for st, g in w.groupby("state_name"):
        t = g.pivot_table(index="year", columns="season", values=["wx_rain_sum", "wx_tmax_mean", "wx_tmin_mean", "wx_rh_mean"], aggfunc="mean")
        weather[st] = {"years": [int(y) for y in t.index]}
        for var, name in (("wx_rain_sum", "rain"), ("wx_tmax_mean", "tmax"), ("wx_tmin_mean", "tmin"), ("wx_rh_mean", "rh")):
            for season in ("Kharif", "Rabi"):
                if (var, season) in t:
                    weather[st]["%s_%s" % (season.lower(), name)] = [None if np.isnan(v) else round(float(v), 1) for v in t[(var, season)]]
    out = {"soil": soil, "weather": weather,
           "granularity": {"soil": "one Soil Health Card profile per district (2023-25 samples), applied to every year",
                           "weather": "one value per district, season window and year (IMD gridded data); a state's figure is the mean of its districts",
                           "implication": "Both describe a district, not a field, and the soil is a recent snapshot: it says which nutrients are scarce, "
                                          "not how the soil changed over the years."}}
    dump("soil_climate.json", out)
    return out


def dataset_stats(m):
    d = m[m.level == "district"]
    cat = pd.read_csv(os.path.join(ROOT, "data", "master_columns.csv"))
    groups = []
    for g, c in cat.groupby("group", sort=False):
        cols = [x for x in c.column if x in d.columns]
        groups.append({"group": g, "columns": int(len(c)), "filled_pct": round(100 * float(d[cols].notna().mean().median()), 1)})
    with open(os.path.join(PROC, "master_reconciliation.json"), encoding="utf-8") as f:
        rec = json.load(f)
    out = {"rows": int(len(m)), "district_rows": int(len(d)), "state_only_rows": int((m.level == "state").sum()), "columns": int(m.shape[1]),
           "districts": int(d.district_code.nunique()), "states_uts": int(m.state_name.nunique()),
           "crops": int(d[d.valid_yield].crop.nunique()), "crops_listed": int(m.crop.nunique()),   # the rest: 17 with area but no usable yield, and the aggregate "Oilseeds total"
           "year_min": int(m.year.min()), "year_max": int(m.year.max()), "sources": SOURCES, "groups": groups,
           "state_vs_district": {"yield_within_2pct": rec["yield_within_2pct"], "yield_within_10pct": rec["yield_within_10pct"],
                                 "district_rows_with_state_values_pct": rec["district_rows_with_state_values_pct"]}}
    dump("dataset_stats.json", out)
    return out


def main():
    os.makedirs(SERVING, exist_ok=True)
    m = pd.read_parquet(os.path.join(PROC, "master_panel.parquet"))
    sv, cs, sc, st = state_view(m), crop_summary(m), soil_climate(m), dataset_stats(m)
    print("state_view %d rows | crop_summary %d crops | soil_climate %d states soil, %d states weather" % (len(sv), len(cs), len(sc["soil"]), len(sc["weather"])))
    print("dataset_stats:", {k: v for k, v in st.items() if k not in ("groups", "sources")})
    for name in ("state_view.parquet", "crop_summary.json", "soil_climate.json", "dataset_stats.json"):
        print("  %-22s %6.0f KB" % (name, os.path.getsize(os.path.join(SERVING, name)) / 1e3))


if __name__ == "__main__":
    main()

"""
One dataset: state -> district -> crop -> season -> year, with every source joined on.

    python pipeline/build_master_dataset.py

Reads  data/processed/district_yield.parquet, district_geo.parquet, season_weather.parquet, calendar_weather.parquet,
       season_ndvi.parquet, district_soil.parquet, district_static.parquet           (the pipeline/ outputs)
       master_dataset_enhanced.csv                                                   (the original state-level data)
Writes data/processed/master_panel.parquet   one row per (district, crop, season, year), plus state-only rows
       data/master_columns.csv               every column, its group and how often it is filled
       data/processed/master_reconciliation.json

Why it is one table and how the two levels meet
  * The original state-level dataset is, almost row for row, the sum of the district data it was built from (see
    master_reconciliation.json): 97.6% of its rows match a district sum and 93.4% agree on yield to within 2%. So the
    state level is attached to every district row as `state_*` columns instead of living in a separate dataset.
  * Rows the district data does not cover (Delhi, a few Goa and Chhattisgarh series) are kept as `level == "state"`
    rows, with the state-level values in area / production / yield, so nothing in the old dataset is lost.
  * The district data adds what the old one lacked: Rajasthan, the Union Territories, 22x the records, and 2021-2024.

Column groups (prefix): identifiers | area, production, yield (the value at this row's level) | state_* (the original
state-level columns, kept with their provenance caveats) | wx_* fixed-window season weather | cal_* weather over the
SAGE planting-to-harvest window | ndvi{60,90,120,full}_* satellite NDVI/EVI at a lead | soil_* Soil Health Card shares |
irr_*, cropping_intensity, fert_npk_per_ha ICRISAT attributes. Weather, NDVI, soil and ICRISAT columns exist only for
district rows with a boundary; they are NaN, never filled, elsewhere.

Provenance caveats that travel with the columns: state_soil_* are one unsourced constant per state; state_fertilizer
and state_pesticide are totals of unclear origin (the Kaggle crop-yield file); soil_* is a 2023-25 snapshot applied to
every year; calendar and NDVI windows are fixed national ones. See data/DATA_CARD.md.
"""

import json
import os
import re
import unicodedata

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
OUT = os.path.join(PROC, "master_panel.parquet")
OLD = os.path.join(ROOT, "master_dataset_enhanced.csv")
KEY = ["district_code", "crop", "season", "year"]
CAL_KIND = {("Rice", "Kharif"): "main", ("Rice", "Rabi"): "second", ("Rice", "Summer"): "second",
            ("Wheat", "Rabi"): "main", ("Maize", "Kharif"): "main"}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z]", "", s)


def read(name):
    return pd.read_parquet(os.path.join(PROC, name))


def state_block():
    """The original state-level data: crop-season-year rows, and per-state weather and soil."""
    old = pd.read_csv(OLD)
    for c in ("crop", "season", "state"):
        old[c] = old[c].str.strip()
    old["season"] = old["season"].replace({"Autumn": "Kharif", "Winter": "Kharif"})    # the district panel's season scheme
    cs = old.groupby(["state", "crop", "season", "year"], as_index=False).agg(
        state_area=("area", "sum"), state_production=("production", "sum"),
        state_fertilizer=("fertilizer", "sum"), state_pesticide=("pesticide", "sum"))
    cs["state_yield"] = cs["state_production"] / cs["state_area"]
    cs["sk"], cs["ck"] = cs["state"].map(norm), cs["crop"].map(norm)
    wx = old.drop_duplicates(["state", "year"])[["state", "year", "avg_temp_c", "total_rainfall_mm", "avg_humidity_percent"]]
    wx = wx.rename(columns={"avg_temp_c": "state_temp_c", "total_rainfall_mm": "state_rainfall_mm", "avg_humidity_percent": "state_humidity_pct"})
    wx["sk"] = wx["state"].map(norm)
    soil = old.drop_duplicates("state")[["state", "N", "P", "K", "pH"]].rename(
        columns={"N": "state_soil_N", "P": "state_soil_P", "K": "state_soil_K", "pH": "state_soil_pH"})
    soil["sk"] = soil["state"].map(norm)
    return cs, wx.drop(columns="state"), soil.drop(columns="state")


def build():
    P = read("district_yield.parquet")
    P["level"] = "district"
    P["sk"], P["ck"] = P["state_name"].map(norm), P["crop"].map(norm)
    geo = read("district_geo.parquet")[["district_code", "shape_id", "lon", "lat", "match_type"]].rename(columns={"match_type": "geo_match"})
    P = P.merge(geo, on="district_code", how="left")
    n_district = len(P)

    cs, wx, soil = state_block()
    # state-level crop-season values attach to every district row of that state, crop, season, year
    # `state` and `crop` are dropped from the right side: a same-named column would split the panel's own `crop` into crop_x / crop_y
    P = P.merge(cs.drop(columns=["state", "crop"]), on=["sk", "ck", "season", "year"], how="left")

    # old rows the district data does not cover stay as state-level rows
    have = set(zip(P.sk, P.ck, P.season, P.year))
    extra = cs[[k not in have for k in zip(cs.sk, cs.ck, cs.season, cs.year)]].copy()
    extra = extra.rename(columns={"state": "state_name"})
    # use the panel's spelling where the same state / crop exists there ("Castor seed" -> "Castor Seed"), so one entity has one label
    canon_state = P.drop_duplicates("sk").set_index("sk")["state_name"]
    canon_crop = P.drop_duplicates("ck").set_index("ck")["crop"]
    extra["state_name"] = extra["sk"].map(canon_state).fillna(extra["state_name"])
    extra["crop"] = extra["ck"].map(canon_crop).fillna(extra["crop"])
    extra["level"], extra["source"] = "state", "STATE_LEGACY"
    extra["area"], extra["production"], extra["yield"] = extra["state_area"], extra["state_production"], extra["state_yield"]
    extra["valid_yield"] = extra["yield"].notna() & (extra["yield"] > 0)
    extra["flag_outlier"] = False
    extra["agri_year"] = extra["year"].astype(str) + "-" + (extra["year"] + 1).astype(str)
    P = pd.concat([P, extra], ignore_index=True)

    P = P.merge(wx, on=["sk", "year"], how="left").merge(soil, on="sk", how="left")

    # ---- district-only blocks ----
    sw = read("season_weather.parquet").rename(columns={"window": "season"})
    sw.columns = [c if c in ("shape_id", "year", "season") else "wx_" + c for c in sw.columns]
    P = P.merge(sw, on=["shape_id", "year", "season"], how="left")

    P["kind"] = [CAL_KIND.get(k) for k in zip(P.crop, P.season)]
    cw = read("calendar_weather.parquet").drop(columns=["plant_doy", "harvest_doy", "window_days"])
    cw.columns = [c if c in ("shape_id", "year", "crop", "kind") else "cal_" + c[2:] for c in cw.columns]
    P = P.merge(cw, on=["shape_id", "year", "crop", "kind"], how="left").drop(columns="kind")

    nd = read("season_ndvi.parquet")
    for lead in (60, 90, 120, 999):
        part = nd[nd.lead == lead].drop(columns=["lead", "n_comp"]).rename(columns={"window": "season"})
        tag = "ndvi%s_" % ("full" if lead == 999 else lead)
        part.columns = [c if c in ("shape_id", "year", "season") else tag + c.replace("ndvi_", "").replace("evi_", "evi_") for c in part.columns]
        P = P.merge(part, on=["shape_id", "year", "season"], how="left")

    P = P.merge(read("district_soil.parquet").drop(columns=["state_name", "district_name"]), on="district_code", how="left")
    P = P.merge(read("district_static.parquet"), on="district_code", how="left")

    P = P.drop(columns=["sk", "ck"])
    for c in P.columns:                                  # features as float32, the file is large otherwise
        if P[c].dtype == "float64" and c not in ("yield", "area", "production", "lon", "lat", "state_yield"):
            P[c] = P[c].astype("float32")
    return P, n_district


def group_of(c):
    if c in ("level", "state_code", "state_name", "district_code", "district_name", "shape_id", "lon", "lat", "geo_match", "crop", "season", "year", "agri_year", "source"):
        return "identifier"
    if c in ("area", "production", "yield", "valid_yield", "flag_outlier"):
        return "yield (value at this row's level)"
    for pre, g in (("state_", "state-level (original dataset)"), ("wx_", "weather, fixed season window"), ("cal_", "weather, planting-to-harvest window"),
                   ("ndvi", "satellite NDVI/EVI"), ("soil_", "soil (Soil Health Card)"), ("irr_", "ICRISAT attributes"), ("icr_", "ICRISAT attributes")):
        if c.startswith(pre):
            return g
    return "ICRISAT attributes" if c in ("cropping_intensity", "fert_npk_per_ha") else "other"


def main():
    P, n_district = build()
    d = P[P.level == "district"]
    for c in ("level", "state_name", "crop", "season", "year"):
        assert P[c].notna().all(), "%s has gaps: a join clobbered it" % c
    assert not d.duplicated(KEY).any(), "duplicate district keys: a join multiplied rows"
    assert len(d) == n_district, "a join changed the number of district rows"
    P.to_parquet(OUT, index=False, compression="zstd")

    cat = pd.DataFrame({"column": P.columns, "group": [group_of(c) for c in P.columns], "dtype": [str(t) for t in P.dtypes],
                        "filled_pct": [round(100 * float(P[c].notna().mean()), 1) for c in P.columns]})
    cat.to_csv(os.path.join(ROOT, "data", "master_columns.csv"), index=False)

    # reconciliation of the two levels, on rows where both exist
    both = d[d.state_yield.notna() & d["yield"].notna() & d.valid_yield]
    agg = both.groupby(["state_name", "crop", "season", "year"]).agg(a=("area", "sum"), p=("production", "sum"), sy=("state_yield", "first")).reset_index()
    ratio = (agg.p / agg.a) / agg.sy
    rec = {"district_rows": int(len(d)), "state_only_rows": int((P.level == "state").sum()),
           "district_rows_with_state_values_pct": round(100 * float(d.state_yield.notna().mean()), 1),
           "compared_state_keys": int(len(agg)),
           "yield_within_2pct": round(100 * float((abs(ratio - 1) < 0.02).mean()), 1),
           "yield_within_10pct": round(100 * float((abs(ratio - 1) < 0.10).mean()), 1),
           "median_ratio_district_over_state": round(float(ratio.median()), 3)}
    with open(os.path.join(PROC, "master_reconciliation.json"), "w", encoding="utf-8") as f:
        json.dump(rec, f, indent=2)

    print("master_panel: %d rows (%d district + %d state-only) x %d columns | %.0f MB" % (
        len(P), len(d), rec["state_only_rows"], P.shape[1], os.path.getsize(OUT) / 1e6))
    print("states %d | districts %d | crops %d | years %d-%d" % (P.state_name.nunique(), d.district_code.nunique(), P.crop.nunique(), P.year.min(), P.year.max()))
    print("\ncolumns by group, and how much of the district rows each group fills:")
    for g, c in cat.groupby("group"):
        cols = [x for x in c.column if x in d.columns]
        print("  %-38s %3d columns | median filled %5.1f%% (district rows)" % (g, len(c), 100 * float(d[cols].notna().mean().median()) if cols else float("nan")))
    print("\nreconciliation:", rec)


if __name__ == "__main__":
    main()

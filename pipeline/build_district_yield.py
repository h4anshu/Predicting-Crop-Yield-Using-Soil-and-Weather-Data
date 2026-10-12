"""
Phase 1A, step 1: one district x crop x season x year yield panel from the raw DES files.

    python pipeline/build_district_yield.py        (needs requirements-data.txt)

Reads  data/raw/des_apy_1997_2023.csv   DES APY via India Data Portal, 1997-98 .. 2022-23
       data/raw/upag_2013_2025.csv      DES via UPAG, 2013-14 .. 2024-25 (2024-25 is partial)
Writes data/processed/district_yield.parquet

The two sources come from the same Directorate of Economics & Statistics and agree to
within 0.1% on 98.8% of overlapping staple rows, but they label things differently, so
the rules below are explicit rather than a bare concat:

  1. year is the START year of the agricultural year (1997-98 -> 1997), matching the
     `year` column of the existing state-level dataset.
  2. APY season "Total" is the sum of the other seasons and is dropped (keeping it
     double-counts). Autumn and Winter (Assam/WB/Odisha rice) are folded into Kharif and
     summed, which is how UPAG reports them; area then matches UPAG within 1% on 97.5%
     of rows. "Whole Year" is kept as its own label.
  3. A (year, district, crop) that APY has under ANY season is taken from APY only. UPAG
     rows are added only where APY has nothing for that district-crop-year. Joining on
     season as well would double-count crops the two sources file under different seasons.
  4. UPAG crop names are mapped to APY's where they are the same crop. Cotton is NOT mapped
     to Cotton(Lint): UPAG converts bales to tonnes at 170 kg and APY's basis is unconfirmed.
  5. Yield is recomputed as production / area (t/ha) where both are positive; the reported
     yield agrees within 1% on 99.8% of rows, and a recomputed one is the same everywhere.
     Otherwise it is NaN, never 0: a reported 0 is a missing report, not a harvest of nothing.
  6. Implausible yields are FLAGGED, not deleted (APY has a maize row at 1,494 t/ha):
     flag_outlier = yield > 3 x the crop's 99th percentile.
"""

import os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "processed", "district_yield.parquet")

KEY = ["district_code", "crop", "season", "year"]
APY_SEASON = {"Kharif": "Kharif", "Autumn": "Kharif", "Winter": "Kharif",
              "Rabi": "Rabi", "Summer": "Summer", "Whole Year": "Whole Year"}
UPAG_CROP = {"Castorseed": "Castor Seed", "Guarseed": "Guar Seed", "Lentil": "Masoor",
             "Moong": "Moong(Green Gram)", "Nigerseed": "Niger Seed",
             "Rapeseed & Mustard": "Rapeseed &Mustard", "Sannhemp": "Sannhamp",
             "Soybean": "Soyabean", "Tur": "Arhar/Tur"}
COLS = ["agri_year", "state_code", "state_name", "district_code", "district_name",
        "crop", "season", "area", "production", "source"]


def load_apy():
    d = pd.read_csv(os.path.join(RAW, "des_apy_1997_2023.csv"))
    d = d[d["season"] != "Total"].copy()
    d["season"] = d["season"].map(APY_SEASON)
    d["agri_year"], d["crop"], d["source"] = d["year"], d["crop_name"].str.strip(), "APY"
    return d[COLS]


def load_upag():
    d = pd.read_csv(os.path.join(RAW, "upag_2013_2025.csv"))
    n0 = len(d)
    d = d.dropna(subset=["district_code"]).copy()
    print("UPAG: dropped %d rows with no district code" % (n0 - len(d)))
    d["district_code"] = d["district_code"].astype(int)
    d["agri_year"], d["source"] = d["year"], "UPAG"
    d["crop"] = d["crop_name"].str.strip().replace(UPAG_CROP)
    return d[COLS]


def build():
    apy, upag = load_apy(), load_upag()
    have = apy[["agri_year", "district_code", "crop"]].drop_duplicates()
    extra = upag.merge(have, on=["agri_year", "district_code", "crop"], how="left", indicator=True)
    extra = extra[extra["_merge"] == "left_only"].drop(columns="_merge")
    print("APY rows %d | UPAG rows %d | UPAG rows APY has nothing for: %d" % (len(apy), len(upag), len(extra)))

    d = pd.concat([apy, extra], ignore_index=True)
    d["year"] = d["agri_year"].str[:4].astype(int)

    # Autumn + Winter + Kharif collapse onto one Kharif row; NaN stays NaN if every part is NaN
    g = d.groupby(KEY, as_index=False).agg(
        agri_year=("agri_year", "first"), state_code=("state_code", "first"),
        area=("area", lambda s: s.sum(min_count=1)),
        production=("production", lambda s: s.sum(min_count=1)),
        source=("source", "first"))
    # latest recorded name for each code
    names = d.sort_values("year").groupby("district_code")[["district_name", "state_name"]].last()
    g = g.join(names, on="district_code")

    ok = (g["area"] > 0) & (g["production"] > 0)
    g["yield"] = np.where(ok, g["production"] / g["area"], np.nan)
    g["valid_yield"] = ok

    p99 = g[ok].groupby("crop")["yield"].agg(lambda s: s.quantile(0.99) if len(s) >= 200 else np.nan)
    g["flag_outlier"] = g["yield"] > 3 * g["crop"].map(p99)
    return g[["agri_year", "year", "state_code", "state_name", "district_code", "district_name",
              "crop", "season", "area", "production", "yield", "valid_yield", "flag_outlier", "source"]
             ].sort_values(KEY).reset_index(drop=True)


def checks(g):
    assert not g.duplicated(KEY).any(), "duplicate district-crop-season-year keys"
    assert g["year"].between(1997, 2024).all()
    assert (g.loc[g.valid_yield, "yield"] > 0).all() and g.loc[~g.valid_yield, "yield"].isna().all()
    assert g.groupby("district_code")["state_code"].nunique().max() == 1, "a district code spans two states"


def report(g):
    print("\nrows %d | districts %d | crops %d | years %d-%d" % (
        len(g), g.district_code.nunique(), g.crop.nunique(), g.year.min(), g.year.max()))
    print("valid yield: %.1f%% | flagged outliers: %d | from UPAG: %d rows" % (
        100 * g.valid_yield.mean(), g.flag_outlier.sum(), (g.source == "UPAG").sum()))
    st = g[g.crop.isin(["Rice", "Wheat", "Maize"]) & g.valid_yield & ~g.flag_outlier]
    t = st.groupby(["year", "crop"]).district_code.nunique().unstack()
    print("\nstaples: districts with a valid yield, by year")
    print(t.to_string())

    # how much history survives the APY -> UPAG handoff (2022 -> 2023)?
    a = st[st.year == 2022][["district_code", "crop", "season"]].drop_duplicates()
    b = st[st.year == 2023][["district_code", "crop", "season"]].drop_duplicates()
    kept = a.merge(b, how="left", indicator=True)["_merge"].eq("both").mean()
    print("\nstaple series present in 2022 that continue under the SAME season label in 2023: %.1f%%" % (100 * kept))


if __name__ == "__main__":
    panel = build()
    checks(panel)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    panel.to_parquet(OUT, index=False)
    report(panel)
    print("\nwrote %s (%.1f MB)" % (OUT, os.path.getsize(OUT) / 1e6))

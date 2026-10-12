"""
Phase 1A: slow-changing district attributes from ICRISAT-TCI (irrigation, cropping intensity, fertilizer).

    python pipeline/build_static.py

Reads  data/raw/icrisat/{sourcewise-irrigated-area,landuse,fertilizer-consumption}.json
       data/processed/district_geo.parquet
Writes data/processed/district_static.parquet     one row per yield-panel district

ICRISAT units are 1966 districts apportioned to constant boundaries (311 of them), so a current
district is attached to its unit in two steps, and the step is recorded in `icr_match`:

  name      same state and normalised name (about 80% of units)
  nearest   otherwise the nearest ICRISAT unit centroid in the same state, only if within 100 km
            (a district created by splitting a 1966 one inherits its parent's values: an approximation)
  none      no unit close enough, or the district has no polygon centroid

Features (irrigation and land use are averaged over 2016-2020, fertilizer over 2013-2017, the last
years each file has, so they are a recent snapshot, not a time series):
  irr_net_share      net irrigated area / net cropped area
  irr_well_share     (tube wells + other wells) / net irrigated area  (groundwater dependence)
  irr_canal_share    canals / net irrigated area
  cropping_intensity gross / net cropped area, percent
  fert_npk_per_ha    total NPK per hectare of net cropped area, kg/ha
"""

import json
import os
import re
import sys
import unicodedata

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw", "icrisat")
OUT = os.path.join(ROOT, "data", "processed", "district_static.parquet")
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from build_district_geo import norm, state_key  # noqa: E402

MAX_KM = 100.0


def load(name):
    j = json.load(open(os.path.join(RAW, name + ".json"), encoding="utf-8"))
    df = pd.DataFrame(j["data"], columns=[h["header"] for h in j["headers"]])
    df["Year"] = pd.to_numeric(df["Year"], errors="coerce")
    return df.dropna(subset=["Year"])


def recent(df, cols, y0, y1):
    d = df[df.Year.between(y0, y1)].copy()
    for c in cols:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d.groupby("Dist Code")[cols].mean()


def units():
    src, land, fert = load("sourcewise-irrigated-area"), load("landuse"), load("fertilizer-consumption")
    s = recent(src, ["CANALS AREA", "TOTAL WELLS AREA", "NET AREA"], 2016, 2020)
    l = recent(land, ["NET CROPPED AREA", "GROSS CROPPED AREA"], 2016, 2020)
    f = recent(fert, ["TOTAL PER HA OF NCA"], 2013, 2017)
    u = s.join(l, how="outer").join(f, how="outer")
    u["irr_net_share"] = u["NET AREA"] / u["NET CROPPED AREA"]
    u["irr_well_share"] = u["TOTAL WELLS AREA"] / u["NET AREA"]
    u["irr_canal_share"] = u["CANALS AREA"] / u["NET AREA"]
    u["cropping_intensity"] = 100 * u["GROSS CROPPED AREA"] / u["NET CROPPED AREA"]
    u["fert_npk_per_ha"] = u["TOTAL PER HA OF NCA"]
    # share ratios outside 0-1.5 are data errors in a 1966-vintage file, not real irrigation
    for c in ("irr_net_share", "irr_well_share", "irr_canal_share"):
        u[c] = u[c].where(u[c].between(0, 1.5))
    meta = src.drop_duplicates("Dist Code").set_index("Dist Code")[["State Name", "Dist Name", "LATITUDE", "LONGITUDE"]]
    for c in ("LATITUDE", "LONGITUDE"):
        meta[c] = pd.to_numeric(meta[c], errors="coerce")
    return meta.join(u[["irr_net_share", "irr_well_share", "irr_canal_share", "cropping_intensity", "fert_npk_per_ha"]])


def km(lat1, lon1, lat2, lon2):
    p = np.pi / 180
    a = np.sin((lat2 - lat1) * p / 2) ** 2 + np.cos(lat1 * p) * np.cos(lat2 * p) * np.sin((lon2 - lon1) * p / 2) ** 2
    return 12742 * np.arcsin(np.sqrt(a))


def build():
    u = units()
    u["skey"] = u["State Name"].map(state_key)
    u["nkey"] = u["Dist Name"].map(norm)
    geo = pd.read_parquet(os.path.join(ROOT, "data", "processed", "district_geo.parquet"))
    feats = ["irr_net_share", "irr_well_share", "irr_canal_share", "cropping_intensity", "fert_npk_per_ha"]
    rows = []
    for r in geo.itertuples():
        sk, nk = state_key(r.state_name), norm(r.district_name)
        cand = u[u.skey == sk]
        hit = cand[cand.nkey == nk]
        match, dist, vals = "none", np.nan, {f: np.nan for f in feats}
        if len(hit) >= 1:
            match, vals = "name", hit.iloc[0][feats].to_dict()
        elif pd.notna(r.lat) and len(cand.dropna(subset=["LATITUDE"])):
            c = cand.dropna(subset=["LATITUDE"])
            d = km(float(r.lat), float(r.lon), c.LATITUDE.values, c.LONGITUDE.values)
            i = int(np.argmin(d))
            if d[i] <= MAX_KM:
                match, dist, vals = "nearest", float(d[i]), c.iloc[i][feats].to_dict()
        rows.append({"district_code": r.district_code, "icr_match": match, "icr_dist_km": dist, **vals})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    out = build()
    out.to_parquet(OUT, index=False)
    print("icr_match:", out.icr_match.value_counts().to_dict())
    print(out[["irr_net_share", "irr_well_share", "irr_canal_share", "cropping_intensity", "fert_npk_per_ha"]].describe().round(2).to_string())
    print("wrote %s" % OUT)

"""
Phase 1A: district soil profile from the Soil Health Card nutrient file (1.1 GB, streamed).

    python pipeline/build_soil.py

Reads  data/raw/soil/soil_nutrient_analysis.csv   India Data Portal, MoAFW Soil Health Card, 2023-2025, ODC-BY
Writes data/processed/district_soil.parquet       one row per district_code

The file is village x nutrient x level, where `value` is the NUMBER OF SAMPLES that tested at that
level (Low / Medium / High; pH Acidic / Neutral / Alkaline; ...). It holds no N, P, K in kg/ha, so
the old state-level N/P/K/pH columns cannot be reproduced; what it does give is, per district, the
fraction of tested soils that are low or high in each nutrient. Features written per nutrient X:

    soil_X_low, soil_X_high   share of samples at that level (N, P, K, OC)
    soil_X_idx                (1*low + 2*medium + 3*high) / samples, i.e. 1 = all low, 3 = all high
    soil_ph_acidic, soil_ph_alkaline, soil_ec_saline            shares
    soil_<micro>_deficient                                      share (B, Cu, Fe, Mn, S, Zn)
    soil_samples                                                tests behind the district's N figure

The card data is a 2023-25 snapshot; soil fertility moves slowly, so it is used as a static district
attribute for every year, which is an assumption. Districts with few samples are noisy:
soil_samples lets downstream code down-weight or drop them.
"""

import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "raw", "soil", "soil_nutrient_analysis.csv")
OUT = os.path.join(ROOT, "data", "processed", "district_soil.parquet")

MACRO = {"Nitrogen": "n", "Phosphorus": "p", "Potassium": "k", "Organic Carbon": "oc"}
MICRO = {"Boron": "b", "Copper": "cu", "Iron": "fe", "Manganese": "mn", "Sulphur": "s", "Zinc": "zn"}


def aggregate(src=SRC):
    acc, rows = {}, 0
    for ch in pd.read_csv(src, usecols=["state_name", "district_name", "district_code", "nutrient_name",
                                        "nutrient_level", "value"], chunksize=2_000_000, on_bad_lines="skip"):
        rows += len(ch)
        for k, v in ch.groupby(["district_code", "nutrient_name", "nutrient_level"]).value.sum().items():
            acc[k] = acc.get(k, 0) + v
        names = ch.groupby("district_code")[["state_name", "district_name"]].last()
        acc.setdefault("names", {}).update(names.to_dict("index"))
    print("rows read: %d" % rows)
    return acc


def features(acc):
    names = acc.pop("names")
    t = pd.Series(acc).rename("n").reset_index()
    t.columns = ["district_code", "nutrient", "level", "n"]
    wide = t.pivot_table(index=["district_code", "nutrient"], columns="level", values="n", aggfunc="sum", fill_value=0)
    out = pd.DataFrame(index=sorted({c for c, _ in wide.index}))
    out.index.name = "district_code"

    def get(nut, level):
        s = wide.xs(nut, level="nutrient")[level] if level in wide.columns else None
        return s.reindex(out.index).fillna(0) if s is not None else pd.Series(0, index=out.index)

    for nut, k in MACRO.items():
        lo, me, hi = get(nut, "Low"), get(nut, "Medium"), get(nut, "High")
        tot = (lo + me + hi).where(lambda s: s > 0)
        out["soil_%s_low" % k], out["soil_%s_high" % k] = lo / tot, hi / tot
        out["soil_%s_idx" % k] = (lo + 2 * me + 3 * hi) / tot
        if k == "n":
            out["soil_samples"] = tot
    ph = get("Soil Ph", "Acidic") + get("Soil Ph", "Neutral") + get("Soil Ph", "Alkaline")
    out["soil_ph_acidic"] = get("Soil Ph", "Acidic") / ph.where(ph > 0)
    out["soil_ph_alkaline"] = get("Soil Ph", "Alkaline") / ph.where(ph > 0)
    ec = get("Electrical Conductivity", "Saline") + get("Electrical Conductivity", "Non Saline")
    out["soil_ec_saline"] = get("Electrical Conductivity", "Saline") / ec.where(ec > 0)
    for nut, k in MICRO.items():
        d, s = get(nut, "Deficient"), get(nut, "Sufficient")
        out["soil_%s_deficient" % k] = d / (d + s).where((d + s) > 0)
    out = out.join(pd.DataFrame.from_dict(names, orient="index"))
    return out.reset_index()


if __name__ == "__main__":
    res = features(aggregate())
    res.to_parquet(OUT, index=False)
    print("districts %d | median samples per district %.0f | districts with <200 samples: %d" % (
        len(res), res.soil_samples.median(), (res.soil_samples < 200).sum()))
    print(res[["soil_n_idx", "soil_p_idx", "soil_k_idx", "soil_oc_idx", "soil_ph_acidic", "soil_ph_alkaline"]].describe().round(2).to_string())
    print("wrote %s" % OUT)

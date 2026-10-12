"""
Phase 1A, step 7: do weather and soil help? (criterion C3 in PRODUCTION_ROADMAP.md)

    python pipeline/district_weather_eval.py

Three models on IDENTICAL rows (district series with a polygon and weather), same trees, same split:
  history           the history-only model from district_baseline.py
  + weather         history + season weather (raw and as anomalies from the district's own norm)
  + weather + soil  also the Soil Health Card profile and ICRISAT irrigation / intensity / fertilizer

C3 passes only if the best of the two weather models has MAE at least 2% below `history` on the
2018-2023 holdout. Reported alongside: every single test year (rolling origin), and per crop.

IMPORTANT: this is an UPPER BOUND on what weather can add to a real forecast. It uses the weather
that actually fell over the whole season, which is not known when a forecast is issued. A real
forecast has only the weather so far plus a forecast of the rest (Phase 2, by lead time). If weather
cannot help even with hindsight, it cannot help in advance.

Anomalies use each district-season's mean over the TRAINING years only, so no test-year weather leaks
into the norm. Soil is a 2023-25 snapshot used as a static attribute for every year (an assumption).
"""

import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from district_baseline import CATS, LAST_YEAR, NUM as HIST_NUM, TEST_FROM, load  # noqa: E402
from train_v3 import build_model, skill  # noqa: E402

PROC = os.path.join(ROOT, "data", "processed")
OUT = os.path.join(PROC, "district_weather_eval.json")
WEATHER = ["rain_sum", "rain_days", "rain_first30", "rain_pre60", "dry_spell_max", "tmax_mean", "tmin_mean",
           "hot_days", "rh_mean", "sw_mean"]
SOIL = ["soil_n_idx", "soil_p_idx", "soil_k_idx", "soil_oc_idx", "soil_n_low", "soil_p_low", "soil_k_low",
        "soil_oc_low", "soil_ph_acidic", "soil_ph_alkaline", "soil_ec_saline", "soil_zn_deficient",
        "soil_b_deficient", "soil_s_deficient"]
STATIC = ["irr_net_share", "irr_well_share", "irr_canal_share", "cropping_intensity", "fert_npk_per_ha"]
MIN_WEATHER_COVER = 0.5      # a weather column with less than this share of rows present is dropped, not imputed


def assemble():
    d = load()
    geo = pd.read_parquet(os.path.join(PROC, "district_geo.parquet"))[["district_code", "shape_id"]]
    d = d.merge(geo, on="district_code").dropna(subset=["shape_id"])
    sw = pd.read_parquet(os.path.join(PROC, "season_weather.parquet")).rename(columns={"window": "season"})
    d = d.merge(sw, on=["shape_id", "year", "season"], how="left")
    d = d.merge(pd.read_parquet(os.path.join(PROC, "district_soil.parquet"))[["district_code"] + SOIL], on="district_code", how="left")
    d = d.merge(pd.read_parquet(os.path.join(PROC, "district_static.parquet"))[["district_code"] + STATIC], on="district_code", how="left")
    cover = d[WEATHER].notna().mean()
    keep = [c for c in WEATHER if cover[c] >= MIN_WEATHER_COVER]
    print("weather columns kept %s | dropped (cover < %.0f%%): %s" % (keep, 100 * MIN_WEATHER_COVER,
          {c: round(float(cover[c]), 2) for c in WEATHER if c not in keep}))
    d = d.dropna(subset=["rain_sum"]).reset_index(drop=True)      # rows without rainfall cannot be compared
    return d, keep


def add_anomalies(d, cols, train_mask):
    """Each weather column minus the district-season mean over the training rows."""
    g = d.loc[train_mask].groupby(["shape_id", "season"])[cols].mean().add_suffix("_norm")
    d = d.join(g, on=["shape_id", "season"])
    for c in cols:
        d[c + "_anom"] = d[c] - d[c + "_norm"]
    return d.drop(columns=[c + "_norm" for c in cols])


def run(d, weather, tr_mask, te_mask):
    d = add_anomalies(d, weather, tr_mask)
    wx = weather + [c + "_anom" for c in weather]
    sets = {"history": HIST_NUM, "+ weather": HIST_NUM + wx, "+ weather + soil": HIST_NUM + wx + SOIL + STATIC}
    tr, te = d[tr_mask.values], d[te_mask.values]
    res = {}
    for name, num in sets.items():
        m = build_model(num, CATS).fit(tr[num + CATS], tr["yield"])
        pred = m.predict(te[num + CATS])
        res[name] = {"mae": float(mean_absolute_error(te["yield"], pred)), "pred": pred}
    return te, res


def main():
    d, weather = assemble()
    print("rows %d | districts %d | years %d-%d" % (len(d), d.district_code.nunique(), d.year.min(), d.year.max()))

    tr_mask, te_mask = d.year < TEST_FROM, (d.year >= TEST_FROM) & (d.year <= LAST_YEAR)
    te, res = run(d, weather, tr_mask, te_mask)
    base = res["history"]["mae"]
    print("\nHOLDOUT %d-%d (n=%d), identical rows for all three" % (TEST_FROM, LAST_YEAR, len(te)))
    out = {"n_test": int(len(te)), "weather_cols": weather, "holdout": {}}
    for k, v in res.items():
        out["holdout"][k] = {"mae": round(v["mae"], 4), "skill_vs_history_pct": skill(v["mae"], base)}
        print("  %-20s MAE %.4f   vs history %+.1f%%" % (k, v["mae"], skill(v["mae"], base)))
    for crop in ("Rice", "Wheat", "Maize"):
        mk = (te["crop"] == crop).to_numpy()
        h = mean_absolute_error(te["yield"][mk], res["history"]["pred"][mk])
        w = mean_absolute_error(te["yield"][mk], res["+ weather + soil"]["pred"][mk])
        print("  %-6s history %.3f -> +weather+soil %.3f  (%+.1f%%)" % (crop, h, w, skill(w, h)))
        out.setdefault("per_crop", {})[crop] = {"history_mae": round(h, 4), "full_mae": round(w, 4), "skill_pct": skill(w, h)}

    print("\nROLLING ORIGIN, one test year at a time")
    out["rolling"] = []
    for yr in range(TEST_FROM, LAST_YEAR + 1):
        t, r = run(d, weather, d.year < yr, d.year == yr)
        h = r["history"]["mae"]
        row = {"year": yr, "n": int(len(t)), "history": round(h, 4),
               "weather": round(r["+ weather"]["mae"], 4), "weather_soil": round(r["+ weather + soil"]["mae"], 4),
               "weather_skill_pct": skill(r["+ weather"]["mae"], h), "weather_soil_skill_pct": skill(r["+ weather + soil"]["mae"], h)}
        out["rolling"].append(row)
        print("  %d n=%d history %.4f | +weather %.4f (%+.1f%%) | +soil %.4f (%+.1f%%)" % (
            yr, row["n"], h, row["weather"], row["weather_skill_pct"], row["weather_soil"], row["weather_soil_skill_pct"]))

    best = max(out["holdout"]["+ weather"]["skill_vs_history_pct"], out["holdout"]["+ weather + soil"]["skill_vs_history_pct"])
    wins = sum(max(r["weather_skill_pct"], r["weather_soil_skill_pct"]) > 0 for r in out["rolling"])
    c3 = best >= 2.0
    out.update({"best_skill_pct": best, "years_improved": wins, "C3": c3})
    print("\nC3 (weather/soil >= 2%% lower MAE than history-only): %s  [best %+.1f%%, better in %d/%d test years]"
          % ("PASS" if c3 else "FAIL", best, wins, len(out["rolling"])))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print("wrote %s" % OUT)


if __name__ == "__main__":
    main()

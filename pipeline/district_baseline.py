"""
Phase 1A, step 5: what district-level yield HISTORY can do on its own, before any weather or soil.

    python pipeline/district_baseline.py

This is the bar the weather and soil work has to clear. It scores the criteria written in
PRODUCTION_ROADMAP.md (Phase 1 pass/fail criteria) C1 and C2, and gives the history-only
number that C3 compares against. Scope: Rice, Wheat, Maize; each (district, crop, season)
series forecast one season ahead; 2024 excluded (UPAG 2024-25 is partial).

Reads  data/processed/district_yield.parquet
Writes data/processed/district_baseline_metrics.json
"""

import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import GroupKFold

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from forecasting import HISTORY_FEATURES, add_history, build_panel  # noqa: E402
from train_v3 import build_model, scores, skill  # noqa: E402

PANEL = os.path.join(ROOT, "data", "processed", "district_yield.parquet")
OUT = os.path.join(ROOT, "data", "processed", "district_baseline_metrics.json")

STAPLES = ["Rice", "Wheat", "Maize"]
KEY = ["district_code", "crop", "season"]
LAST_YEAR = 2023
TEST_FROM = 2018
NUM = ["year"] + HISTORY_FEATURES
CATS = ["crop", "season", "state_name"]
FEATURES = NUM + CATS


def load():
    g = pd.read_parquet(PANEL)
    g = g[g.crop.isin(STAPLES) & g.valid_yield & ~g.flag_outlier & (g.year <= LAST_YEAR)].copy()
    g = add_history(g, build_panel(g, KEY), KEY)
    return g[g.history_seasons >= 1].reset_index(drop=True)   # forecastable rows


def baselines(tr, te):
    """Every baseline for `te`, using only training years plus the earlier seasons attached to each row."""
    crop_state = tr.groupby(["state_name", "crop"])["yield"].mean().rename("cs").reset_index()
    series = tr.groupby(KEY)["yield"].mean().rename("s").reset_index()
    cs = te[["state_name", "crop"]].merge(crop_state, how="left", on=["state_name", "crop"])["cs"].to_numpy()
    cs = np.where(np.isnan(cs), te["crop"].map(tr.groupby("crop")["yield"].mean()).to_numpy(), cs)
    s = te[KEY].merge(series, how="left", on=KEY)["s"].to_numpy()
    return {
        "persistence": te["yield_anchor"].to_numpy(),
        "mean_3yr": te["yield_mean3"].to_numpy(),
        "district_series_mean": np.where(np.isnan(s), cs, s),
        "state_crop_mean": cs,
    }


def fit_predict(tr, te):
    return build_model(NUM, CATS).fit(tr[FEATURES], tr["yield"]).predict(te[FEATURES])


def compare(y, pred, base):
    m = scores(y, pred)
    b = {k: scores(y, v) for k, v in base.items()}
    return {"model": m, "baselines": b,
            "skill_pct": {k: skill(m["mae"], v["mae"]) for k, v in b.items()}}


def main():
    d = load()
    print("forecastable rows %d | districts %d | years %d-%d" % (
        len(d), d.district_code.nunique(), d.year.min(), d.year.max()))

    # holdout: train < 2018, test 2018-2023
    tr, te = d[d.year < TEST_FROM], d[d.year >= TEST_FROM]
    y = te["yield"].to_numpy()
    base = baselines(tr, te)
    holdout = compare(y, fit_predict(tr, te), base)
    per_crop = {}
    pred = fit_predict(tr, te)
    for crop in STAPLES:
        mk = (te["crop"] == crop).to_numpy()
        mae_m = float(mean_absolute_error(y[mk], pred[mk]))
        mae_p = float(mean_absolute_error(y[mk], base["persistence"][mk]))
        per_crop[crop] = {"n": int(mk.sum()), "model_mae": round(mae_m, 4),
                          "persistence_mae": round(mae_p, 4), "skill_vs_persistence_pct": skill(mae_m, mae_p)}
    print("\nHOLDOUT 2018-2023 (n=%d)" % len(te))
    print("  model MAE %.4f R2 %.4f" % (holdout["model"]["mae"], holdout["model"]["r2"]))
    for k, v in holdout["baselines"].items():
        print("  %-22s MAE %.4f  model skill %+.1f%%" % (k, v["mae"], holdout["skill_pct"][k]))
    for c, r in per_crop.items():
        print("  %-6s n=%d model %.3f vs persistence %.3f  skill %+.1f%%" % (
            c, r["n"], r["model_mae"], r["persistence_mae"], r["skill_vs_persistence_pct"]))

    # rolling origin, one test year at a time
    rolling = []
    for yr in range(TEST_FROM, LAST_YEAR + 1):
        a, b = d[d.year < yr], d[d.year == yr]
        mae_m = mean_absolute_error(b["yield"], fit_predict(a, b))
        mae_p = mean_absolute_error(b["yield"], b["yield_anchor"])
        mae_3 = mean_absolute_error(b["yield"], b["yield_mean3"])
        rolling.append({"year": yr, "n": int(len(b)), "model_mae": round(float(mae_m), 4),
                        "persistence_mae": round(float(mae_p), 4), "mean_3yr_mae": round(float(mae_3), 4),
                        "skill_vs_persistence_pct": skill(mae_m, mae_p)})
        print("  %d n=%d model %.4f persistence %.4f 3yr %.4f  skill %+.1f%%" % (
            yr, len(b), mae_m, mae_p, mae_3, rolling[-1]["skill_vs_persistence_pct"]))
    wins = sum(r["skill_vs_persistence_pct"] > 0 for r in rolling)

    # leave-districts-out: whole districts withheld, their own history still an input
    pred_lso = np.zeros(len(d))
    for a, b in GroupKFold(5).split(d, groups=d["district_code"]):
        pred_lso[b] = fit_predict(d.iloc[a], d.iloc[b])
    lso = compare(d["yield"].to_numpy(), pred_lso,
                  {"persistence": d["yield_anchor"].to_numpy(), "mean_3yr": d["yield_mean3"].to_numpy()})
    print("\nLEAVE-DISTRICTS-OUT (n=%d): model %.4f persistence %.4f skill %+.1f%%" % (
        len(d), lso["model"]["mae"], lso["baselines"]["persistence"]["mae"], lso["skill_pct"]["persistence"]))

    # EXTRA, added after C2 passed and NOT one of the pre-registered criteria. Plain leave-districts-out
    # trains on other districts' rows from the SAME years it tests, so it can learn a year's common
    # shock (a drought) that is not knowable ahead of time. Strict version: unseen districts AND
    # unseen years -- train only on other districts' seasons before 2018, test 2018-2023.
    ys, ps, per, m3 = [], [], [], []
    for a, b in GroupKFold(5).split(d, groups=d["district_code"]):
        tr_s, te_s = d.iloc[a], d.iloc[b]
        tr_s, te_s = tr_s[tr_s.year < TEST_FROM], te_s[te_s.year >= TEST_FROM]
        ys.append(te_s["yield"].to_numpy()); ps.append(fit_predict(tr_s, te_s))
        per.append(te_s["yield_anchor"].to_numpy()); m3.append(te_s["yield_mean3"].to_numpy())
    strict = compare(np.concatenate(ys), np.concatenate(ps),
                     {"persistence": np.concatenate(per), "mean_3yr": np.concatenate(m3)})
    print("STRICT leave-districts-out + forward in time (n=%d): model %.4f persistence %.4f skill %+.1f%%"
          % (strict["model"]["n"], strict["model"]["mae"], strict["baselines"]["persistence"]["mae"],
             strict["skill_pct"]["persistence"]))

    c1 = holdout["skill_pct"]["persistence"] > 0 and wins >= 4
    c2 = lso["skill_pct"]["persistence"] > 0
    print("\nC1 (beats persistence pooled and in >=4/6 years): %s  [pooled %+.1f%%, %d/6 years]" % (
        "PASS" if c1 else "FAIL", holdout["skill_pct"]["persistence"], wins))
    print("C2 (positive skill, leave-districts-out):          %s  [%+.1f%%]" % (
        "PASS" if c2 else "FAIL", lso["skill_pct"]["persistence"]))
    print("C3 (weather + soil >= 2%% better than history-only) needs weather and soil: history-only MAE %.4f"
          % holdout["model"]["mae"])

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"scope": STAPLES, "test": "%d-%d" % (TEST_FROM, LAST_YEAR), "holdout": holdout,
                   "per_crop": per_crop, "rolling_origin": rolling, "years_beating_persistence": wins,
                   "leave_districts_out": lso, "leave_districts_out_forward_extra": strict,
                   "C1": c1, "C2": c2,
                   "history_only_holdout_mae": holdout["model"]["mae"]}, f, indent=2)
    print("wrote %s" % OUT)


if __name__ == "__main__":
    main()

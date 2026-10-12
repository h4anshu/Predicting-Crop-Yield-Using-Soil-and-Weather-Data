"""
Phase 2: forecasts at a stated lead time, with intervals and trust flags.
Criteria P2-1, P2-2, P2-3 in PRODUCTION_ROADMAP.md (written before this was run).

    python pipeline/phase2_forecast.py

Groups: Kharif Rice + Maize (history + to-date weather + NDVI) and Wheat/Rabi (history + NDVI, no weather).
Leads: 0 (history only), 60, 90, 120 days after the window opens (Kharif Jun 1, Rabi Nov 1). A lead-L model sees
only weather and NDVI up to day L. Same anchored Extra Trees as before, configuration fixed, no tuning.

Rolling origin: for each test year Y, train on earlier years only. 2018-2023 is development, 2024 is the
confirmation set (never used for a decision; its yields are partial). 2017 is run only to supply calibration
residuals for 2018.

Intervals (80%): split conformal. For test year Y the interval is pred x (1 +/- q), where q is the 80% quantile
(finite-sample corrected) of |y - pred| / pred over year Y-1's out-of-sample forecasts from the model trained on
years before Y-1. Calibrating on the previous year assumes forecast error scale changes slowly; that is
checked by the coverage, not assumed.

Trust flag: recent volatility of the series, mean of |lag1 - lag2| and |lag2 - lag3| over the 3-season mean. A row
is flagged when its volatility is in the top 20% of the TRAINING rows' volatility for that test year.

Writes data/processed/phase2_metrics.json and data/processed/phase2_predictions.parquet (every test-year forecast).
Set HIST_SHIFT=1 to impose a one-season publication lag (Gate G1): history comes only from seasons <= Y-2 and the
baselines become "last available season repeated" / "mean of the last three available". Outputs get a _shift1 suffix.
"""

import json
import math
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
from district_baseline import CATS, KEY, PANEL, STAPLES  # noqa: E402
from forecasting import HISTORY_FEATURES, add_history, build_panel  # noqa: E402
from train_v3 import build_model, skill  # noqa: E402

PROC = os.path.join(ROOT, "data", "processed")
HIST = ["year"] + HISTORY_FEATURES
NDVI = ["ndvi_max", "ndvi_mean", "ndvi_int", "evi_max", "evi_mean"]
WX = ["wl_rain_sum", "wl_rain_days", "wl_rain_pre60", "wl_dry_spell_max", "wl_tmax_mean", "wl_tmin_mean",
      "wl_hot_days", "wl_rh_mean", "wl_sw_mean"]
LEADS = [0, 60, 90, 120]
FIT_LEADS = LEADS          # which leads run_group fits; every lead's columns are still used to pick the rows
DEV_YEARS, CONFIRM = list(range(2018, 2024)), 2024
CAL_FIRST = 2017           # run only to calibrate 2018
GROUPS = {
    "Kharif Rice + Maize": dict(sel=lambda d: d.crop.isin(["Rice", "Maize"]) & (d.season == "Kharif"), window="Kharif", weather=True),
    "Wheat (Rabi)": dict(sel=lambda d: (d.crop == "Wheat") & (d.season == "Rabi"), window="Rabi", weather=False),
}
SK = ["shape_id", "crop", "season"]
COVER_LEVEL = 0.8
SHIFT = int(os.environ.get("HIST_SHIFT", "0"))     # publication lag in seasons (Gate G1 uses 1)
SUFFIX = "" if SHIFT == 0 else "_shift%d" % SHIFT


def load():
    g = pd.read_parquet(PANEL)
    g = g[g.crop.isin(STAPLES) & g.valid_yield & ~g.flag_outlier & (g.year <= CONFIRM)].copy()
    g = add_history(g, build_panel(g, KEY), KEY, shift=SHIFT)
    g = g[g.history_seasons >= 1].dropna(subset=["yield_anchor"])
    geo = pd.read_parquet(os.path.join(PROC, "district_geo.parquet"))[["district_code", "shape_id"]]
    g = g.merge(geo, on="district_code").dropna(subset=["shape_id"])
    # volatility of the series: how much it jumped in the last two seasons, relative to its level
    g["vol"] = ((g.yield_lag1 - g.yield_lag2).abs() + (g.yield_lag2 - g.yield_lag3).abs()) / 2 / g.yield_mean3
    return g


def attach(d, window, weather):
    sn = pd.read_parquet(os.path.join(PROC, "season_ndvi.parquet"))
    sl = pd.read_parquet(os.path.join(PROC, "season_weather_lead.parquet"))
    for lead in LEADS[1:]:
        a = sn[(sn.window == window) & (sn.lead == lead)][["shape_id", "year"] + NDVI]
        a.columns = ["shape_id", "year"] + ["nd%d_%s" % (lead, c) for c in NDVI]
        d = d.merge(a, on=["shape_id", "year"], how="left")
        if weather:
            b = sl[(sl.window == window) & (sl.lead == lead)][["shape_id", "year"] + WX]
            b.columns = ["shape_id", "year"] + ["wx%d_%s" % (lead, c[3:]) for c in WX]
            d = d.merge(b, on=["shape_id", "year"], how="left")
    return d


def lead_cols(lead, weather):
    if lead == 0:
        return []
    cols = ["nd%d_%s" % (lead, c) for c in NDVI]
    if weather:
        cols += ["wx%d_%s" % (lead, c[3:]) for c in WX]
    return cols


def with_anomalies(d, cols, train_mask):
    n = d.loc[train_mask].groupby(SK)[cols].mean().add_suffix("_n")
    d = d.join(n, on=SK)
    for c in cols:
        d[c + "_anom"] = d[c] - d[c + "_n"]
    return d.drop(columns=[c + "_n" for c in cols])


def conformal_q(rel_resid, level=COVER_LEVEL):
    r = np.sort(np.asarray(rel_resid))
    k = min(len(r) - 1, math.ceil((len(r) + 1) * level) - 1)
    return float(r[k])


def run_group(name, spec, g):
    d = attach(g[spec["sel"](g)], spec["window"], spec["weather"]).reset_index(drop=True)
    need = [c for c in lead_cols(120, spec["weather"])]
    d = d.dropna(subset=need).reset_index(drop=True)      # identical rows for every lead
    print("\n%s: %d rows, %d districts, years %d-%d" % (name, len(d), d.district_code.nunique(), d.year.min(), d.year.max()), flush=True)
    allcols = sorted({c for L in LEADS for c in lead_cols(L, spec["weather"])})
    out = []
    prev_resid = {}                                         # lead -> relative residuals of the previous test year
    for yr in [CAL_FIRST] + DEV_YEARS + [CONFIRM]:
        dd = with_anomalies(d, allcols, d.year < yr)
        tr, te = dd[dd.year < yr], dd[dd.year == yr]
        if len(te) == 0:
            continue
        thr = tr["vol"].quantile(0.8)
        for lead in FIT_LEADS:
            lc = lead_cols(lead, spec["weather"])
            num = HIST + lc + [c + "_anom" for c in lc]
            m = build_model(num, CATS).fit(tr[num + CATS], tr["yield"])
            pred = m.predict(te[num + CATS])
            rel = np.abs(te["yield"].to_numpy() - pred) / np.maximum(pred, 0.05)
            row = te[["district_code", "state_name", "crop", "season", "year", "yield", "yield_anchor", "yield_mean3", "vol"]].copy()
            row["pred"], row["lead"], row["group"] = pred, lead, name
            if lead in prev_resid:                          # previous year's residuals calibrate this year's interval
                q = conformal_q(prev_resid[lead])
                row["q"], row["lo"], row["hi"] = q, pred * (1 - q), pred * (1 + q)
            row["flag_low_trust"] = (te["vol"] >= thr).to_numpy()
            out.append(row)
            prev_resid[lead] = rel
        print("  %d done (n=%d)" % (yr, len(te)), flush=True)
    return pd.concat(out, ignore_index=True)


def mae(df, col):
    return float(np.abs(df["yield"] - df[col]).mean())


def summarize(P):
    S = {}
    for label, years in (("dev_2018_2023", DEV_YEARS), ("confirm_2024", [CONFIRM])):
        s = P[P.year.isin(years)]
        S[label] = {}
        for lead in LEADS:
            x = s[s.lead == lead]
            S[label][str(lead)] = {
                "n": int(len(x)), "mae": round(mae(x, "pred"), 4), "persistence_mae": round(mae(x, "yield_anchor"), 4),
                "mean3_mae": round(mae(x, "yield_mean3"), 4),
                "skill_vs_persistence_pct": skill(mae(x, "pred"), mae(x, "yield_anchor")),
                "skill_vs_mean3_pct": skill(mae(x, "pred"), mae(x, "yield_mean3"))}
            if x["lo"].notna().any():
                c = x.dropna(subset=["lo"])
                S[label][str(lead)]["coverage_80"] = round(float(((c["yield"] >= c.lo) & (c["yield"] <= c.hi)).mean()), 4)
                S[label][str(lead)]["median_rel_halfwidth"] = round(float(c.q.median()), 4)
    # per group, lead 90, dev years
    S["by_group_lead90_dev"] = {}
    for gname, x in P[(P.lead == 90) & P.year.isin(DEV_YEARS)].groupby("group"):
        S["by_group_lead90_dev"][gname] = {"n": int(len(x)), "skill_vs_persistence_pct": skill(mae(x, "pred"), mae(x, "yield_anchor"))}
    # per-year skill at lead 90 over both groups
    S["lead90_by_year"] = []
    for yr in DEV_YEARS + [CONFIRM]:
        x = P[(P.lead == 90) & (P.year == yr)]
        S["lead90_by_year"].append({"year": yr, "n": int(len(x)), "skill_vs_persistence_pct": skill(mae(x, "pred"), mae(x, "yield_anchor"))})
    # trust flags at lead 90
    S["trust_flags_lead90"] = {}
    for label, years in (("dev_2018_2023", DEV_YEARS), ("confirm_2024", [CONFIRM])):
        x = P[(P.lead == 90) & P.year.isin(years) & P.vol.notna()]
        f, u = x[x.flag_low_trust], x[~x.flag_low_trust]
        S["trust_flags_lead90"][label] = {"n_flagged": int(len(f)), "n_unflagged": int(len(u)),
                                          "mae_flagged": round(mae(f, "pred"), 4), "mae_unflagged": round(mae(u, "pred"), 4),
                                          "ratio": round(mae(f, "pred") / mae(u, "pred"), 3)}
    return S


def criteria(S):
    d90, c90 = S["dev_2018_2023"]["90"], S["confirm_2024"]["90"]
    yrs = [r for r in S["lead90_by_year"] if r["year"] in DEV_YEARS]
    wins = sum(r["skill_vs_persistence_pct"] > 0 for r in yrs)
    p1 = d90["skill_vs_persistence_pct"] >= 3.0 and wins >= 4 and c90["skill_vs_persistence_pct"] >= 2.0
    cov_d, cov_c = d90.get("coverage_80"), c90.get("coverage_80")
    p2 = cov_d is not None and cov_c is not None and 0.72 <= cov_d <= 0.88 and 0.72 <= cov_c <= 0.88
    tf = S["trust_flags_lead90"]
    p3 = tf["dev_2018_2023"]["ratio"] >= 1.3
    return {"P2_1": bool(p1), "P2_1_detail": {"dev_skill": d90["skill_vs_persistence_pct"], "years_better": wins,
                                              "confirm_skill": c90["skill_vs_persistence_pct"]},
            "P2_2": bool(p2), "P2_2_detail": {"coverage_dev": cov_d, "coverage_2024": cov_c},
            "P2_3": bool(p3), "P2_3_detail": {"ratio_dev": tf["dev_2018_2023"]["ratio"], "ratio_2024": tf["confirm_2024"]["ratio"]}}


def main():
    g = load()
    P = pd.concat([run_group(n, s, g) for n, s in GROUPS.items()], ignore_index=True)
    P.to_parquet(os.path.join(PROC, "phase2_predictions%s.parquet" % SUFFIX), index=False)
    S = summarize(P)
    C = criteria(S)
    print("\nACCURACY BY LEAD (both groups pooled)")
    for label in ("dev_2018_2023", "confirm_2024"):
        print(" ", label)
        for lead in LEADS:
            r = S[label][str(lead)]
            print("    lead %3d n=%5d  MAE %.4f | persistence %.4f | 3yr-mean %.4f | skill vs persistence %+.1f%% | vs 3yr %+.1f%% | cover80 %s" % (
                lead, r["n"], r["mae"], r["persistence_mae"], r["mean3_mae"], r["skill_vs_persistence_pct"], r["skill_vs_mean3_pct"], r.get("coverage_80", "-")))
    print("  lead-90 skill by year:", [(r["year"], r["skill_vs_persistence_pct"]) for r in S["lead90_by_year"]])
    print("  lead-90 by group (dev):", S["by_group_lead90_dev"])
    print("  trust flags (lead 90):", S["trust_flags_lead90"])
    for k in ("P2_1", "P2_2", "P2_3"):
        print("%s: %s  %s" % (k, "PASS" if C[k] else "FAIL", C[k + "_detail"]))
    with open(os.path.join(PROC, "phase2_metrics%s.json" % SUFFIX), "w", encoding="utf-8") as f:
        json.dump({"summary": S, "criteria": C}, f, indent=2)
    print("wrote phase2_metrics%s.json" % SUFFIX)


if __name__ == "__main__":
    main()

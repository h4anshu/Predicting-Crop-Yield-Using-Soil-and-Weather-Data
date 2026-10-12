"""
One table, one model: train and test forecasting models on data/processed/master_panel.parquet.
Criteria M1-M4 are in PRODUCTION_ROADMAP.md ("One table, one model"), written before this was run.

    python pipeline/train_master.py [m1] [m2] [m3]        # default: all three (M4 is scored with M3)

Everything uses the Gate G1 setting: one-season publication lag, rolling origin (test years 2018-2023, confirmation 2024),
Extra Trees with 100 trees, anchored on the last published season. Skill is always per crop or group against the same
rows' baselines, never pooled across crops.

Lag-consistent (Amendment A1 in the roadmap): the model for test year Y is trained on rows with year <= Y-2 only, because
with a one-season publication lag the yields of Y-1 are not known when a Y forecast is made, and intervals for Y are
calibrated on the residuals of year Y-2. Training through Y-1, as this script first did, flattered the staple groups by
about 0.8 points (Kharif) and 4.4 points (Wheat) of skill against the 3-season mean.

Writes data/processed/master_models_metrics.json and master_preds_{m1,m2,m3}.parquet (every test-year forecast).
The serving build (district_forecast.train) imports load(), relative() and fit_predict() from here, so what is served is
the design that was tested.
"""

import json
import math
import os
import sys
import time

import joblib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from forecasting import HISTORY_FEATURES, REL_NUM, add_history, build_panel, relative  # noqa: E402
from train_v3 import build_model, skill  # noqa: E402

PROC = os.path.join(ROOT, "data", "processed")
MASTER = os.path.join(PROC, "master_panel.parquet")

SHIFT = 1
DATA_END = 2024
DEV, CONFIRM = list(range(2018, 2024)), 2024
LAG = 1 + SHIFT                                      # a forecast for Y knows yields through Y-LAG
TEST_YEARS = [2016, 2017] + DEV + [CONFIRM]          # 2016 and 2017 only calibrate 2018 and 2019
KEY = ["district_code", "crop", "season"]
HIST = ["year"] + HISTORY_FEATURES
CATS = ["crop", "season", "state_name"]
STATIC = None            # filled by load(): soil_*, ICRISAT attributes, lon, lat
GROUPS = {
    "Kharif Rice + Maize": lambda d: d.crop.isin(["Rice", "Maize"]) & (d.season == "Kharif"),
    "Wheat (Rabi)": lambda d: (d.crop == "Wheat") & (d.season == "Rabi"),
}
LEAF_SIZES = (20, 50, 100)
MAX_MODEL_MB = 15
COVER_LEVEL = 0.8
MIN_TEST_ROWS, MIN_SKILL, MIN_YEARS = 300, 2.0, 4


def valid_rows():
    """Every usable district row of the master table (no history needed): what the service keeps for history and maps."""
    head = ["level", "state_name", "district_name", "shape_id", "district_code", "crop", "season", "year", "yield", "valid_yield", "flag_outlier",
            "lon", "lat", "ndvi120_max", "wx_rain_sum", "icr_dist_km", "irr_net_share", "irr_well_share", "irr_canal_share",
            "cropping_intensity", "fert_npk_per_ha"]
    soil = [c for c in pq.read_schema(MASTER).names if c.startswith("soil_")]
    g = pd.read_parquet(MASTER, columns=head + soil)
    g = g[(g.level == "district") & g.valid_yield & ~g.flag_outlier & (g.year <= DATA_END) & (g.crop != "Coconut")].copy()
    g["district_code"] = g["district_code"].astype(int)
    assert not g.duplicated(KEY + ["year"]).any(), "series are not unique: a join multiplied rows"
    global STATIC
    STATIC = soil + ["icr_dist_km", "irr_net_share", "irr_well_share", "irr_canal_share", "cropping_intensity", "fert_npk_per_ha", "lon", "lat"]
    return g


def load():
    """Forecastable district rows (at least one of the three lags exists), with history features, volatility and the relative design."""
    g = valid_rows()
    g = add_history(g, build_panel(g, KEY), KEY, shift=SHIFT)
    g = g[g.history_seasons >= 1].reset_index(drop=True)
    g["vol"] = ((g.yield_lag1 - g.yield_lag2).abs() + (g.yield_lag2 - g.yield_lag3).abs()) / 2 / g.yield_mean3
    return relative(g)


def fit_predict(tr, te, num, cats, leaf, rel=False):
    """Fit on `tr`, predict `te`. In relative mode the model learns yield / anchor - 1 (anchor column `one`)."""
    m = build_model(num, cats, et=dict(min_samples_leaf=leaf, n_estimators=100))
    if rel:
        m.set_params(anchor="one")
        m.fit(tr[num + cats + ["one"]], tr["yield"] / tr["yield_anchor"])
        return m, m.predict(te[num + cats + ["one"]]) * te["yield_anchor"].to_numpy()
    m.fit(tr[num + cats], tr["yield"])
    return m, m.predict(te[num + cats])


def rolling(d, num, cats, leaf, rel=False, label=""):
    """Out-of-sample forecasts for 2016..2024, each from a model trained on rows through Y-LAG only (what is published by then)."""
    out = []
    for yr in TEST_YEARS:
        tr, te = d[d.year <= yr - LAG], d[d.year == yr]
        if len(te) == 0:
            continue
        t0 = time.time()
        _, pred = fit_predict(tr, te, num, cats, leaf, rel)
        row = te[["district_code", "state_name", "crop", "season", "year", "yield", "yield_anchor", "yield_mean3", "vol"]].copy()
        row["pred"] = pred
        row["flag"] = (te["vol"] >= tr["vol"].quantile(0.8)).to_numpy()
        out.append(row)
        print("    %s %d: train %d, test %d (%.0fs)" % (label, yr, len(tr), len(te), time.time() - t0), flush=True)
    return pd.concat(out, ignore_index=True)


def mae(x, col):
    return float(np.abs(x["yield"] - x[col]).mean())


def block(x):
    """MAE of the model and both baselines on identical rows, with skill against each."""
    if len(x) == 0:
        return {"n": 0}
    m, p, b3 = mae(x, "pred"), mae(x, "yield_anchor"), mae(x, "yield_mean3")
    return {"n": int(len(x)), "mae": round(m, 4), "last_published_mae": round(p, 4), "mean3_mae": round(b3, 4),
            "skill_vs_last_published_pct": skill(m, p), "skill_vs_mean3_pct": skill(m, b3)}


def by_year(x):
    return {int(y): skill(mae(s, "pred"), mae(s, "yield_mean3")) for y, s in x.groupby("year")}


def summary(x):
    dev, conf = x[x.year.isin(DEV)], x[x.year == CONFIRM]
    yrs = by_year(dev)
    return {"dev": block(dev), "confirm_2024": block(conf), "dev_by_year_skill_vs_mean3": yrs,
            "years_better_than_mean3": int(sum(v > 0 for v in yrs.values()))}


# ── M1 / M2 ────────────────────────────────────────────────────────────────────────────────────
def staples(d, static):
    num = HIST + (STATIC if static else [])
    out = []
    for name, sel in GROUPS.items():
        g = d[sel(d)].reset_index(drop=True)
        print("  %s: %d rows %s" % (name, len(g), "with static columns" if static else "history only"), flush=True)
        p = rolling(g, num, CATS, leaf=20, label=name)
        p["group"] = name
        out.append(p)
    return pd.concat(out, ignore_index=True)


def old_rows(d, p):
    """Rows the earlier served models trained and were tested on (NDVI at day 120, and weather for Kharif), approximately."""
    ok = (d.lon.notna() & d.ndvi120_max.notna() & ((d.season != "Kharif") | d.wx_rain_sum.notna())).to_numpy()
    keep = set(map(tuple, d.loc[ok, KEY + ["year"]].to_numpy()))
    return p[[tuple(r) in keep for r in p[KEY + ["year"]].to_numpy()]]


def score_m1(d, p):
    res = {g: summary(x) for g, x in p.groupby("group")}
    res_old = {g: summary(old_rows(d, x)) for g, x in p.groupby("group")}
    for g in res:
        print("  %-20s dev n=%d skill vs mean3 %+.1f%% (vs last published %+.1f%%), years better %d/6, 2024 %+.1f%% | old rows: dev %+.1f%%, 2024 %+.1f%%" % (
            g, res[g]["dev"]["n"], res[g]["dev"]["skill_vs_mean3_pct"], res[g]["dev"]["skill_vs_last_published_pct"],
            res[g]["years_better_than_mean3"], res[g]["confirm_2024"]["skill_vs_mean3_pct"],
            res_old[g]["dev"]["skill_vs_mean3_pct"], res_old[g]["confirm_2024"]["skill_vs_mean3_pct"]))
    print("M1 (lag-consistent): reported without a verdict, see Amendment A1")
    return {"groups": res, "old_rows_groups": res_old, "protocol": "lag-consistent"}


def run_m1(d):
    print("\nM1: staples from the master table", flush=True)
    p = staples(d, static=False)
    p.to_parquet(os.path.join(PROC, "master_preds_m1.parquet"), index=False)
    return score_m1(d, p), p


def score_m2(m1_preds, p):
    key = KEY + ["year"]
    j = m1_preds.merge(p[key + ["pred"]], on=key, suffixes=("_hist", "_static"))
    rows = {}
    for label, years in (("dev", DEV), ("confirm_2024", [CONFIRM])):
        s = j[j.year.isin(years)]
        rows[label] = {"mae_history": round(float(np.abs(s["yield"] - s.pred_hist).mean()), 4),
                       "mae_static": round(float(np.abs(s["yield"] - s.pred_static).mean()), 4)}
        rows[label]["gain_pct"] = round(100 * (1 - rows[label]["mae_static"] / rows[label]["mae_history"]), 2)
    yr = {int(y): round(100 * (1 - float(np.abs(s["yield"] - s.pred_static).mean()) / float(np.abs(s["yield"] - s.pred_hist).mean())), 2)
          for y, s in j[j.year.isin(DEV)].groupby("year")}
    ok = rows["dev"]["gain_pct"] >= 2.0 and sum(v > 0 for v in yr.values()) >= 4 and rows["confirm_2024"]["gain_pct"] >= 0
    print("  pooled MAE history-only %.4f vs with static %.4f -> %+.2f%% (dev), by year %s, 2024 %+.2f%%" % (
        rows["dev"]["mae_history"], rows["dev"]["mae_static"], rows["dev"]["gain_pct"], yr, rows["confirm_2024"]["gain_pct"]))
    print("M2: %s" % ("PASS" if ok else "FAIL"))
    return {"pooled": rows, "dev_gain_by_year_pct": yr, "pass": bool(ok), "columns": STATIC}


def run_m2(d, m1_preds):
    print("\nM2: do the static master columns help the staples?", flush=True)
    p = staples(d, static=True)
    p.to_parquet(os.path.join(PROC, "master_preds_m2.parquet"), index=False)
    return score_m2(m1_preds, p)


# ── M3 / M4 ────────────────────────────────────────────────────────────────────────────────────
def pickled_mb(d, leaf):
    tmp = os.path.join(PROC, "_size_probe.pkl")
    m, _ = fit_predict(d, d.head(5), REL_NUM, CATS, leaf, rel=True)
    joblib.dump(m, tmp, compress=3)
    mb = os.path.getsize(tmp) / 1e6
    os.remove(tmp)
    return mb


def conformal_q(rel, level=COVER_LEVEL):
    r = np.sort(np.asarray(rel))
    if len(r) == 0:
        return float("nan")
    return float(r[min(len(r) - 1, math.ceil((len(r) + 1) * level) - 1)])


def intervals(p):
    """Mondrian (by volatility flag) split conformal: year Y is calibrated on year Y-LAG's out-of-sample residuals (the latest known)."""
    p = p.copy()
    p["rel"] = np.abs(p["yield"] - p["pred"]) / np.maximum(p["pred"], 1e-6)
    p["lo"] = p["hi"] = np.nan
    for yr in DEV + [CONFIRM]:
        prev = p[p.year == yr - LAG]
        for flag in (True, False):
            q = conformal_q(prev.loc[prev.flag == flag, "rel"])
            m = (p.year == yr) & (p.flag == flag)
            p.loc[m, "lo"], p.loc[m, "hi"] = p.loc[m, "pred"] * (1 - q), p.loc[m, "pred"] * (1 + q)
    return p


def cover(x):
    x = x.dropna(subset=["lo"])
    return round(float(((x["yield"] >= x.lo) & (x["yield"] <= x.hi)).mean()), 4) if len(x) else None


def coverage_report(ip):
    """Coverage of an interval frame (columns lo, hi, flag, year) on the development years and on 2024."""
    dev = ip.year.isin(DEV)
    return {"dev": cover(ip[dev]), "confirm_2024": cover(ip[ip.year == CONFIRM]),
            "flagged_dev": cover(ip[dev & ip.flag]), "flagged_2024": cover(ip[(ip.year == CONFIRM) & ip.flag]),
            "unflagged_dev": cover(ip[dev & ~ip.flag])}


def coverage_ok(cov):
    return all(v is not None for v in cov.values()) and 0.72 <= cov["dev"] <= 0.88 and 0.72 <= cov["confirm_2024"] <= 0.88 \
        and cov["flagged_dev"] >= 0.70 and cov["flagged_2024"] >= 0.70


def fit_m3(d):
    """Fit and roll every eligible leaf size, keep the most accurate. The pooled error is relative to the anchor, so crops can be pooled."""
    print("\nM3: one pooled relative model for every crop", flush=True)
    sizes = {}
    for leaf in LEAF_SIZES:
        t0 = time.time()
        sizes[leaf] = pickled_mb(d, leaf)
        print("  leaf %3d: full-data pickle %.1f MB (%.0fs)" % (leaf, sizes[leaf], time.time() - t0), flush=True)
    eligible = [l for l in LEAF_SIZES if sizes[l] <= MAX_MODEL_MB]
    results, score = {}, {}
    for leaf in eligible:
        print("  rolling origin, leaf %d" % leaf, flush=True)
        p = rolling(d, REL_NUM, CATS, leaf, rel=True, label="leaf%d" % leaf)
        results[leaf] = p
        dv = p[p.year.isin(DEV)]
        score[leaf] = float((np.abs(dv["yield"] - dv.pred) / dv.yield_anchor).mean())
        print("   leaf %d: pooled MAE relative to the anchor (2018-23) %.4f" % (leaf, score[leaf]), flush=True)
    leaf = min(score, key=score.get)
    results[leaf].to_parquet(os.path.join(PROC, "master_preds_m3.parquet"), index=False)
    fit = {"pickle_mb": {str(k): round(v, 2) for k, v in sizes.items()}, "leaf_score": {str(k): round(v, 4) for k, v in score.items()}, "leaf": leaf}
    with open(os.path.join(PROC, "master_m3_fit.json"), "w") as f:
        json.dump(fit, f, indent=2)
    return results[leaf], fit


def score_m3(p, m1, fit):
    leaf, sizes = fit["leaf"], fit["pickle_mb"]
    print("  chosen leaf %d (%.1f MB)" % (leaf, sizes[str(leaf)]))
    per_crop = {}
    for crop, x in p.groupby("crop"):
        s = summary(x)
        ok = (s["dev"]["n"] >= MIN_TEST_ROWS and s["dev"]["skill_vs_mean3_pct"] >= MIN_SKILL
              and s["years_better_than_mean3"] >= MIN_YEARS and s["confirm_2024"].get("skill_vs_mean3_pct", -1) >= 0)
        per_crop[crop] = {**s, "served": bool(ok)}
    served = sorted(c for c, v in per_crop.items() if v["served"])
    print("  crops tested %d, with >= %d test rows %d, served %d: %s" % (
        len(per_crop), MIN_TEST_ROWS, sum(v["dev"]["n"] >= MIN_TEST_ROWS for v in per_crop.values()), len(served), served))
    group_skill = {}
    for name, sel in GROUPS.items():
        x = p[sel(p)]
        group_skill[name] = summary(x)
        diff = group_skill[name]["dev"]["skill_vs_mean3_pct"] - m1["groups"][name]["dev"]["skill_vs_mean3_pct"]
        group_skill[name]["diff_vs_m1_pts"] = round(diff, 2)
        print("  staples in pooled model: %-20s skill vs mean3 %+.1f%% (M1 %+.1f%%, diff %+.2f)" % (
            name, group_skill[name]["dev"]["skill_vs_mean3_pct"], m1["groups"][name]["dev"]["skill_vs_mean3_pct"], diff))
    replaces = all(abs(v["diff_vs_m1_pts"]) <= 1.0 or v["diff_vs_m1_pts"] > 0 for v in group_skill.values())
    dv = p[p.year.isin(DEV)]
    share_rows = round(float(dv.crop.isin(served).mean()), 4)
    m4 = {"coverage": None, "flagged_over_unflagged_mae": None, "pass": None, "note": "no crop was served, so there is no model range to test"}
    if served:                                    # M4: coverage of the ranges a user would see
        ip = intervals(p[p.crop.isin(served)])
        cov, fd = coverage_report(ip), ip[ip.year.isin(DEV)]
        ratio = mae(fd[fd.flag], "pred") / mae(fd[~fd.flag], "pred")
        m4 = {"coverage": cov, "flagged_over_unflagged_mae": round(ratio, 3), "pass": bool(coverage_ok(cov) and ratio >= 1.3)}
        print("  coverage (served): %s | flagged/unflagged MAE ratio %.2f" % (cov, ratio))
    print("M3: %s (%d crops served; pooled replaces M1 group models: %s)" % ("PASS" if served else "FAIL", len(served), replaces))
    print("M4: %s" % {True: "PASS", False: "FAIL", None: "not applicable (nothing served)"}[m4["pass"]])
    return {"leaf": leaf, "pickle_mb": sizes, "leaf_score": fit["leaf_score"], "per_crop": per_crop, "served": served,
            "served_share_of_test_rows": share_rows, "staples_in_pooled": group_skill, "pooled_replaces_m1": bool(replaces),
            "m4": m4, "pass": bool(served)}


def run_m3(d, m1):
    p, fit = fit_m3(d)
    return score_m3(p, m1, fit), p


# ── B1: the range around the 3-season mean (Amendment A2) ─────────────────────────────────────
MIN_CAL_ROWS = 100


def b1_ranges(d):
    """Out-of-sample 80% ranges around the 3-season mean, year Y calibrated on year Y-LAG, per crop and volatility flag."""
    b = d[["district_code", "state_name", "crop", "season", "year", "yield", "yield_anchor", "yield_mean3", "vol"]].copy()
    b["rel"] = (b["yield"] - b["yield_mean3"]).abs() / b["yield_mean3"]
    out = []
    for yr in DEV + [CONFIRM]:
        thr = d.loc[d.year <= yr - LAG, "vol"].quantile(0.8)
        cal = b[b.year == yr - LAG]
        cal_flag = cal.vol >= thr
        pooled = {f: conformal_q(cal.loc[cal_flag == f, "rel"]) for f in (True, False)}
        per = {}
        for crop, g in cal.groupby("crop"):
            for f in (True, False):
                r = g.loc[(g.vol >= thr) == f, "rel"]
                if len(r) >= MIN_CAL_ROWS:
                    per[(crop, f)] = conformal_q(r)
        te = b[b.year == yr].copy()
        te["flag"] = (te.vol >= thr).to_numpy()
        te["q"] = [per.get((c, f), pooled[f]) for c, f in zip(te.crop, te.flag)]
        te["lo"], te["hi"] = te.yield_mean3 * (1 - te.q), te.yield_mean3 * (1 + te.q)
        out.append(te)
    return pd.concat(out, ignore_index=True)


def run_b1(d):
    print("\nB1: range around the 3-season mean", flush=True)
    ip = b1_ranges(d)
    cov = coverage_report(ip)
    dev = ip[ip.year.isin(DEV)]
    per_crop = {}
    for crop, x in dev.groupby("crop"):
        m3_, last = mae(x, "yield_mean3"), mae(x, "yield_anchor")
        per_crop[crop] = {"n": int(len(x)), "mean3_mae": round(m3_, 4), "last_published_mae": round(last, 4), "mean3_vs_last_published_pct": skill(m3_, last)}
    wins = sum(v["mean3_vs_last_published_pct"] > 0 for v in per_crop.values())
    ok = coverage_ok(cov)
    print("  coverage: %s" % cov)
    print("  the 3-season mean beat the last published season for %d of %d crops (pooled over rows: %+.1f%% error)" % (
        wins, len(per_crop), skill(mae(dev, "yield_mean3"), mae(dev, "yield_anchor"))))
    print("B1: %s" % ("PASS" if ok else "FAIL"))
    return {"coverage": cov, "pass": bool(ok), "per_crop": per_crop, "crops_mean3_beats_last": int(wins), "crops": len(per_crop)}, ip


def rescore(d):
    """Recompute every result from the saved forecasts (no refit)."""
    m1p = pd.read_parquet(os.path.join(PROC, "master_preds_m1.parquet"))
    m2p = pd.read_parquet(os.path.join(PROC, "master_preds_m2.parquet"))
    m3p = pd.read_parquet(os.path.join(PROC, "master_preds_m3.parquet"))
    with open(os.path.join(PROC, "master_m3_fit.json")) as f:
        fit = json.load(f)
    m1 = score_m1(d, m1p)
    return {"m1": m1, "m2": score_m2(m1p, m2p), "m3": score_m3(m3p, m1, fit), "b1": run_b1(d)[0]}


def main():
    steps = sys.argv[1:] or ["m1", "m2", "m3", "b1"]
    d = load()
    print("forecastable rows %d | crops %d | districts %d | years %d-%d" % (len(d), d.crop.nunique(), d.district_code.nunique(), d.year.min(), d.year.max()), flush=True)
    path = os.path.join(PROC, "master_models_metrics.json")
    metrics = json.load(open(path)) if os.path.exists(path) else {}
    if steps == ["score"]:
        metrics.update(rescore(d))
    else:
        m1p = None
        if set(steps) & {"m1", "m2", "m3"}:
            metrics["m1"], m1p = run_m1(d)
        if "m2" in steps:
            metrics["m2"] = run_m2(d, m1p)
        if "m3" in steps:
            metrics["m3"], _ = run_m3(d, metrics["m1"])
        if "b1" in steps:
            metrics["b1"], _ = run_b1(d)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    print("\nwrote", path)


if __name__ == "__main__":
    main()

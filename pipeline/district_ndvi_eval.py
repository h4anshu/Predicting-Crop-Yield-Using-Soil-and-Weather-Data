"""
Phase 1A, step 9: does satellite NDVI help, and how early? (criteria C5a / C5b in PRODUCTION_ROADMAP.md)

    python pipeline/district_ndvi_eval.py

Two groups, one model each: Wheat (Rabi) and Kharif Rice + Maize. Rolling origin 2018-2023, each test year trained
on earlier years only, identical rows for every model compared (rows need NDVI at every lead time).

  history              district yield history only
  + weather            history + fixed-window season weather (as in C3)
  + weather + NDVI     the above plus full-season NDVI/EVI              -> C5a ceiling, vs "+ weather"
  history + NDVI @60   history plus NDVI seen in the first 60 days      -> C5b, vs "history"
  history + NDVI @90 / @120 / full   reported, not scored

NDVI features are raw and as anomalies from the district-crop-season norm over the training years only.
"""

import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import district_weather_eval as E  # noqa: E402
from district_baseline import CATS, NUM as HIST_NUM, TEST_FROM, LAST_YEAR  # noqa: E402
from train_v3 import build_model, skill  # noqa: E402

PROC = os.path.join(ROOT, "data", "processed")
OUT = os.path.join(PROC, "district_ndvi_eval.json")
NDVI = ["ndvi_max", "ndvi_mean", "ndvi_int", "evi_max", "evi_mean"]
KEYS = ["shape_id", "crop", "season"]
LEADS = [60, 90, 120, 999]
GROUPS = {"Wheat (Rabi)": ((lambda d: (d.crop == "Wheat") & (d.season == "Rabi")), "Rabi"),
          "Kharif Rice + Maize": ((lambda d: d.crop.isin(["Rice", "Maize"]) & (d.season == "Kharif")), "Kharif")}


def assemble():
    d, fixed = E.assemble()
    sn = pd.read_parquet(os.path.join(PROC, "season_ndvi.parquet"))
    return d, fixed, sn


def attach(sub, sn, window):
    for lead in LEADS:
        part = sn[(sn.window == window) & (sn.lead == lead)][["shape_id", "year"] + NDVI]
        part.columns = ["shape_id", "year"] + ["n%s_%s" % (lead, c) for c in NDVI]
        sub = sub.merge(part, on=["shape_id", "year"], how="left")
    return sub


def run_group(name, sub, fixed, sn, window):
    sub = attach(sub, sn, window)
    must = ["n%s_ndvi_max" % l for l in LEADS]
    sub = sub.dropna(subset=must).reset_index(drop=True)
    print("\n%s: %d rows, %d districts, years %d-%d" % (name, len(sub), sub.district_code.nunique(), sub.year.min(), sub.year.max()), flush=True)
    ncols = {l: ["n%s_%s" % (l, c) for c in NDVI] for l in LEADS}
    allcols = fixed + [c for l in LEADS for c in ncols[l]]
    fw = fixed + [c + "_anom" for c in fixed]
    nv = lambda l: ncols[l] + [c + "_anom" for c in ncols[l]]  # noqa: E731
    sets = {"history": HIST_NUM, "+ weather": HIST_NUM + fw, "+ weather + NDVI": HIST_NUM + fw + nv(999),
            "history + NDVI@60": HIST_NUM + nv(60), "history + NDVI@90": HIST_NUM + nv(90),
            "history + NDVI@120": HIST_NUM + nv(120), "history + NDVI full": HIST_NUM + nv(999)}
    tot = {k: 0.0 for k in sets}
    n_tot, rows = 0, []
    for yr in range(TEST_FROM, LAST_YEAR + 1):
        d = sub.join(sub[sub.year < yr].groupby(KEYS)[allcols].mean().add_suffix("_n"), on=KEYS)
        for c in allcols:
            d[c + "_anom"] = d[c] - d[c + "_n"]
        tr, te = d[d.year < yr], d[d.year == yr]
        res = {}
        for k, num in sets.items():
            m = build_model(num, CATS).fit(tr[num + CATS], tr["yield"])
            res[k] = float(np.abs(te["yield"] - m.predict(te[num + CATS])).mean())
            tot[k] += res[k] * len(te)
        n_tot += len(te)
        rows.append({"year": yr, "n": int(len(te)), **{k: round(v, 4) for k, v in res.items()},
                     "ndvi_full_over_weather_pct": skill(res["+ weather + NDVI"], res["+ weather"]),
                     "ndvi60_over_history_pct": skill(res["history + NDVI@60"], res["history"])})
        print("  %d n=%4d history %.4f | +weather %.4f | +w+NDVI %.4f (%+.1f%% vs +w) | NDVI@60 %.4f (%+.1f%% vs hist) | @90 %.4f | @120 %.4f | full %.4f" % (
            yr, len(te), res["history"], res["+ weather"], res["+ weather + NDVI"], rows[-1]["ndvi_full_over_weather_pct"],
            res["history + NDVI@60"], rows[-1]["ndvi60_over_history_pct"], res["history + NDVI@90"], res["history + NDVI@120"],
            res["history + NDVI full"]), flush=True)
    pooled = {k: round(v / n_tot, 4) for k, v in tot.items()}
    a = skill(pooled["+ weather + NDVI"], pooled["+ weather"])
    b = skill(pooled["history + NDVI@60"], pooled["history"])
    wa = sum(r["ndvi_full_over_weather_pct"] > 0 for r in rows)
    wb = sum(r["ndvi60_over_history_pct"] > 0 for r in rows)
    lead_skill = {k: skill(pooled[k], pooled["history"]) for k in pooled}
    print("  pooled MAE:", pooled)
    print("  skill vs history:", lead_skill)
    print("  C5a input: NDVI over +weather %+.1f%% (better %d/6) | C5b input: NDVI@60 over history %+.1f%% (better %d/6)" % (a, wa, b, wb))
    return {"n_rows": int(len(sub)), "pooled_mae": pooled, "skill_vs_history_pct": lead_skill,
            "C5a_pct": a, "C5a_years": wa, "C5b_pct": b, "C5b_years": wb, "years": rows}


def main():
    d, fixed, sn = assemble()
    out = {name: run_group(name, d[sel(d)], fixed, sn, window) for name, (sel, window) in GROUPS.items()}
    out["C5a"] = bool(any(g["C5a_pct"] >= 3.0 and g["C5a_years"] >= 4 for g in out.values()))
    out["C5b"] = bool(any(g["C5b_pct"] >= 2.0 and g["C5b_years"] >= 4 for g in out.values() if isinstance(g, dict)))
    print("\nC5a (NDVI over history+weather >= +3.0%% and >= 4/6 years, in at least one group): %s" % ("PASS" if out["C5a"] else "FAIL"))
    print("C5b (NDVI@60 over history   >= +2.0%% and >= 4/6 years, in at least one group): %s" % ("PASS" if out["C5b"] else "FAIL"))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print("wrote %s" % OUT)


if __name__ == "__main__":
    main()

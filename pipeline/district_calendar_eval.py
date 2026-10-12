"""
Phase 1A, step 8: do calendar-aligned weather windows beat fixed ones? (criteria C4a / C4b in PRODUCTION_ROADMAP.md)

    python pipeline/district_calendar_eval.py

One model per group, rolling origin over 2018-2023 (each test year trained only on earlier years), the same
rows for every model compared:
  history          district yield history only
  fixed weather    + the fixed national-window season weather used in C3 (raw + anomalies)
  calendar weather + SAGE planting-to-harvest window weather (raw + anomalies, incl. last-30-days heat)
  calendar + static + irrigation / cropping intensity / fertilizer from ICRISAT

Groups: Wheat (Rabi), and Kharif Rice + Maize. Same caveat as C3: realised in-season weather is an upper bound on
what a real forecast can use. Anomalies use each district-crop-season's mean over the training years only.
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
OUT = os.path.join(PROC, "district_calendar_eval.json")
CAL = ["c_rain_sum", "c_rain_days", "c_rain_first30", "c_rain_pre60", "c_dry_spell_max", "c_tmax_mean",
       "c_tmin_mean", "c_hot_days", "c_rh_mean", "c_sw_mean", "c_tmax_last30", "c_hot_last30"]
KEYS = ["shape_id", "crop", "season"]
GROUPS = {"Wheat (Rabi)": lambda d: (d.crop == "Wheat") & (d.season == "Rabi"),
          "Kharif Rice + Maize": lambda d: d.crop.isin(["Rice", "Maize"]) & (d.season == "Kharif")}


def assemble():
    d, fixed = E.assemble()
    d["kind"] = np.select([(d.crop == "Rice") & (d.season == "Kharif"), (d.crop == "Rice") & d.season.isin(["Rabi", "Summer"]),
                           (d.crop == "Wheat") & (d.season == "Rabi"), (d.crop == "Maize") & (d.season == "Kharif")],
                          ["main", "second", "main", "main"], default="")
    cw = pd.read_parquet(os.path.join(PROC, "calendar_weather.parquet")).drop(columns=["plant_doy", "harvest_doy", "window_days"])
    d = d.merge(cw, on=["shape_id", "year", "crop", "kind"], how="left")
    return d, fixed


def run_group(name, sub, fixed):
    sub = sub.dropna(subset=["c_rain_sum", "c_tmax_mean"]).reset_index(drop=True)
    print("\n%s: %d rows, %d districts" % (name, len(sub), sub.district_code.nunique()), flush=True)
    fw = fixed + [c + "_anom" for c in fixed]
    cw = CAL + [c + "_anom" for c in CAL]
    sets = {"history": HIST_NUM, "fixed weather": HIST_NUM + fw, "calendar weather": HIST_NUM + cw,
            "calendar + static": HIST_NUM + cw + E.STATIC}
    tot = {k: 0.0 for k in sets}
    n_tot, rows = 0, []
    for yr in range(TEST_FROM, LAST_YEAR + 1):
        d = sub.join(sub[sub.year < yr].groupby(KEYS)[fixed + CAL].mean().add_suffix("_n"), on=KEYS)
        for c in fixed + CAL:
            d[c + "_anom"] = d[c] - d[c + "_n"]
        tr, te = d[d.year < yr], d[d.year == yr]
        res = {}
        for k, num in sets.items():
            m = build_model(num, CATS).fit(tr[num + CATS], tr["yield"])
            res[k] = float(np.abs(te["yield"] - m.predict(te[num + CATS])).mean())
            tot[k] += res[k] * len(te)
        n_tot += len(te)
        row = {"year": yr, "n": int(len(te)), **{k.replace(" ", "_").replace("+", "and"): round(v, 4) for k, v in res.items()},
               "calendar_vs_history_pct": skill(res["calendar weather"], res["history"]),
               "fixed_vs_history_pct": skill(res["fixed weather"], res["history"])}
        rows.append(row)
        print("  %d n=%4d history %.4f | fixed %.4f (%+.1f%%) | calendar %.4f (%+.1f%%) | +static %.4f (%+.1f%%)" % (
            yr, len(te), res["history"], res["fixed weather"], row["fixed_vs_history_pct"], res["calendar weather"],
            row["calendar_vs_history_pct"], res["calendar + static"], skill(res["calendar + static"], res["history"])), flush=True)
    pooled = {k: round(v / n_tot, 4) for k, v in tot.items()}
    sk = {k: skill(v, pooled["history"]) for k, v in pooled.items()}
    wins = sum(r["calendar_vs_history_pct"] > 0 for r in rows)
    print("  pooled MAE:", pooled)
    print("  pooled skill vs history:", sk, "| calendar better in %d/%d years" % (wins, len(rows)))
    return {"n_rows": int(len(sub)), "pooled_mae": pooled, "pooled_skill_vs_history_pct": sk,
            "calendar_years_better": wins, "years": rows}


def main():
    d, fixed = assemble()
    out = {name: run_group(name, d[sel(d)], fixed) for name, sel in GROUPS.items()}
    w, k = out["Wheat (Rabi)"], out["Kharif Rice + Maize"]
    out["C4a"] = bool(w["pooled_skill_vs_history_pct"]["calendar weather"] >= 1.0 and w["calendar_years_better"] >= 4)
    out["C4b"] = bool(k["pooled_skill_vs_history_pct"]["calendar weather"] >= 2.5 and k["calendar_years_better"] >= 4)
    print("\nC4a (Wheat: calendar >= +1.0%% and >= 4/6 years):        %s  [%+.1f%%, %d/6]" % (
        "PASS" if out["C4a"] else "FAIL", w["pooled_skill_vs_history_pct"]["calendar weather"], w["calendar_years_better"]))
    print("C4b (Kharif Rice+Maize: calendar >= +2.5%% and >= 4/6):  %s  [%+.1f%%, %d/6]" % (
        "PASS" if out["C4b"] else "FAIL", k["pooled_skill_vs_history_pct"]["calendar weather"], k["calendar_years_better"]))
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print("wrote %s" % OUT)


if __name__ == "__main__":
    main()

"""
Phase 5: can the served models be much smaller without losing accuracy?
Criteria in PRODUCTION_ROADMAP.md ("Model size for serving"), written before this ran.

    python pipeline/shrink_experiment.py

For each Extra Trees configuration: rolling-origin forecasts at lead 0 under the one-season publication lag (Gate G1,
2018-2024), pooled MAE on 2018-23 and on 2024, and the size of the two group models fitted on every season and pickled
with compress=3 (what would be committed). Writes data/processed/shrink_experiment.json.
"""

import functools
import json
import os
import sys
import tempfile

import joblib
import numpy as np

os.environ["HIST_SHIFT"] = "1"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
import phase2_forecast as P2  # noqa: E402
from train_v3 import build_model as base_build  # noqa: E402

P2.FIT_LEADS = [0]
CONFIGS = {
    "current (leaf 2, 200 trees)": dict(),
    "leaf 5, 200 trees": dict(min_samples_leaf=5),
    "leaf 5, 100 trees": dict(min_samples_leaf=5, n_estimators=100),
    "leaf 10, 100 trees": dict(min_samples_leaf=10, n_estimators=100),
    "leaf 20, 100 trees": dict(min_samples_leaf=20, n_estimators=100),
}
OUT = os.path.join(ROOT, "data", "processed", "shrink_experiment.json")


def evaluate(cfg, g):
    P2.build_model = functools.partial(base_build, et=cfg)
    P = np.concatenate([P2.run_group(n, s, g).assign(_g=n).to_records(index=False) for n, s in P2.GROUPS.items()])
    import pandas as pd
    P = pd.DataFrame(P)
    dev, c24 = P[P.year.isin(P2.DEV_YEARS)], P[P.year == P2.CONFIRM]
    return {"mae_dev": float((dev["yield"] - dev.pred).abs().mean()), "mae_2024": float((c24["yield"] - c24.pred).abs().mean())}


def size_mb(cfg, g):
    total = 0.0
    for name, spec in P2.GROUPS.items():
        d = P2.attach(g[spec["sel"](g)], spec["window"], spec["weather"])
        d = d.dropna(subset=P2.lead_cols(120, spec["weather"])).reset_index(drop=True)
        m = base_build(P2.HIST, P2.CATS, True, et=cfg).fit(d[P2.HIST + P2.CATS], d["yield"])
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
            path = f.name
        joblib.dump(m, path, compress=3)
        total += os.path.getsize(path) / 1e6
        os.remove(path)
    return total


def main():
    g = P2.load()
    out = {}
    for name, cfg in CONFIGS.items():
        r = evaluate(cfg, g)
        r["size_mb"] = round(size_mb(cfg, g), 1)
        out[name] = r
        print("%-30s size %5.1f MB | MAE 2018-23 %.4f | MAE 2024 %.4f" % (name, r["size_mb"], r["mae_dev"], r["mae_2024"]), flush=True)
    ref = out["current (leaf 2, 200 trees)"]
    for name, r in out.items():
        r["dev_vs_current_pct"] = round(100 * (r["mae_dev"] / ref["mae_dev"] - 1), 2)
        r["y2024_vs_current_pct"] = round(100 * (r["mae_2024"] / ref["mae_2024"] - 1), 2)
        r["accepted"] = bool(r["size_mb"] <= 15 and r["dev_vs_current_pct"] <= 1.0 and r["y2024_vs_current_pct"] <= 1.5)
    ok = {k: v for k, v in out.items() if v["accepted"]}
    best = min(ok, key=lambda k: ok[k]["mae_dev"]) if ok else None
    print("\naccepted:", list(ok), "| chosen (most accurate on 2018-23 among accepted):", best)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"results": out, "chosen": best}, f, indent=2)


if __name__ == "__main__":
    main()

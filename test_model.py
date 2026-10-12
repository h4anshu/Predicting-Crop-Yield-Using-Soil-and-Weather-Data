"""
Guards the v3.1 model's contract. Run after any retrain:  python test_model.py

What this file protects, in order of how badly it hurts when it breaks:

  1. No lookahead. A row's history features must come from strictly earlier seasons.
     The dataset's own yield_ma2 / yield_change columns contain the current season's
     yield (94.9% of rows); a model trained on them looks superb and forecasts nothing.
  2. The forecast is driven by the series' own history -- the property v3 lacked.
  3. The metrics file reports every score against baselines, and says so consistently.
  4. The model is not catastrophically worse than repeating last season. It currently
     IS worse (see the skill figure printed below); this only fails on a collapse.
"""

import json
import os
import joblib
import numpy as np
import pandas as pd

from features import add_derived, build_row
from forecasting import HISTORY_FEATURES, add_history, build_panel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(BASE_DIR, "crop_yield_model_v3.pkl")
METRICS = os.path.join(BASE_DIR, "model_metrics.json")
DATA = os.path.join(BASE_DIR, "master_dataset_enhanced.csv")

STAPLES = ["Rice", "Wheat", "Maize", "Gram", "Onion", "Potato"]
LEAKY_COLUMNS = ["yield_ma2", "yield_change"]   # raw-CSV columns that contain the target
MIN_ACCEPTABLE_SKILL_PCT = -25.0   # measured -9.6 at v3.1; fail only if it collapses


def load():
    data = pd.read_csv(DATA)
    for c in ("crop", "season", "state"):
        data[c] = data[c].str.strip()
    return data[data["crop"] != "Coconut"].reset_index(drop=True)


def check_contract(model, metrics):
    feats = list(model.feature_names_in_)
    assert "state" in feats and "crop" in feats and "season" in feats
    for h in HISTORY_FEATURES:
        assert h in feats, "history feature %s missing from the model" % h
    for col in LEAKY_COLUMNS:
        assert col not in feats, "%s leaks the current season's yield" % col
    assert "Coconut" in metrics["data_quality"]["excluded_crops"]
    print("  contract: state + %d history features in, %s out" % (len(HISTORY_FEATURES), LEAKY_COLUMNS))


def check_no_lookahead(data, panel):
    """Poison every yield from the cut year onward; features of cut-year rows must not move."""
    cut = 2010
    rows = add_derived(data[data.year == cut])
    clean = add_history(rows, panel)

    poisoned = panel.copy()
    poisoned[poisoned.index.get_level_values("year") >= cut] = 999.0
    dirty = add_history(rows, poisoned)
    pd.testing.assert_frame_equal(clean[HISTORY_FEATURES], dirty[HISTORY_FEATURES])

    # and the lag really is the previous calendar year's recorded value
    r = clean[clean.history_seasons == 3].iloc[0]
    for k in (1, 2, 3):
        assert r["yield_lag%d" % k] == panel[(r.state, r.crop, r.season, cut - k)]
    print("  no lookahead: %d rows unchanged when every yield from %d on is poisoned" % (len(rows), cut))


def check_history_drives_forecast(model, data, panel):
    """Scale every recorded yield by 1.5 and the forecast must follow. Without this
    property the model is back to ignoring the series it is forecasting."""
    rows = data[(data.year == 2019) & data.crop.isin(STAPLES)]
    feats = list(model.feature_names_in_)
    rows = add_history(add_derived(rows), panel)
    rows = rows[rows.history_seasons >= 1]
    base = model.predict(rows[feats])
    up = model.predict(add_history(add_derived(rows.drop(columns=HISTORY_FEATURES)), panel * 1.5)[feats])
    pct = float(np.median(100 * (up - base) / np.maximum(base, 1e-9)))
    assert pct > 25, "forecast moved only %.1f%% when all history rose 50%%" % pct
    print("  history drives the forecast: +50%% history -> median +%.0f%% forecast (%d rows)" % (pct, len(rows)))
    return rows, feats


def check_field_inputs(model, rows, feats):
    """Informational. Soil is constant per state and the model is anchored on history,
    so field inputs are expected to move the forecast very little; this prints how little
    so a surprise in either direction is visible. Only sanity is asserted."""
    for col, lo, hi in [("total_rainfall_mm", 300, 3000), ("N", 20, 160), ("P", 10, 90), ("pH", 4.5, 8.5)]:
        a, b = rows.copy(), rows.copy()
        a[col], b[col] = lo, hi
        v0 = model.predict(add_derived(a)[feats])
        v1 = model.predict(add_derived(b)[feats])
        assert np.isfinite(v0).all() and np.isfinite(v1).all() and (v0 >= 0).all() and (v1 >= 0).all()
        print("  %-18s %s -> %-5s median move %5.2f%%" % (
            col, lo, hi, float(np.median(100 * np.abs(v1 - v0) / np.maximum(v0, 1e-9)))))


def check_real_forecast(model, data, panel):
    feats = list(model.feature_names_in_)
    r = data[(data.state == "Punjab") & (data.crop == "Wheat") & (data.year == 2019)].iloc[0]
    payload = {k: r[k] for k in ("state", "crop", "season", "year", "N", "P", "K", "pH", "avg_temp_c",
                                 "total_rainfall_mm", "avg_humidity_percent", "fertilizer_per_ha",
                                 "pesticide_per_ha")}
    pred = float(model.predict(build_row(payload, feats, panel))[0])
    assert 0 < pred < 120, "implausible yield: %r" % pred
    print("  Punjab wheat 2019: forecast %.2f t/ha (recorded %.2f)" % (pred, r["yield"]))


def check_metrics(metrics):
    b, sk = metrics["baselines"], metrics["skill"]
    assert set(b) == {"crop_mean", "series_mean", "mean_3yr", "persistence"}
    best = min(b, key=lambda n: b[n]["mae"])
    assert sk["best_baseline"] == best, "skill is not measured against the strongest baseline"
    expect = round(100 * (1 - metrics["headline"]["mae"] / b[best]["mae"]), 1)
    assert abs(sk["vs_best_baseline_pct"] - expect) < 0.11, "skill figure does not follow from the MAEs"
    assert all(b[n]["n"] == metrics["headline"]["n"] for n in b), "baselines scored on different rows"
    assert len(metrics["rolling_origin"]) >= 3 and metrics["leave_states_out"]["model"]["n"] > 1000
    assert metrics["data_quality"]["leakage"]["yield_ma2_contains_target_pct"] > 90
    assert metrics["core_staples"]["r2"] < metrics["headline"]["r2"], \
        "core-staples R2 should be the lower, more conservative number"
    assert metrics["data_quality"]["known_ceiling"]
    assert len(metrics["per_crop"]) > 20 and len(metrics["scatter"]) > 100
    assert sk["vs_best_baseline_pct"] >= MIN_ACCEPTABLE_SKILL_PCT, (
        "model MAE %.3f is %.1f%% against %s (floor %.0f%%): retrain has regressed"
        % (metrics["headline"]["mae"], sk["vs_best_baseline_pct"], best, MIN_ACCEPTABLE_SKILL_PCT))
    return best


def main():
    model = joblib.load(MODEL)
    metrics = json.load(open(METRICS, encoding="utf-8"))
    data = load()
    panel = build_panel(data)

    print("model contract")
    check_contract(model, metrics)
    check_no_lookahead(data, panel)
    rows, feats = check_history_drives_forecast(model, data, panel)
    check_real_forecast(model, data, panel)
    print("field-input response (expected to be small)")
    check_field_inputs(model, rows, feats)
    best = check_metrics(metrics)

    h, sk = metrics["headline"], metrics["skill"]
    print("\nholdout MAE %.3f | best baseline (%s) MAE %.3f | skill %+.1f%%"
          % (h["mae"], best, metrics["baselines"][best]["mae"], sk["vs_best_baseline_pct"]))
    print("all model checks passed")


if __name__ == "__main__":
    main()

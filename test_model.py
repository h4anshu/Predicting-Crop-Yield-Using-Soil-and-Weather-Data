"""
Guards the v3 model's contract. Run after any retrain:  python test_model.py

The sensitivity assertions are the point of this file. Accuracy alone cannot catch a
model that scores well while ignoring the inputs the user can actually move -- v2's
pH response was 1.1%, so that control was very nearly decorative -- so responsiveness
is asserted directly.

Two methodology notes, both learned the hard way:
  - Perturb through features.add_derived(). Setting a raw column alone leaves its
    derived children stale and makes a live model look dead.
  - Measure over many rows and take the median. A single row is far too noisy to
    characterise a tree ensemble.
"""

import json
import os
import joblib
import numpy as np
import pandas as pd

from features import add_derived

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.join(BASE_DIR, "crop_yield_model_v3.pkl")
METRICS = os.path.join(BASE_DIR, "model_metrics.json")
DATA = os.path.join(BASE_DIR, "master_dataset_enhanced.csv")

STAPLES = ["Rice", "Wheat", "Maize", "Gram", "Onion", "Potato"]


def sample_fields(data, n=200):
    """A stable sample of real staple rows to perturb."""
    sub = data[data["crop"].isin(STAPLES)]
    idx = np.random.default_rng(0).choice(len(sub), min(n, len(sub)), replace=False)
    return sub.iloc[idx]


def median_response(model, rows, feats, col, lo, hi):
    a, b = rows.copy(), rows.copy()
    a[col], b[col] = lo, hi
    v0 = model.predict(add_derived(a)[feats])
    v1 = model.predict(add_derived(b)[feats])
    return float(np.median(100 * np.abs(v1 - v0) / np.maximum(v0, 1e-9)))


def main():
    model = joblib.load(MODEL)
    metrics = json.load(open(METRICS, encoding="utf-8"))
    data = pd.read_csv(DATA)
    data["crop"] = data["crop"].str.strip()
    data["season"] = data["season"].str.strip()
    feats = list(model.feature_names_in_)

    # 1. `state` must stay out: with it, the trees ignore the agronomic inputs.
    assert "state" not in feats, "state leaked back into the feature set"
    assert "crop" in feats and "season" in feats

    # 2. Coconut is nuts/ha inside a tonnes/ha column -- it must not be predictable.
    assert "Coconut" in metrics["data_quality"]["excluded_crops"]

    # 3. Model produces a sane number for a real field.
    rows = sample_fields(data)
    base = float(model.predict(add_derived(rows.iloc[0:1])[feats])[0])
    assert 0 < base < 120, "implausible yield: %r" % base

    # 4. The regression that motivated v3: inputs must actually move the forecast.
    #    Floors sit well under the measured medians (rain 5.2, N 33.8, P 59.2,
    #    pH 6.4) so retraining noise will not trip them, while a slide back toward
    #    v2's inert pH (1.1%) fails loudly.
    for col, lo, hi, floor in [
        ("total_rainfall_mm", 300, 3000, 2.0),
        ("N", 20, 160, 10.0),
        ("P", 10, 90, 20.0),
        ("pH", 4.5, 8.5, 3.0),
    ]:
        pct = median_response(model, rows, feats, col, lo, hi)
        assert pct >= floor, (
            "%s is inert: %s->%s moves the forecast %.2f%% (need >=%.1f%%). "
            "The model has stopped responding to field inputs." % (col, lo, hi, pct, floor)
        )
        print("  %-20s %s -> %-5s median move %6.2f%%  OK" % (col, lo, hi, pct))

    # 5. Metrics file must carry the honest breakdown, not just the headline.
    assert metrics["core_staples"]["r2"] < metrics["headline"]["r2"], \
        "core-staples R2 should be the lower, more conservative number"
    assert metrics["data_quality"]["known_ceiling"]
    assert len(metrics["per_crop"]) > 20 and len(metrics["scatter"]) > 100

    print("\nheadline R2 %.4f | core staples R2 %.4f | CV MAE %.3f"
          % (metrics["headline"]["r2"], metrics["core_staples"]["r2"], metrics["cv"]["mae_mean"]))
    print("all model checks passed")


if __name__ == "__main__":
    main()

"""
Retrain the crop-yield model (v3) and emit the evaluation artifacts that the
Model Performance page consumes.

Two deliberate changes from v2, both documented in model_metrics.json:

  1. `state` is dropped as a feature. Soil and weather are state-level constants in
     this dataset -- every crop sharing a state-year carries an identical input
     vector -- so `state` was a cleaner split than any agronomic column and the trees
     leaned on it. Removing it forces the model to locate a field from its soil and
     climate instead. Measured over 200 held-out staple rows (see sensitivity()),
     every input becomes more responsive, pH most of all:

         input      v2      v3
         pH       1.13%   6.35%     <- was effectively inert
         temp     2.43%   4.71%
         rain     2.77%   5.24%
         K       16.12%  26.98%
         P       43.39%  59.22%
         N       32.71%  33.78%

     N and P already worked in v2; pH and temperature did not. Note that this buys
     regional responsiveness, not field-level -- see data_quality.known_ceiling.

  2. Coconut is excluded. It is recorded in nuts/ha inside a tonnes/ha column, and
     the enhanced dataset's winsorisation at 104.2734 pinned 164 of its 172 rows to
     one identical value -- so v2 scored a fake MAE of 0.000 on it while it carried
     38% of total feature importance. Sugarcane is KEPT: its ~51 t/ha is real
     agronomy, not a unit error. Metrics are reported with and without it.

Evaluation uses a temporal holdout (train <2018, test 2018-2020). The shipped model
is then refit on all years -- standard practice, and stated in the metrics file so the
reported numbers are never confused with the shipped artifact's training set.

    python train_v3.py
"""

import json
import os
import numpy as np
import pandas as pd
import joblib
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.metrics import r2_score, mean_absolute_error, mean_squared_error
from sklearn.model_selection import cross_val_score, KFold

from features import add_derived

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE_DIR, "master_dataset_enhanced.csv")
OUT_MODEL = os.path.join(BASE_DIR, "crop_yield_model_v3.pkl")
OUT_METRICS = os.path.join(BASE_DIR, "model_metrics.json")

EXCLUDED_CROPS = ["Coconut"]     # unit inconsistency, see module docstring
SCALE_OUTLIERS = ["Sugarcane"]   # legitimate but high-magnitude; reported separately
TEST_FROM_YEAR = 2018

NUM = [
    'year', 'avg_temp_c', 'total_rainfall_mm', 'avg_humidity_percent', 'N', 'P', 'K', 'pH',
    'fertilizer_per_ha', 'pesticide_per_ha', 'NPK_total', 'N_to_P_ratio', 'N_to_K_ratio',
    'P_to_K_ratio', 'NPK_balance_score', 'temp_rainfall_interaction',
    'temp_humidity_interaction', 'moisture_index', 'growing_degree_days', 'pH_optimal',
    'soil_fertility_score', 'fertilizer_rainfall_ratio', 'pesticide_efficiency',
    'input_intensity', 'years_since_start',
]
CATS = ['crop', 'season']
FEATURES = NUM + CATS


def build_pipeline():
    return Pipeline([
        ('preprocessing', ColumnTransformer([
            ('num', Pipeline([
                ('imputer', SimpleImputer(strategy='median')),
                ('scaler', StandardScaler()),
            ]), NUM),
            ('cat', Pipeline([
                ('imputer', SimpleImputer(strategy='most_frequent')),
                ('encoder', OneHotEncoder(handle_unknown='ignore')),
            ]), CATS),
        ])),
        ('model', ExtraTreesRegressor(
            n_estimators=200, max_depth=20, min_samples_split=5,
            min_samples_leaf=2, random_state=42, n_jobs=-1,
        )),
    ])


def scores(y, pred):
    return {
        "r2": round(float(r2_score(y, pred)), 4),
        "mae": round(float(mean_absolute_error(y, pred)), 4),
        "rmse": round(float(np.sqrt(mean_squared_error(y, pred))), 4),
        "n": int(len(y)),
    }


SWEEPS = [
    ('total_rainfall_mm', 300, 3000, 'mm'),
    ('N', 20, 160, 'kg/ha'),
    ('P', 10, 90, 'kg/ha'),
    ('K', 8, 60, 'kg/ha'),
    ('pH', 4.5, 8.5, 'pH'),
    ('avg_temp_c', 18, 36, 'C'),
]


def sensitivity(pipe, rows, feats):
    """How much the forecast moves across a realistic sweep of each field input.

    Measured over many rows and reported as a median: a single row is far too
    noisy to characterise a tree ensemble, and an unlucky one can make a
    responsive model look dead (or the reverse).

    Derived columns are rebuilt from the perturbed raw value via features.py.
    Skipping that step is the trap -- rainfall also feeds moisture_index,
    temp_rainfall_interaction and fertilizer_rainfall_ratio, so perturbing the raw
    column alone leaves the model reading three stale copies of the old value and
    understates its true response.
    """
    out = {}
    for col, lo, hi, unit in SWEEPS:
        a, b = rows.copy(), rows.copy()
        a[col], b[col] = lo, hi
        v0 = pipe.predict(add_derived(a)[feats])
        v1 = pipe.predict(add_derived(b)[feats])
        pct = 100 * np.abs(v1 - v0) / np.maximum(v0, 1e-9)
        out[col] = {
            "from": lo, "to": hi, "unit": unit,
            "median_pct_change": round(float(np.median(pct)), 2),
            "p25": round(float(np.percentile(pct, 25)), 2),
            "p75": round(float(np.percentile(pct, 75)), 2),
            "n_rows": int(len(rows)),
        }
    return out


def grouped_importance(pipe):
    """One-hot columns are summed back into their source feature, otherwise
    `crop` looks like 55 weak features instead of one dominant one."""
    names = pipe.named_steps['preprocessing'].get_feature_names_out()
    imp = pipe.named_steps['model'].feature_importances_
    agg = {}
    for n, v in zip(names, imp):
        key = n.split('__', 1)[1]
        if n.startswith('cat__'):
            key = key.split('_')[0]
        agg[key] = agg.get(key, 0.0) + float(v)
    top = sorted(agg.items(), key=lambda kv: -kv[1])
    return [{"feature": k, "importance": round(v, 5)} for k, v in top]


def main():
    d = pd.read_csv(DATA)
    d['crop'] = d['crop'].str.strip()
    d['season'] = d['season'].str.strip()
    n_raw = len(d)

    # Detect the winsorisation cap from the data rather than hardcoding it. A rounded
    # literal (104.2734) is numerically ABOVE the true cap (104.2733866960), so a
    # `>= literal` test silently matches zero rows and the artifact disappears from
    # the report. Count what actually sits on the plateau instead.
    clip_value = float(d['yield'].max())
    at_cap = d['yield'] >= clip_value - 1e-6
    clipped = int(at_cap.sum())
    clipped_by_crop = d[at_cap]['crop'].value_counts().to_dict()

    df = d[~d['crop'].isin(EXCLUDED_CROPS)].copy()
    tr = df[df.year < TEST_FROM_YEAR].dropna(subset=FEATURES + ['yield'])
    te = df[df.year >= TEST_FROM_YEAR].dropna(subset=FEATURES + ['yield'])

    print("train %d  test %d  (excluded %s: %d rows)"
          % (len(tr), len(te), EXCLUDED_CROPS, n_raw - len(df)))

    pipe = build_pipeline()
    pipe.fit(tr[FEATURES], tr['yield'])
    pred = pipe.predict(te[FEATURES])
    y = te['yield'].values

    core = ~te['crop'].isin(SCALE_OUTLIERS).values
    headline = scores(y, pred)
    core_only = scores(y[core], pred[core])
    print("holdout R2=%s MAE=%s | core staples R2=%s MAE=%s"
          % (headline['r2'], headline['mae'], core_only['r2'], core_only['mae']))

    # per-crop / per-state error -- the breakdown showing where the model actually works
    err = pd.DataFrame({
        'crop': te['crop'].values,
        'state': te['state'].values,
        'actual': y, 'pred': pred, 'ae': np.abs(y - pred),
    })
    per_crop = [
        {"crop": c, "n": int(g.shape[0]), "mae": round(float(g.ae.mean()), 3),
         "mean_actual": round(float(g.actual.mean()), 3)}
        for c, g in err.groupby('crop') if g.shape[0] >= 5
    ]
    per_crop.sort(key=lambda r: -r['mae'])
    per_state = [
        {"state": s, "n": int(g.shape[0]), "mae": round(float(g.ae.mean()), 3)}
        for s, g in err.groupby('state') if g.shape[0] >= 5
    ]
    per_state.sort(key=lambda r: -r['mae'])

    cv = cross_val_score(build_pipeline(), tr[FEATURES], tr['yield'],
                         cv=KFold(5, shuffle=True, random_state=42),
                         scoring='neg_mean_absolute_error', n_jobs=-1)
    print("5-fold CV MAE %.3f +/- %.3f" % (-cv.mean(), cv.std()))

    rng0 = np.random.default_rng(0)
    staples = te[te.crop.isin(['Rice', 'Wheat', 'Maize', 'Gram', 'Onion', 'Potato'])]
    sample = staples.iloc[rng0.choice(len(staples), min(200, len(staples)), replace=False)]
    sens = sensitivity(pipe, sample, FEATURES)
    print("sensitivity (median over %d rows):" % len(sample),
          {k: str(v['median_pct_change']) + "%" for k, v in sens.items()})

    # same sweep on v2, same rows -- the honest before/after for the write-up
    sens_v2 = None
    v2_path = os.path.join(BASE_DIR, "crop_yield_model_v2_extra_trees.pkl")
    if os.path.exists(v2_path):
        v2 = joblib.load(v2_path)
        sens_v2 = sensitivity(v2, sample, list(v2.feature_names_in_))
        print("v2 for comparison:", {k: str(v['median_pct_change']) + "%" for k, v in sens_v2.items()})

    # scatter sample for the predicted-vs-actual plot (cap payload size)
    rng = np.random.default_rng(42)
    idx = rng.choice(len(err), size=min(1200, len(err)), replace=False)
    scatter = [{"a": round(float(err.actual.iloc[i]), 3), "p": round(float(err.pred.iloc[i]), 3)}
               for i in idx]

    metrics = {
        "model": "Extra Trees Regressor",
        "version": "v3",
        "trained_on": "all years 1997-2020 (shipped artifact)",
        "evaluated_on": "temporal holdout: train <%d, test %d-2020" % (TEST_FROM_YEAR, TEST_FROM_YEAR),
        "note": "Reported metrics come from the holdout fit. The shipped .pkl is refit on all "
                "years for production use; it is never evaluated on data it has seen.",
        "hyperparameters": {"n_estimators": 200, "max_depth": 20,
                            "min_samples_split": 5, "min_samples_leaf": 2},
        "features": {"numeric": len(NUM), "categorical": CATS, "total": len(FEATURES),
                     "dropped_vs_v2": ["state"]},
        "headline": headline,
        "core_staples": dict(core_only, excludes=SCALE_OUTLIERS),
        "cv": {"folds": 5, "mae_mean": round(float(-cv.mean()), 4),
               "mae_std": round(float(cv.std()), 4)},
        "sensitivity": sens,
        "sensitivity_v2": sens_v2,
        "feature_importance": grouped_importance(pipe),
        "per_crop": per_crop,
        "per_state": per_state,
        "scatter": scatter,
        "data_quality": {
            "rows_total": n_raw,
            "rows_used": int(len(df)),
            "excluded_crops": EXCLUDED_CROPS,
            "exclusion_reason": "Coconut is recorded in nuts/ha within a tonnes/ha column; "
                                "winsorisation at the dataset cap collapsed most of its rows to a "
                                "single value, which v2 memorised for a fake MAE of 0.000.",
            "clipped_rows": clipped,
            "clip_value": round(clip_value, 4),
            "clipped_by_crop": {k: int(v) for k, v in clipped_by_crop.items()},
            "known_ceiling": "Soil (N/P/K/pH) is a single constant per state and weather is "
                             "state-year level, so every crop sharing a state-year has an "
                             "identical input vector. The model can therefore learn regional "
                             "response, not field-level response. Closing this needs "
                             "district-level soil/weather data, not a different algorithm.",
        },
    }

    with open(OUT_METRICS, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, indent=2)
    print("wrote %s" % OUT_METRICS)

    # ship a model fit on every year
    final = build_pipeline()
    full = df.dropna(subset=FEATURES + ['yield'])
    final.fit(full[FEATURES], full['yield'])
    joblib.dump(final, OUT_MODEL, compress=3)
    print("wrote %s (%.1f MB, fit on %d rows)"
          % (OUT_MODEL, os.path.getsize(OUT_MODEL) / 1e6, len(full)))


if __name__ == "__main__":
    main()

"""
Retrain the crop-yield model (v3.1) and emit the evaluation artifacts that the
Model Performance page consumes.

v3.1 is the Phase 0 correction described in PRODUCTION_ROADMAP.md. The v3 model scored
R2 0.92 but lost to trivial baselines, because it never saw a series' own history and
had `state` removed to make sliders respond. What changed:

  1. Yield history is a feature. For each (state, crop, season) the previous three
     seasons' yields (forecasting.add_history) enter as lags, mean, trend and an
     `anchor` -- last season's yield. The model learns the change from that anchor.
     The dataset's own `yield_ma2` / `yield_change` columns contain the CURRENT season's
     yield and are never used; data_quality.leakage records the check.
  2. `state` is back. It was dropped to make soil/weather sliders respond; for a
     product that forecasts a state's next season that was the wrong trade.
  3. Every number is reported against baselines, with a skill score
     (1 - model MAE / baseline MAE). R2 on its own cannot show a model is useless;
     "better than repeating last year" can.
  4. Two harder checks sit beside the temporal holdout: leave-states-out (an unseen
     region) and rolling-origin (does the result hold across different test years).

Coconut stays excluded (nuts/ha inside a tonnes/ha column; the dataset's winsorisation
pinned 164 of its 172 rows to one value). Sugarcane is kept and reported separately.

Evaluation is one season ahead: a row's features use only strictly earlier seasons, which
is exactly what is knowable at forecast time. Train < 2018, test 2018-2020. Rows with no
recorded season in the three years before them cannot be forecast (the API refuses them),
so they are counted but not scored. The shipped model is refit on every year.

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
from sklearn.model_selection import GroupKFold

from features import add_derived
from forecasting import AnchoredRegressor, HISTORY_FEATURES, SERIES_KEY, add_history, build_panel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE_DIR, "master_dataset_enhanced.csv")
OUT_MODEL = os.path.join(BASE_DIR, "crop_yield_model_v3.pkl")
OUT_METRICS = os.path.join(BASE_DIR, "model_metrics.json")

EXCLUDED_CROPS = ["Coconut"]     # unit inconsistency, see module docstring
SCALE_OUTLIERS = ["Sugarcane"]   # legitimate but high-magnitude; reported separately
TEST_FROM_YEAR = 2018
ROLLING_YEARS = range(2015, 2021)

NUM = [
    'year', 'avg_temp_c', 'total_rainfall_mm', 'avg_humidity_percent', 'N', 'P', 'K', 'pH',
    'fertilizer_per_ha', 'pesticide_per_ha', 'NPK_total', 'N_to_P_ratio', 'N_to_K_ratio',
    'P_to_K_ratio', 'NPK_balance_score', 'temp_rainfall_interaction',
    'temp_humidity_interaction', 'moisture_index', 'growing_degree_days', 'pH_optimal',
    'soil_fertility_score', 'fertilizer_rainfall_ratio', 'pesticide_efficiency',
    'input_intensity', 'years_since_start',
]
CATS = ['crop', 'season', 'state']
FEATURES = NUM + HISTORY_FEATURES + CATS

BASELINES = {
    "crop_mean": "Crop average over the training years",
    "series_mean": "State x crop x season average over the training years",
    "mean_3yr": "Average of the previous three seasons of the same series",
    "persistence": "Last season's recorded yield, repeated",
}


ET_DEFAULT = dict(n_estimators=200, max_depth=20, min_samples_split=5, min_samples_leaf=2, random_state=42, n_jobs=-1)


def build_model(num, cats, anchored=True, et=None):
    """`et` overrides the Extra Trees settings (used to test smaller models for serving)."""
    pipe = Pipeline([
        ('preprocessing', ColumnTransformer([
            ('num', Pipeline([
                ('imputer', SimpleImputer(strategy='median')),
                ('scaler', StandardScaler()),
            ]), num),
            ('cat', Pipeline([
                ('imputer', SimpleImputer(strategy='most_frequent')),
                ('encoder', OneHotEncoder(handle_unknown='ignore')),
            ]), cats),
        ])),
        ('model', ExtraTreesRegressor(**{**ET_DEFAULT, **(et or {})})),
    ])
    return AnchoredRegressor(pipe) if anchored else pipe


def scores(y, pred):
    return {
        "r2": round(float(r2_score(y, pred)), 4),
        "mae": round(float(mean_absolute_error(y, pred)), 4),
        "rmse": round(float(np.sqrt(mean_squared_error(y, pred))), 4),
        "n": int(len(y)),
    }


def skill(model_mae, baseline_mae):
    """Percent MAE reduction over a baseline. Negative means the baseline is better."""
    return round(100 * (1 - model_mae / baseline_mae), 1)


def baseline_forecasts(tr, te):
    """Every baseline for the rows of `te`, using only information available at forecast
    time: training-year averages, and the earlier seasons already attached to each row."""
    crop_mean = te['crop'].map(tr.groupby('crop')['yield'].mean()).fillna(tr['yield'].mean())
    series = tr.groupby(SERIES_KEY)['yield'].mean().rename('m').reset_index()
    series_mean = te[SERIES_KEY].merge(series, how='left', on=SERIES_KEY)['m'].to_numpy()
    series_mean = np.where(np.isnan(series_mean), crop_mean.to_numpy(), series_mean)
    return {
        "crop_mean": crop_mean.to_numpy(),
        "series_mean": series_mean,
        "mean_3yr": te['yield_mean3'].to_numpy(),
        "persistence": te['yield_anchor'].to_numpy(),
    }


def compare(y, model_pred, baselines):
    """Model and every baseline scored on the same rows, plus skill against each."""
    model = scores(y, model_pred)
    base = {name: dict(scores(y, p), label=BASELINES[name]) for name, p in baselines.items()}
    best = min(base, key=lambda n: base[n]["mae"])
    return model, base, {
        "best_baseline": best,
        "vs_best_baseline_pct": skill(model["mae"], base[best]["mae"]),
        "vs_baseline_pct": {n: skill(model["mae"], b["mae"]) for n, b in base.items()},
    }


def forecastable(df):
    """Rows that have at least one recorded season in the three years before them, with
    every non-history feature present."""
    return df[(df['history_seasons'] >= 1)].dropna(subset=NUM + CATS + ['yield_anchor', 'yield'])


def leave_states_out(df, folds=5):
    """Hold out whole states: what the model does in a region it has never been trained on.

    The state's own recorded history is still an input (that is knowable for any region
    with records), but nothing about the region is learned. `no_history` is the same test
    for a model with agronomic inputs only, i.e. a region with no records at all."""
    rows = forecastable(df)
    y = rows['yield'].to_numpy()
    pred = np.zeros(len(rows))
    pred_nh = np.zeros(len(rows))
    crop_mean = np.zeros(len(rows))
    num_nh, cats_nh = NUM, ['crop', 'season']          # no history, no state
    for tr_i, te_i in GroupKFold(folds).split(rows, groups=rows['state']):
        tr, te = rows.iloc[tr_i], rows.iloc[te_i]
        m = build_model(NUM + HISTORY_FEATURES, CATS).fit(tr[NUM + HISTORY_FEATURES + CATS], tr['yield'])
        pred[te_i] = m.predict(te[NUM + HISTORY_FEATURES + CATS])
        nh = build_model(num_nh, cats_nh, anchored=False).fit(tr[num_nh + cats_nh], tr['yield'])
        pred_nh[te_i] = nh.predict(te[num_nh + cats_nh])
        crop_mean[te_i] = baseline_forecasts(tr, te)["crop_mean"]
    base = {"persistence": rows['yield_anchor'].to_numpy(), "mean_3yr": rows['yield_mean3'].to_numpy()}
    model, bl, sk = compare(y, pred, {**base, "crop_mean": crop_mean})
    nh_scores = scores(y, pred_nh)
    return {
        "folds": folds, "scheme": "5 folds, whole states held out, all years pooled",
        "model": model, "baselines": bl, "skill": sk,
        "no_history": dict(nh_scores, vs_crop_mean_pct=skill(nh_scores["mae"], bl["crop_mean"]["mae"]),
                           note="Agronomic inputs only (no yield history), on held-out states."),
    }


def rolling_origin(df):
    """Train on every season before Y, forecast Y, for several Y. A single 2018-2020
    split could be a lucky or unlucky window; this shows whether the verdict is stable."""
    out = []
    for yr in ROLLING_YEARS:
        tr = forecastable(df[df.year < yr])
        te = forecastable(df[df.year == yr])
        m = build_model(NUM + HISTORY_FEATURES, CATS).fit(tr[NUM + HISTORY_FEATURES + CATS], tr['yield'])
        y = te['yield'].to_numpy()
        mae_m = mean_absolute_error(y, m.predict(te[NUM + HISTORY_FEATURES + CATS]))
        mae_p = mean_absolute_error(y, te['yield_anchor'])
        mae_3 = mean_absolute_error(y, te['yield_mean3'])
        out.append({
            "year": int(yr), "n": int(len(te)),
            "model_mae": round(float(mae_m), 4),
            "persistence_mae": round(float(mae_p), 4),
            "mean_3yr_mae": round(float(mae_3), 4),
            "skill_vs_persistence_pct": skill(mae_m, mae_p),
            "skill_vs_mean_3yr_pct": skill(mae_m, mae_3),
        })
    return out


def ablation(tr, te):
    """Which input groups earn their place, on the holdout. The roadmap's claim --
    weather and soil add nothing once history is known -- is checked here, not assumed."""
    y = te['yield'].to_numpy()
    variants = [
        ("No history (agronomic inputs + state)", NUM, CATS, False),
        ("History only (no weather or soil)", ['year'] + HISTORY_FEATURES, CATS, True),
        ("History + weather + soil (shipped)", NUM + HISTORY_FEATURES, CATS, True),
    ]
    out = []
    for name, num, cats, anchored in variants:
        m = build_model(num, cats, anchored).fit(tr[num + cats], tr['yield'])
        out.append(dict(scores(y, m.predict(te[num + cats])), variant=name))
    return out


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
    noisy to characterise a tree ensemble.

    Derived columns are rebuilt from the perturbed raw value via features.py. Skipping
    that step is the trap -- rainfall also feeds moisture_index,
    temp_rainfall_interaction and fertilizer_rainfall_ratio, so perturbing the raw
    column alone leaves the model reading three stale copies of the old value and
    understates its true response. Yield history does not depend on these inputs, so
    it is left as attached to the row.
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


def grouped_importance(model):
    """One-hot columns are summed back into their source feature, otherwise `crop`
    looks like 55 weak features instead of one dominant one. Importance describes the
    learned CHANGE from last season's yield, not the yield level."""
    inner = model.estimator_
    names = inner.named_steps['preprocessing'].get_feature_names_out()
    imp = inner.named_steps['model'].feature_importances_
    agg = {}
    for n, v in zip(names, imp):
        key = n.split('__', 1)[1]
        if n.startswith('cat__'):
            key = key.split('_')[0]
        agg[key] = agg.get(key, 0.0) + float(v)
    top = sorted(agg.items(), key=lambda kv: -kv[1])
    return [{"feature": k, "importance": round(v, 5)} for k, v in top]


def leakage_check(raw):
    """The enhanced CSV ships `yield_ma2` and `yield_change`. Both are functions of the
    row's own yield, so a model trained on them is told the answer."""
    ma2 = np.isclose(raw['yield_ma2'], (raw['yield'] + raw['yield_lag1']) / 2)
    chg = np.isclose(raw['yield_change'], raw['yield'] - raw['yield_lag1'])
    return {
        "yield_ma2_contains_target_pct": round(100 * float(ma2.mean()), 1),
        "yield_change_contains_target_pct": round(100 * float(chg.mean()), 1),
        "columns_not_used": ["yield_ma2", "yield_change"],
        "history_source": "Every history feature, including yield_lag1, is recomputed per state x "
                          "crop x season from strictly earlier calendar years "
                          "(forecasting.add_history), not read from the CSV. test_model.py proves "
                          "no lookahead.",
    }


def main():
    raw = pd.read_csv(DATA)
    n_raw = len(raw)
    d = raw.copy()
    for c in ('crop', 'season', 'state'):
        d[c] = d[c].str.strip()

    # Detect the winsorisation cap from the data rather than hardcoding it. A rounded
    # literal (104.2734) is numerically ABOVE the true cap (104.2733866960), so a
    # `>= literal` test silently matches zero rows and the artifact disappears from
    # the report. Count what actually sits on the plateau instead.
    clip_value = float(d['yield'].max())
    at_cap = d['yield'] >= clip_value - 1e-6
    clipped = int(at_cap.sum())
    clipped_by_crop = d[at_cap]['crop'].value_counts().to_dict()

    df = d[~d['crop'].isin(EXCLUDED_CROPS)].copy()
    df = add_history(add_derived(df), build_panel(df))
    eligible = forecastable(df)
    tr = eligible[eligible.year < TEST_FROM_YEAR]
    te = eligible[eligible.year >= TEST_FROM_YEAR]
    n_test_all = int((df.year >= TEST_FROM_YEAR).sum())

    print("train %d  test %d  (excluded %s: %d rows; %d test rows have no prior season)"
          % (len(tr), len(te), EXCLUDED_CROPS, n_raw - len(df), n_test_all - len(te)))

    model = build_model(NUM + HISTORY_FEATURES, CATS).fit(tr[FEATURES], tr['yield'])
    pred = model.predict(te[FEATURES])
    y = te['yield'].to_numpy()

    base_pred = baseline_forecasts(tr, te)
    headline, baselines, headline_skill = compare(y, pred, base_pred)

    core = ~te['crop'].isin(SCALE_OUTLIERS).to_numpy()
    core_only, core_baselines, core_skill = compare(
        y[core], pred[core], {k: v[core] for k, v in base_pred.items()})
    print("holdout MAE %s (R2 %s) | best baseline %s MAE %s | skill %s%%"
          % (headline['mae'], headline['r2'], headline_skill['best_baseline'],
             baselines[headline_skill['best_baseline']]['mae'], headline_skill['vs_best_baseline_pct']))
    print("core staples: MAE %s | skill %s%% vs %s"
          % (core_only['mae'], core_skill['vs_best_baseline_pct'], core_skill['best_baseline']))

    # per-crop / per-state error, with the persistence baseline beside it
    err = pd.DataFrame({
        'crop': te['crop'].to_numpy(), 'state': te['state'].to_numpy(), 'actual': y,
        'ae': np.abs(y - pred), 'base_ae': np.abs(y - base_pred["persistence"]),
    })
    per_crop = [
        {"crop": c, "n": int(g.shape[0]), "mae": round(float(g.ae.mean()), 3),
         "baseline_mae": round(float(g.base_ae.mean()), 3),
         "mean_actual": round(float(g.actual.mean()), 3)}
        for c, g in err.groupby('crop') if g.shape[0] >= 5
    ]
    per_crop.sort(key=lambda r: -r['mae'])
    per_state = [
        {"state": s, "n": int(g.shape[0]), "mae": round(float(g.ae.mean()), 3),
         "baseline_mae": round(float(g.base_ae.mean()), 3)}
        for s, g in err.groupby('state') if g.shape[0] >= 5
    ]
    per_state.sort(key=lambda r: -r['mae'])

    print("leave-states-out ...")
    lso = leave_states_out(eligible)
    print("  model MAE %s | %s MAE %s | skill %s%% | no-history MAE %s (%s%% vs crop mean)"
          % (lso['model']['mae'], lso['skill']['best_baseline'],
             lso['baselines'][lso['skill']['best_baseline']]['mae'],
             lso['skill']['vs_best_baseline_pct'], lso['no_history']['mae'],
             lso['no_history']['vs_crop_mean_pct']))
    print("rolling origin ...")
    rolling = rolling_origin(df)
    for r in rolling:
        print("  %d  model %.3f  persistence %.3f  3yr-mean %.3f  skill vs persistence %s%%"
              % (r['year'], r['model_mae'], r['persistence_mae'], r['mean_3yr_mae'],
                 r['skill_vs_persistence_pct']))
    print("ablation ...")
    abl = ablation(tr, te)
    for a in abl:
        print("  %-42s MAE %s" % (a['variant'], a['mae']))

    rng0 = np.random.default_rng(0)
    staples = te[te.crop.isin(['Rice', 'Wheat', 'Maize', 'Gram', 'Onion', 'Potato'])]
    sample = staples.iloc[rng0.choice(len(staples), min(200, len(staples)), replace=False)]
    sens = sensitivity(model, sample, FEATURES)
    print("sensitivity (median over %d rows):" % len(sample),
          {k: str(v['median_pct_change']) + "%" for k, v in sens.items()})

    # same sweep on v2, same rows -- the honest before/after for the write-up
    sens_v2 = None
    v2_path = os.path.join(BASE_DIR, "crop_yield_model_v2_extra_trees.pkl")
    if os.path.exists(v2_path):
        v2 = joblib.load(v2_path)
        sens_v2 = sensitivity(v2, sample, list(v2.feature_names_in_))

    # scatter sample for the predicted-vs-actual plot (cap payload size)
    rng = np.random.default_rng(42)
    idx = rng.choice(len(err), size=min(1200, len(err)), replace=False)
    scatter = [{"a": round(float(y[i]), 3), "p": round(float(pred[i]), 3)} for i in idx]

    metrics = {
        "model": "Extra Trees Regressor (anchored on last season's yield)",
        "version": "v3.1",
        "trained_on": "all years 1997-2020 (shipped artifact)",
        "evaluated_on": "temporal holdout: train <%d, test %d-2020, one season ahead"
                        % (TEST_FROM_YEAR, TEST_FROM_YEAR),
        "note": "Reported metrics come from the holdout fit. The shipped .pkl is refit on all "
                "years for production use; it is never evaluated on data it has seen.",
        "hyperparameters": {"n_estimators": 200, "max_depth": 20,
                            "min_samples_split": 5, "min_samples_leaf": 2},
        "features": {"numeric": len(NUM), "history": HISTORY_FEATURES, "categorical": CATS,
                     "total": len(FEATURES), "dropped_vs_v2": [], "added_vs_v3": HISTORY_FEATURES + ['state']},
        "forecast_design": {
            "task": "One-season-ahead yield for a state x crop x season series.",
            "anchor": "The model learns the change from last season's recorded yield "
                      "(mean of the earlier seasons that exist when last season is missing).",
            "requires": "At least one recorded season in the three years before the forecast year.",
            "unscored_test_rows": n_test_all - len(te),
        },
        "headline": headline,
        "core_staples": dict(core_only, excludes=SCALE_OUTLIERS),
        "baselines": baselines,
        "core_staples_baselines": core_baselines,
        "skill": dict(headline_skill, core_staples=core_skill),
        "rolling_origin": rolling,
        "leave_states_out": lso,
        "ablation": abl,
        "sensitivity": sens,
        "sensitivity_v2": sens_v2,
        "feature_importance": grouped_importance(model),
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
            "leakage": leakage_check(raw),
            "known_ceiling": "Soil (N/P/K/pH) is a single constant per state and weather is "
                             "state-year level, so every crop sharing a state-year has an "
                             "identical input vector. Once a series' own history is known, these "
                             "inputs add no measurable accuracy (see ablation). Closing this needs "
                             "district-level soil/weather data, not a different algorithm.",
        },
    }

    with open(OUT_METRICS, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, indent=2)
    print("wrote %s" % OUT_METRICS)

    # ship a model fit on every year
    final = build_model(NUM + HISTORY_FEATURES, CATS)
    full = eligible
    final.fit(full[FEATURES], full['yield'])
    joblib.dump(final, OUT_MODEL, compress=3)
    print("wrote %s (%.1f MB, fit on %d rows)"
          % (OUT_MODEL, os.path.getsize(OUT_MODEL) / 1e6, len(full)))


if __name__ == "__main__":
    main()

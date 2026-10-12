"""
Yield history and the anchored forecaster -- shared by training and serving.

A forecast for (state, crop, season, year) is made from what was *recorded in earlier
seasons of that same series*, plus the weather and soil inputs. Both halves live here so
that the retrain, the evaluation and the API cannot drift apart:

  add_history()      builds lag/mean/trend features from a yield panel. Every lookup is
                     for a strictly earlier calendar year, so a row never sees its own
                     yield or anything after it. (The dataset's own `yield_ma2` and
                     `yield_change` columns DO include the current season's yield, so
                     they are never used -- see train_v3.py, data_quality.leakage.)

  AnchoredRegressor  predicts the *change* from last season's yield rather than the
                     yield itself. Trees cannot extrapolate "tomorrow ~ yesterday" from
                     raw lag columns; anchoring hands them that identity for free.
"""

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin, clone

SERIES_KEY = ["state", "crop", "season"]
LAGS = (1, 2, 3)

HISTORY_FEATURES = [
    "yield_lag1", "yield_lag2", "yield_lag3",
    "yield_mean3",        # mean of whichever of the three lags exist
    "yield_trend",        # (lag1 - lag3) / 2, tonnes/ha per season
    "history_seasons",    # how many of the three lags exist (0-3)
    "yield_anchor",       # last season's yield; mean of the lags that exist if it is missing
]

# The scale-free design of the pooled model (sugarcane and pulses share it): every history column divided by the anchor.
REL_NUM = ["year", "history_seasons", "r1", "r2", "r3", "rm", "rt", "log_anchor"]


def build_panel(df, key=SERIES_KEY):
    """Yield by (*key, year). Index must be unique and labels stripped. `key` defaults to the
    state-level series; the district pipeline passes ["district_code", "crop", "season"]."""
    return df.set_index(list(key) + ["year"])["yield"]


def add_history(df, panel, key=SERIES_KEY, shift=0):
    """Attach HISTORY_FEATURES. Needs stripped label columns (features.add_derived guarantees
    that for the state-level path) because the panel is keyed on them.

    `shift` models a publication lag: with shift=1 the lags look at year-2, year-3, year-4, so
    `yield_lag1` means "the most recent season that has been published", not "last season"."""
    df = df.copy()
    for k in LAGS:
        idx = pd.MultiIndex.from_arrays([df[c] for c in key] + [df["year"] - (k + shift)])
        df[f"yield_lag{k}"] = panel.reindex(idx).to_numpy()
    lags = df[[f"yield_lag{k}" for k in LAGS]]
    df["history_seasons"] = lags.notna().sum(axis=1)
    df["yield_mean3"] = lags.mean(axis=1)
    df["yield_trend"] = (df["yield_lag1"] - df["yield_lag3"]) / 2
    df["yield_anchor"] = df["yield_lag1"].fillna(df["yield_mean3"])
    return df


def relative(df):
    """Add REL_NUM's ratio columns and `one` (the anchor of a relative model: it learns yield / anchor - 1)."""
    a = df["yield_anchor"]
    df = df.copy()
    for k in LAGS:
        df[f"r{k}"] = df[f"yield_lag{k}"] / a
    df["rm"], df["rt"] = df["yield_mean3"] / a, df["yield_trend"] / a
    df["log_anchor"], df["one"] = np.log(a), 1.0
    return df


class AnchoredRegressor(BaseEstimator, RegressorMixin):
    """Wraps a pipeline so it learns `yield - yield_anchor` and adds the anchor back.

    Yields cannot be negative, so predictions are floored at zero. `predict_members`
    exposes the per-tree forecasts the API turns into an ensemble-agreement interval.
    """

    def __init__(self, estimator, anchor="yield_anchor"):
        self.estimator = estimator
        self.anchor = anchor

    def fit(self, X, y):
        self.estimator_ = clone(self.estimator).fit(X, np.asarray(y) - X[self.anchor].to_numpy())
        self.feature_names_in_ = np.asarray(X.columns)
        return self

    def predict(self, X):
        return np.maximum(self.estimator_.predict(X) + X[self.anchor].to_numpy(), 0.0)

    def predict_members(self, X):
        """Per-tree forecasts, shape (n_trees, n_rows)."""
        pre = self.estimator_.named_steps["preprocessing"]
        trees = self.estimator_.named_steps["model"].estimators_
        Xt = pre.transform(X)
        return np.maximum(np.stack([t.predict(Xt) for t in trees]) + X[self.anchor].to_numpy(), 0.0)

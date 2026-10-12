"""
District yield forecasts for serving (Phase 4, first slice): history-only, publication-lag aware.

    python district_forecast.py        train and save the serving models  (needs data/processed/*, pipeline/)

What is served, and why it is this and not more:
  * Rice and Maize (Kharif) share one model, Wheat (Rabi) has its own. Both are the anchored Extra Trees validated in
    Phase 2, fitted on every season up to 2024, with `year`, the district's recorded history and crop / season / state.
  * History is lagged by one season (Gate G1): for a forecast of agricultural year Y the most recent season used is
    Y-2, because district yields are published more than a year late. `forecast_year` is therefore 2025 or 2026.
  * No weather or NDVI. Under that lag they bought about 1% of MAE on 2018-23 and nothing on 2024, and they would need
    a live feed. They can be added later as an in-season update.
  * The 80% interval is conformal calibrated per trust flag (Mondrian) on the last three out-of-sample years:
    volatile series get wider intervals, so their coverage is not dragged below the nominal level by the stable
    ones. Volatile-series coverage has still been only about 67-80% in backtests, and is disclosed as approximate.

Everything the model knows about a series is returned with the forecast (last published season, 3-season mean, recent
history, whether the series is volatile, how the model did on past seasons), so a reader can judge it.
"""

import json
import math
import os

import joblib
import numpy as np
import pandas as pd

from forecasting import HISTORY_FEATURES, add_history, build_panel

ROOT = os.path.dirname(os.path.abspath(__file__))
PROC = os.path.join(ROOT, "data", "processed")           # training inputs; not needed to serve
SERVING = os.path.join(ROOT, "serving")                   # everything the service reads; tracked in git (~7 MB)
MODEL_DIR = os.path.join(SERVING, "models")
SERIES_PATH = os.path.join(SERVING, "district_series.parquet")
TRACK_PATH = os.path.join(SERVING, "track_record.parquet")
SHAPES_PATH = os.path.join(SERVING, "district_shapes.json")
# Smaller than the validated-by-default trees (32.7 + 22.4 MB): leaf 20 and 100 trees pickle to ~5 MB in total and
# were as accurate in the size experiment (PRODUCTION_ROADMAP.md, "Model size for serving"; pipeline/shrink_experiment.py).
ET_SERVING = dict(min_samples_leaf=20, n_estimators=100)

KEY = ["district_code", "crop", "season"]
SHIFT = 1
DATA_END = 2024
CAL_YEARS = (2022, 2023, 2024)
FORECAST_YEARS = (DATA_END + 1, DATA_END + 2)       # 2025 and 2026: the seasons not yet published
HIST = ["year"] + HISTORY_FEATURES
CATS = ["crop", "season", "state_name"]
GROUPS = {
    "kharif_rice_maize": {"label": "Kharif Rice + Maize", "crops": ("Rice", "Maize"), "season": "Kharif", "p2": "Kharif Rice + Maize"},
    "wheat_rabi": {"label": "Wheat (Rabi)", "crops": ("Wheat",), "season": "Rabi", "p2": "Wheat (Rabi)"},
}
STAPLES = ["Rice", "Maize", "Wheat"]


class ForecastError(ValueError):
    """A request that cannot be forecast, with a reason a user can act on."""


def group_of(crop, season):
    for name, g in GROUPS.items():
        if crop in g["crops"] and season == g["season"]:
            return name
    return None


def conformal_q(rel, level=0.8):
    r = np.sort(np.asarray(rel))
    if len(r) == 0:
        return float("nan")
    return float(r[min(len(r) - 1, math.ceil((len(r) + 1) * level) - 1)])


def _volatility(df):
    """Recent jumpiness of a series relative to its level (same definition as Phase 2)."""
    return ((df["yield_lag1"] - df["yield_lag2"]).abs() + (df["yield_lag2"] - df["yield_lag3"]).abs()) / 2 / df["yield_mean3"]


def _training_frame():
    """Training-side view: staple series with a valid yield, up to DATA_END, for districts that have a boundary."""
    g = pd.read_parquet(os.path.join(PROC, "district_yield.parquet"))
    g = g[g.crop.isin(STAPLES) & g.valid_yield & ~g.flag_outlier & (g.year <= DATA_END)].copy()
    geo = pd.read_parquet(os.path.join(PROC, "district_geo.parquet"))[["district_code", "shape_id"]]
    return g.merge(geo, on="district_code").dropna(subset=["shape_id"])      # same districts the model was validated on


def _panel_frame():
    """Serving-side view: the trimmed export written by train()."""
    return pd.read_parquet(SERIES_PATH)


# ── training ────────────────────────────────────────────────────────────────────────────────────
def train():
    """Fit the serving models, run their own out-of-sample backtest, and export everything serving needs to `serving/`.
    Phase 2's own code builds the rows, so the served model is the validated design, not a re-implementation. The
    calibration, trust flag and skill figures come from THIS configuration's rolling-origin forecasts, never from a
    different one."""
    os.environ["HIST_SHIFT"] = str(SHIFT)
    import functools
    import shutil
    import sys
    sys.path.insert(0, os.path.join(ROOT, "pipeline"))
    import phase2_forecast as P2
    from train_v3 import build_model

    et_model = functools.partial(build_model, et=ET_SERVING)
    P2.build_model, P2.FIT_LEADS = et_model, [0]
    g = P2.load()
    preds = pd.concat([P2.run_group(spec["p2"], P2.GROUPS[spec["p2"]], g) for spec in GROUPS.values()], ignore_index=True)
    os.makedirs(MODEL_DIR, exist_ok=True)
    for slug, spec in GROUPS.items():
        p2 = P2.GROUPS[spec["p2"]]
        d = P2.attach(g[p2["sel"](g)], p2["window"], p2["weather"])
        d = d.dropna(subset=P2.lead_cols(120, p2["weather"])).reset_index(drop=True)   # same rows as the validation
        model = et_model(HIST, CATS).fit(d[HIST + CATS], d["yield"])
        joblib.dump(model, os.path.join(MODEL_DIR, "district_%s.pkl" % slug), compress=3)
        # Mondrian calibration from the last three out-of-sample years (each forecast made by a model trained on
        # earlier years only). One year was too noisy: the flagged-wheat quantile ranged 0.24-0.42 across years and
        # rested on as few as 39 rows, so three years are pooled.
        r = preds[(preds.group == spec["p2"]) & (preds.lead == 0) & (preds.year.isin(CAL_YEARS))].copy()
        r["rel"] = (r["yield"] - r["pred"]).abs() / np.maximum(r["pred"], 0.05)
        meta = {"label": spec["label"], "trained_through": DATA_END, "history_lag_seasons": SHIFT, "rows": int(len(d)),
                "districts": int(d.district_code.nunique()), "vol_threshold": float(d["vol"].quantile(0.8)),
                "q_flagged": conformal_q(r[r.flag_low_trust].rel), "q_unflagged": conformal_q(r[~r.flag_low_trust].rel),
                "calibration_rows": int(len(r)), "skill": group_skill(preds, spec["p2"]), "trees": ET_SERVING}
        with open(os.path.join(MODEL_DIR, "district_%s.json" % slug), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
        print("%-22s rows %6d | districts %d | vol threshold %.3f | q flagged %.3f unflagged %.3f | %.1f MB" % (
            spec["label"], len(d), meta["districts"], meta["vol_threshold"], meta["q_flagged"], meta["q_unflagged"],
            os.path.getsize(os.path.join(MODEL_DIR, "district_%s.pkl" % slug)) / 1e6))

    # trimmed data the service reads at runtime
    cols = ["district_code", "district_name", "state_name", "crop", "season", "year", "yield", "shape_id"]
    _training_frame()[cols].to_parquet(SERIES_PATH, index=False)
    keep = ["district_code", "crop", "season", "year", "pred", "yield", "yield_anchor"]
    preds[preds.lead == 0][keep].to_parquet(TRACK_PATH, index=False)
    shutil.copyfile(os.path.join(PROC, "district_shapes.json"), SHAPES_PATH)
    total = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(SERVING) for f in fs)
    print("serving/ total %.1f MB" % (total / 1e6))


def group_skill(preds, group):
    """The skill figures a reader needs for ONE group, from the Gate G1 run (one-season publication lag, history-only
    lead): MAE against the last published season and the 3-season mean, on 2018-23 and on the 2024 confirmation year."""
    out = {}
    for label, years in (("dev_2018_2023", range(2018, 2024)), ("confirm_2024", [DATA_END])):
        x = preds[(preds.group == group) & (preds.lead == 0) & preds.year.isin(list(years))]
        m = float((x["yield"] - x["pred"]).abs().mean())
        lp = float((x["yield"] - x["yield_anchor"]).abs().mean())
        m3 = float((x["yield"] - x["yield_mean3"]).abs().mean())
        out[label] = {"n": int(len(x)), "mae": round(m, 4), "last_published_mae": round(lp, 4), "mean3_mae": round(m3, 4),
                      "skill_vs_last_published_pct": round(100 * (1 - m / lp), 1), "skill_vs_mean3_pct": round(100 * (1 - m / m3), 1)}
    return out


# ── serving ─────────────────────────────────────────────────────────────────────────────────────
class DistrictForecaster:
    def __init__(self):
        self.frame = _panel_frame()
        self.panel = build_panel(self.frame, KEY).sort_index()
        self.series = self.frame.groupby(KEY).year.agg(["min", "max"])
        self.names = (self.frame.sort_values("year").groupby("district_code")[["district_name", "state_name"]].last())
        self.shape_ids = self.frame.groupby("district_code").shape_id.first()
        self._models, self._meta = {}, {}
        self._preds, self._shapes, self._maps = None, None, {}

    def _load(self, slug):
        if slug not in self._models:
            self._models[slug] = joblib.load(os.path.join(MODEL_DIR, "district_%s.pkl" % slug))
            self._meta[slug] = json.load(open(os.path.join(MODEL_DIR, "district_%s.json" % slug), encoding="utf-8"))
        return self._models[slug], self._meta[slug]

    def options(self):
        """state -> district -> the crop/season combinations that can be forecast."""
        out = {}
        for (dc, crop, season), r in self.series.iterrows():
            if group_of(crop, season) is None or r["max"] < DATA_END - 3:      # needs a recent record to forecast from
                continue
            nm = self.names.loc[dc]
            d = out.setdefault(nm.state_name, {}).setdefault(int(dc), {"name": nm.district_name, "series": []})
            d["series"].append({"crop": crop, "season": season})
        return out

    def forecast(self, district_code, crop, season, year):
        slug = group_of(crop, season)
        if slug is None:
            raise ForecastError("Forecasts are available for Rice and Maize in Kharif and Wheat in Rabi.")
        if (district_code, crop, season) not in self.series.index:
            raise ForecastError("No %s (%s) records for this district." % (crop, season))
        if year not in FORECAST_YEARS:
            raise ForecastError("Forecasts are for %d or %d, the seasons whose yields are not yet published." % FORECAST_YEARS)
        model, meta = self._load(slug)
        nm = self.names.loc[district_code]
        row = pd.DataFrame([{"year": year, "district_code": district_code, "crop": crop, "season": season,
                             "state_name": nm.state_name}])
        row = add_history(row, self.panel, KEY, shift=SHIFT)
        if int(row["history_seasons"].iloc[0]) == 0:
            raise ForecastError("No yield recorded in the three published seasons before %d, so there is nothing to forecast from." % year)
        pred = float(model.predict(row[HIST + CATS])[0])
        vol = float(_volatility(row).iloc[0])
        flagged = bool(np.isfinite(vol) and vol >= meta["vol_threshold"])
        q = meta["q_flagged"] if flagged else meta["q_unflagged"]
        r = row.iloc[0]
        lag = next(k for k in (1, 2, 3) if not np.isnan(r["yield_lag%d" % k]))
        hist = self.frame[(self.frame.district_code == district_code) & (self.frame.crop == crop) & (self.frame.season == season)]
        hist = hist.sort_values("year").tail(6)
        notes = []
        if nm.state_name == "Madhya Pradesh":
            notes.append("Madhya Pradesh district figures in the source are about twice the Centre's official state totals for wheat; "
                         "treat the level with caution. Changes from year to year are less affected.")
        if flagged:
            notes.append("This series has jumped around recently, so its forecasts have been less reliable and the range is wider.")
        if year == FORECAST_YEARS[1]:
            notes.append("The most recent published season for this series is older than for a %d forecast; accuracy is lower." % FORECAST_YEARS[0])
        return {
            "district": {"code": int(district_code), "name": nm.district_name, "state": nm.state_name},
            "crop": crop, "season": season, "forecast_year": int(year), "unit": "tonnes/ha",
            "forecast": round(pred, 2),
            "interval": {"level": 0.8, "low": round(pred * (1 - q), 2), "high": round(pred * (1 + q), 2),
                         "relative_half_width": round(q, 3), "method": "conformal, calibrated separately for volatile and stable series"},
            "baselines": {
                "last_published": {"value": round(float(r["yield_anchor"]), 2), "year": int(year - (lag + SHIFT))},
                "mean_last_three_published": round(float(r["yield_mean3"]), 2)},
            "trust": {"low_trust": flagged, "volatility": None if not np.isfinite(vol) else round(vol, 3),
                      "seasons_of_history_used": int(r["history_seasons"])},
            "history": [{"year": int(y), "yield": round(float(v), 2)} for y, v in zip(hist.year, hist["yield"])],
            "model": {"group": meta["label"], "trained_through": meta["trained_through"],
                      "history_lag_seasons": meta["history_lag_seasons"], "skill": meta["skill"],
                      "inputs": "the series' own published history, crop, season, state and year; no weather or satellite data"},
            "notes": notes,
        }

    def shapes(self):
        """District outlines for the map (built by pipeline/build_map_shapes.py)."""
        if self._shapes is None:
            self._shapes = json.load(open(SHAPES_PATH, encoding="utf-8"))
        return self._shapes

    def map_data(self, crop, season, year):
        """Every forecastable district for one crop, season and year, in one pass.

        Same rows, same model, same interval rule as `forecast()` (test_district.py checks that a district on the map
        and the same district on the forecast page agree), computed as one batch because a map needs ~600 at once."""
        slug = group_of(crop, season)
        if slug is None:
            raise ForecastError("Maps are available for Rice and Maize in Kharif and Wheat in Rabi.")
        if year not in FORECAST_YEARS:
            raise ForecastError("Forecasts are for %d or %d, the seasons whose yields are not yet published." % FORECAST_YEARS)
        key = (crop, season, year)
        if key in self._maps:
            return self._maps[key]
        model, meta = self._load(slug)
        s = self.series.reset_index()
        s = s[(s.crop == crop) & (s.season == season) & (s["max"] >= DATA_END - 3)]
        df = pd.DataFrame({"year": year, "district_code": s.district_code.to_numpy(), "crop": crop, "season": season})
        df["state_name"] = self.names.loc[df.district_code, "state_name"].to_numpy()
        df = add_history(df, self.panel, KEY, shift=SHIFT)
        df = df[df.history_seasons > 0].reset_index(drop=True)
        pred = model.predict(df[HIST + CATS])
        vol = _volatility(df).to_numpy()
        flagged = np.isfinite(vol) & (vol >= meta["vol_threshold"])
        q = np.where(flagged, meta["q_flagged"], meta["q_unflagged"])
        rows = []
        for i, r in df.iterrows():
            last = float(r["yield_anchor"])
            rows.append({
                "district_code": int(r.district_code), "name": self.names.loc[r.district_code, "district_name"],
                "state": r.state_name, "shape_id": self.shape_ids[r.district_code],
                "forecast": round(float(pred[i]), 2), "low": round(float(pred[i] * (1 - q[i])), 2),
                "high": round(float(pred[i] * (1 + q[i])), 2), "last_published": round(last, 2),
                "mean3": round(float(r.yield_mean3), 2),
                "change_vs_last_pct": round(100 * (float(pred[i]) / last - 1), 1) if last > 0 else None,
                "change_vs_mean3_pct": round(100 * (float(pred[i]) / float(r.yield_mean3) - 1), 1) if r.yield_mean3 > 0 else None,
                "low_trust": bool(flagged[i])})
        out = {"crop": crop, "season": season, "forecast_year": int(year), "unit": "tonnes/ha", "group": meta["label"],
               "skill": meta["skill"], "districts": rows}
        self._maps[key] = out
        return out

    def track_record(self, district_code, crop, season):
        """Out-of-sample forecasts of past seasons (each made by a model trained on earlier years only)."""
        if self._preds is None:
            self._preds = pd.read_parquet(TRACK_PATH)
        p = self._preds[(self._preds.district_code == district_code) & (self._preds.crop == crop) &
                        (self._preds.season == season)].sort_values("year")
        rows = [{"year": int(r.year), "forecast": round(float(r.pred), 2), "actual": round(float(r["yield"]), 2),
                 "last_published": round(float(r.yield_anchor), 2)} for _, r in p.iterrows()]
        out = {"seasons": rows}
        if rows:
            a = np.array([[x["forecast"], x["actual"], x["last_published"]] for x in rows])
            out["summary"] = {"n": len(rows), "model_mae": round(float(np.abs(a[:, 0] - a[:, 1]).mean()), 3),
                              "last_published_mae": round(float(np.abs(a[:, 2] - a[:, 1]).mean()), 3)}
        return out


if __name__ == "__main__":
    train()

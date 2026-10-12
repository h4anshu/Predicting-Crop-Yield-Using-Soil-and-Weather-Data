"""
District outlook: the expected yield of a crop in a district, from the master table, with a tested range.

    python district_forecast.py        build the serving files (needs data/processed/master_panel.parquet and the
                                       results of `python pipeline/train_master.py`)

What is served, and why it is this and not a model (the evidence is in PRODUCTION_ROADMAP.md, "One table, one model",
Amendments A1 and A2, and in pipeline/train_master.py, which makes every decision recorded here):
  * The expected yield is the mean of the last three PUBLISHED seasons of the series. A pooled machine-learning model
    trained on the whole master table (63 crops) was tested the way a forecaster would meet the data, with a one-season
    publication lag and training only on what would have been published by then; no crop beat that mean by the bar set in
    advance, so none is served. The mean itself beat repeating the last published season for most crops.
  * History is lagged by one season: for a forecast of agricultural year Y the most recent season used is Y-2, because
    district yields are published more than a year late. `forecast_year` is therefore 2025 or 2026.
  * The 80% range is conformal around that mean, calibrated per crop and volatility flag on the last three out-of-sample
    years (Mondrian): volatile series get wider ranges. Its coverage was tested in advance (B1).
  * No weather, satellite or soil input: under the lag they bought about 1% and fell short of every bar.

Everything the outlook rests on is returned with it (last published season, recent history, whether the series is
volatile, how the mean and the tested model did on seasons they had not seen), so a reader can judge it.
"""

import json
import math
import os
import shutil
import sys

import numpy as np
import pandas as pd

from forecasting import add_history, build_panel

ROOT = os.path.dirname(os.path.abspath(__file__))
PROC = os.path.join(ROOT, "data", "processed")           # training inputs; not needed to serve
SERVING = os.path.join(ROOT, "serving")                   # everything the service reads; tracked in git
CARD_PATH = os.path.join(SERVING, "outlook.json")
SERIES_PATH = os.path.join(SERVING, "district_series.parquet")
TRACK_PATH = os.path.join(SERVING, "track_record.parquet")
SHAPES_PATH = os.path.join(SERVING, "district_shapes.json")

KEY = ["district_code", "crop", "season"]
SHIFT = 1
DATA_END = 2024
CAL_YEARS = (2022, 2023, 2024)
FORECAST_YEARS = (DATA_END + 1, DATA_END + 2)       # 2025 and 2026: the seasons not yet published
MIN_CAL_ROWS = 100                                   # per crop and flag; fewer falls back to the pooled quantile
MIN_MAP_DISTRICTS = 20                               # a crop and season grown in fewer districts is not offered as a map
METHOD = "the mean of the last three published seasons"


class ForecastError(ValueError):
    """A request that cannot be answered, with a reason a user can act on."""


def conformal_q(rel, level=0.8):
    r = np.sort(np.asarray(rel))
    if len(r) == 0:
        return float("nan")
    return float(r[min(len(r) - 1, math.ceil((len(r) + 1) * level) - 1)])


def _volatility(df):
    """Recent jumpiness of a series relative to its level (same definition as the evaluation)."""
    return ((df["yield_lag1"] - df["yield_lag2"]).abs() + (df["yield_lag2"] - df["yield_lag3"]).abs()) / 2 / df["yield_mean3"]


# ── build ───────────────────────────────────────────────────────────────────────────────────────
def build():
    """Write the serving files from the master table and the recorded evaluation. Nothing is fitted here: the mean needs no
    training, and the model that was tested did not clear its bar. Only the ranges are calibrated, on the last three
    out-of-sample years of the series' own mean."""
    sys.path.insert(0, os.path.join(ROOT, "pipeline"))
    import train_master as T

    with open(os.path.join(PROC, "master_models_metrics.json"), encoding="utf-8") as f:
        ev = json.load(f)
    b1, m3 = ev["b1"], ev["m3"]
    offered = sorted(b1["per_crop"])
    d = T.load()
    d = d[d.crop.isin(offered)]
    valid = T.valid_rows()
    valid = valid[valid.crop.isin(offered)]

    thr = float(d["vol"].quantile(0.8))
    cal = d[d.year.isin(CAL_YEARS)].copy()
    cal["rel"] = (cal["yield"] - cal["yield_mean3"]).abs() / cal["yield_mean3"]
    cal["flag"] = cal["vol"] >= thr
    pooled = {f: conformal_q(cal.loc[cal.flag == f, "rel"]) for f in (True, False)}
    crops = {}
    for crop in offered:
        g = cal[cal.crop == crop]
        q = {f: (conformal_q(g.loc[g.flag == f, "rel"]) if (g.flag == f).sum() >= MIN_CAL_ROWS else None) for f in (True, False)}
        mod = m3["per_crop"][crop]
        crops[crop] = {
            "q_flagged": q[True] if q[True] is not None else pooled[True], "q_unflagged": q[False] if q[False] is not None else pooled[False],
            "range_from_pooled": bool(q[True] is None or q[False] is None),
            "mean3": b1["per_crop"][crop],                                  # the mean against the last published season
            "model": {"dev": mod["dev"], "confirm_2024": mod["confirm_2024"], "years_better_than_mean3": mod["years_better_than_mean3"]}}  # the model that failed
    track = d[d.year >= 2018]
    series_n = int(valid.groupby(KEY).ngroups)

    card = {
        "method": METHOD, "data_through": DATA_END, "history_lag_seasons": SHIFT, "forecast_years": list(FORECAST_YEARS),
        "vol_threshold": thr, "ranges": {"calibration_years": list(CAL_YEARS), "pooled_q_flagged": pooled[True], "pooled_q_unflagged": pooled[False],
                                         "min_rows_per_crop_and_flag": MIN_CAL_ROWS},
        "crops": crops,
        "criteria": {
            "M1": {"first_protocol": {"pass": ev["m1_first_protocol"]["pass"], "groups": _group_skill(ev["m1_first_protocol"])},
                   "lag_consistent": {"groups": _group_skill(ev["m1"])}},
            "M2": {"pass": ev["m2"]["pass"], "dev_gain_pct": ev["m2"]["pooled"]["dev"]["gain_pct"], "gain_2024_pct": ev["m2"]["pooled"]["confirm_2024"]["gain_pct"],
                   "gain_by_year_pct": ev["m2"]["dev_gain_by_year_pct"],
                   "first_protocol": {"pass": ev["m2_first_protocol"]["pass"], "dev_gain_pct": ev["m2_first_protocol"]["pooled"]["dev"]["gain_pct"]}},
            "M3": {"pass": m3["pass"], "crops_tested": len(m3["per_crop"]), "crops_served": len(m3["served"]), "leaf": m3["leaf"],
                   "near_misses": sorted(({"crop": c, "dev_skill_vs_mean3_pct": v["dev"]["skill_vs_mean3_pct"], "years_better": v["years_better_than_mean3"],
                                           "skill_2024": v["confirm_2024"].get("skill_vs_mean3_pct")}      # None: no 2024 rows for this crop
                                          for c, v in m3["per_crop"].items() if v["dev"]["n"] >= 300 and v["dev"].get("skill_vs_mean3_pct", -99) >= 2.0),
                                         key=lambda x: -x["dev_skill_vs_mean3_pct"]),
                   "staples_in_pooled": {g: v["dev"]["skill_vs_mean3_pct"] for g, v in m3["staples_in_pooled"].items()}},
            "B1": {"pass": b1["pass"], "coverage": b1["coverage"]},
        },
        "headline": {
            "crops_offered": len(offered), "model_crops_tested": len(m3["per_crop"]), "model_crops_beating_mean": len(m3["served"]),
            "mean_beats_last_published_crops": b1["crops_mean3_beats_last"], "series": series_n, "districts": int(valid.district_code.nunique()),
            "range_coverage": {"dev_2018_2023": b1["coverage"]["dev"], "confirm_2024": b1["coverage"]["confirm_2024"]},
            "data_through": DATA_END, "forecast_years": list(FORECAST_YEARS), "method": METHOD},
    }
    os.makedirs(SERVING, exist_ok=True)
    shutil.rmtree(os.path.join(SERVING, "models"), ignore_errors=True)      # the previous generation's pickles are not part of this one
    with open(CARD_PATH, "w", encoding="utf-8") as f:
        json.dump(card, f, indent=1)

    # the data the service reads at runtime: every offered series' history, and the out-of-sample record of the mean
    valid[["district_code", "district_name", "state_name", "crop", "season", "year", "yield", "shape_id"]].to_parquet(SERIES_PATH, index=False, compression="zstd")
    track = track.rename(columns={"yield_mean3": "pred"})
    track[["district_code", "crop", "season", "year", "pred", "yield", "yield_anchor"]].to_parquet(TRACK_PATH, index=False, compression="zstd")
    shutil.copyfile(os.path.join(PROC, "district_shapes.json"), SHAPES_PATH)
    total = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(SERVING) for f in fs)
    print("headline:", card["headline"])
    print("serving/ total %.1f MB" % (total / 1e6))


def _group_skill(m1):
    return {g: {"dev_skill_vs_mean3_pct": v["dev"]["skill_vs_mean3_pct"], "skill_2024_vs_mean3_pct": v["confirm_2024"]["skill_vs_mean3_pct"]}
            for g, v in m1["groups"].items()}


# ── serving ─────────────────────────────────────────────────────────────────────────────────────
class DistrictForecaster:
    def __init__(self):
        self.frame = pd.read_parquet(SERIES_PATH)
        self.panel = build_panel(self.frame, KEY).sort_index()
        self.series = self.frame.groupby(KEY).year.agg(["min", "max"])
        self.names = self.frame.sort_values("year").groupby("district_code")[["district_name", "state_name"]].last()
        self.shape_ids = self.frame.groupby("district_code").shape_id.first()
        with open(CARD_PATH, encoding="utf-8") as f:
            self.card = json.load(f)
        self._preds, self._shapes, self._maps = None, None, {}

    def _crop(self, crop):
        c = self.card["crops"].get(crop)
        if c is None:
            raise ForecastError("No outlook is offered for %s: it was not among the tested crops, or has too little recent history." % crop)
        return c

    def evidence(self, crop):
        """How the mean, and the model that was tested against it, did on seasons they had not seen (2018-23 and 2024)."""
        c = self._crop(crop)
        return {"crop": crop, "range_from_pooled": c["range_from_pooled"], "mean3": c["mean3"], "model": c["model"],
                "range_coverage": self.card["criteria"]["B1"]["coverage"]}

    def options(self):
        """Every state and district that has a series on offer, and the crop / season pairs grown widely enough to map."""
        states, count = {}, {}
        for (dc, crop, season), r in self.series.iterrows():
            if crop not in self.card["crops"] or r["max"] < DATA_END - 3:      # needs a recent record to forecast from
                continue
            nm = self.names.loc[dc]
            d = states.setdefault(nm.state_name, {}).setdefault(int(dc), {"name": nm.district_name, "series": []})
            d["series"].append({"crop": crop, "season": season})
            count[(crop, season)] = count.get((crop, season), 0) + 1
        staple_first = lambda cs: (cs[0] not in ("Rice", "Wheat", "Maize"), cs[0], cs[1])      # the three staples lead every list
        for st in states.values():
            for d in st.values():
                d["series"].sort(key=lambda x: staple_first((x["crop"], x["season"])))
        pairs = [{"crop": c, "season": s, "districts": n} for (c, s), n in sorted(count.items(), key=lambda kv: staple_first(kv[0])) if n >= MIN_MAP_DISTRICTS]
        return {"states": states, "crop_seasons": pairs}

    def _rows(self, year, district_codes, crop, season):
        """History features for the requested series, using only seasons published by `year`."""
        df = pd.DataFrame({"year": year, "district_code": district_codes, "crop": crop, "season": season})
        df["state_name"] = self.names.loc[df.district_code, "state_name"].to_numpy()
        return add_history(df, self.panel, KEY, shift=SHIFT)

    def forecast(self, district_code, crop, season, year):
        c = self._crop(crop)
        if (district_code, crop, season) not in self.series.index:
            raise ForecastError("No %s (%s) records for this district." % (crop, season))
        if year not in FORECAST_YEARS:
            raise ForecastError("Outlooks are for %d or %d, the seasons whose yields are not yet published." % FORECAST_YEARS)
        nm = self.names.loc[district_code]
        row = self._rows(year, [district_code], crop, season)
        if int(row["history_seasons"].iloc[0]) == 0:
            raise ForecastError("No yield recorded in the three published seasons before %d, so there is nothing to base an outlook on." % year)
        r = row.iloc[0]
        mean3 = float(r["yield_mean3"])
        vol = float(_volatility(row).iloc[0])
        flagged = bool(np.isfinite(vol) and vol >= self.card["vol_threshold"])
        q = c["q_flagged"] if flagged else c["q_unflagged"]
        lag = next(k for k in (1, 2, 3) if not np.isnan(r["yield_lag%d" % k]))
        hist = self.frame[(self.frame.district_code == district_code) & (self.frame.crop == crop) & (self.frame.season == season)]
        hist = hist.sort_values("year").tail(6)
        notes = []
        if nm.state_name == "Madhya Pradesh":
            notes.append("Madhya Pradesh district figures in the source are about twice the Centre's official state total for wheat and have not "
                         "been checked for other crops; treat the level with caution. Changes from year to year are less affected.")
        if flagged:
            notes.append("This series has jumped around recently, so the range is wider.")
        if c["range_from_pooled"]:
            notes.append("There are too few past seasons of %s to calibrate its own range, so the range is the one measured across all crops." % crop)
        if year == FORECAST_YEARS[1]:
            notes.append("The most recent published season for this series is older than for a %d outlook; accuracy is lower." % FORECAST_YEARS[0])
        return {
            "district": {"code": int(district_code), "name": nm.district_name, "state": nm.state_name},
            "crop": crop, "season": season, "forecast_year": int(year), "unit": "tonnes/ha", "method": METHOD,
            "forecast": round(mean3, 2),
            "interval": {"level": 0.8, "low": round(mean3 * (1 - q), 2), "high": round(mean3 * (1 + q), 2),
                         "relative_half_width": round(q, 3), "method": "conformal, calibrated per crop and separately for volatile and stable series"},
            "baselines": {"last_published": {"value": round(float(r["yield_anchor"]), 2), "year": int(year - (lag + SHIFT))},
                          "mean_last_three_published": round(mean3, 2)},
            "trust": {"low_trust": flagged, "volatility": None if not np.isfinite(vol) else round(vol, 3), "seasons_of_history_used": int(r["history_seasons"])},
            "history": [{"year": int(y), "yield": round(float(v), 2)} for y, v in zip(hist.year, hist["yield"])],
            "evidence": self.evidence(crop),
            "notes": notes,
        }

    def shapes(self):
        """District outlines for the map (built by pipeline/build_map_shapes.py)."""
        if self._shapes is None:
            self._shapes = json.load(open(SHAPES_PATH, encoding="utf-8"))
        return self._shapes

    def map_data(self, crop, season, year):
        """Every district with a series for one crop, season and year, in one pass.

        Same rows and same range rule as `forecast()` (test_district.py checks that a district on the map and the same
        district on the forecast page agree), computed as one batch because a map needs ~600 at once."""
        c = self._crop(crop)
        if year not in FORECAST_YEARS:
            raise ForecastError("Outlooks are for %d or %d, the seasons whose yields are not yet published." % FORECAST_YEARS)
        key = (crop, season, year)
        if key in self._maps:
            return self._maps[key]
        s = self.series.reset_index()
        s = s[(s.crop == crop) & (s.season == season) & (s["max"] >= DATA_END - 3)]
        df = self._rows(year, s.district_code.to_numpy(), crop, season)
        df = df[df.history_seasons > 0].reset_index(drop=True)
        vol = _volatility(df).to_numpy()
        flagged = np.isfinite(vol) & (vol >= self.card["vol_threshold"])
        q = np.where(flagged, c["q_flagged"], c["q_unflagged"])
        rows = []
        for i, r in df.iterrows():
            last, mean3 = float(r["yield_anchor"]), float(r["yield_mean3"])
            sid = self.shape_ids[r.district_code]
            rows.append({
                "district_code": int(r.district_code), "name": self.names.loc[r.district_code, "district_name"],
                "state": r.state_name, "shape_id": None if pd.isna(sid) else sid,
                "forecast": round(mean3, 2), "low": round(mean3 * (1 - q[i]), 2), "high": round(mean3 * (1 + q[i]), 2),
                "last_published": round(last, 2),
                "change_vs_last_pct": round(100 * (mean3 / last - 1), 1) if last > 0 else None,
                "low_trust": bool(flagged[i])})
        out = {"crop": crop, "season": season, "forecast_year": int(year), "unit": "tonnes/ha", "method": METHOD,
               "evidence": self.evidence(crop), "districts": rows}
        self._maps[key] = out
        return out

    def track_record(self, district_code, crop, season):
        """Out-of-sample record of the mean: what it said for past seasons, each from seasons published by then, beside what was recorded."""
        self._crop(crop)
        if self._preds is None:
            self._preds = pd.read_parquet(TRACK_PATH)
        p = self._preds[(self._preds.district_code == district_code) & (self._preds.crop == crop) &
                        (self._preds.season == season)].sort_values("year")
        rows = [{"year": int(r.year), "forecast": round(float(r.pred), 2), "actual": round(float(r["yield"]), 2),
                 "last_published": round(float(r.yield_anchor), 2)} for _, r in p.iterrows()]
        out = {"seasons": rows}
        if rows:
            a = np.array([[x["forecast"], x["actual"], x["last_published"]] for x in rows])
            out["summary"] = {"n": len(rows), "mean_mae": round(float(np.abs(a[:, 0] - a[:, 1]).mean()), 3),
                              "last_published_mae": round(float(np.abs(a[:, 2] - a[:, 1]).mean()), 3)}
        return out


if __name__ == "__main__":
    build()

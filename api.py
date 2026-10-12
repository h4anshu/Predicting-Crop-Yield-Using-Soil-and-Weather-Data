"""
FastAPI backend for AgriPredict AI
Serves the ML model and data logic as REST endpoints.
"""

import json
import logging
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, Field, field_validator
import joblib
import numpy as np
import pandas as pd

from district_forecast import DistrictForecaster, ForecastError
from features import build_row
from forecasting import LAGS, build_panel

logger = logging.getLogger("agripredict")

# ── Config ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "crop_yield_model_v3.pkl")
METRICS_PATH = os.path.join(BASE_DIR, "model_metrics.json")
DATA_PATH = os.path.join(BASE_DIR, "master_dataset_enhanced.csv")
FALLBACK_DATA_PATH = os.path.join(BASE_DIR, "master_dataset_cleaned.csv")

SPECIAL_UNIT_CROPS = {"Coconut": "nuts/ha"}
DEFAULT_UNIT = "tonnes/ha"

# Browsers allowed to call this API. Set CORS_ORIGINS (comma-separated) on the deployed
# service to the frontend's origin, e.g. https://agripredict.vercel.app. The default
# is local development only, so a deploy that forgets the variable fails closed.
CORS_ORIGINS = [o.strip() for o in
                os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://localhost:4173").split(",")
                if o.strip()]

app = FastAPI(title="AgriPredict AI API")

app.add_middleware(GZipMiddleware, minimum_size=1000)   # the outlines and the all-district forecast are ~0.4 MB / 0.1 MB of JSON
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# ── Load model and data ──
# The model is loaded on first prediction rather than at import. Cloud Run scales to
# zero, so an import-time unpickle put the full model-load cost in front of every
# cold request -- including /api/options, which only needs the CSV.
_model = None

with open(METRICS_PATH, encoding="utf-8") as f:
    MODEL_METRICS = json.load(f)

EXCLUDED_CROPS = set(MODEL_METRICS["data_quality"]["excluded_crops"])


def get_model():
    # No fallback to an older artifact: v2 has no history features, so serving it would
    # return forecasts the current contract cannot describe. A missing model fails loudly.
    global _model
    if _model is None:
        _model = joblib.load(MODEL_PATH)
    return _model


def model_features():
    return list(get_model().feature_names_in_)

data_path = DATA_PATH if os.path.exists(DATA_PATH) else FALLBACK_DATA_PATH
data = pd.read_csv(data_path)
# The source CSV pads its labels ('Rabi       '). Strip once at load so every lookup below,
# the request validation and the model all see the same spelling.
for _col in ("state", "crop", "season"):
    data[_col] = data[_col].str.strip()

state_options = sorted(data["state"].dropna().unique().tolist())
season_options = sorted(data["season"].dropna().unique().tolist())
crop_options = sorted(c for c in data["crop"].dropna().unique().tolist()
                      if c not in EXCLUDED_CROPS)

# The yield history every forecast is anchored on. Coconut is excluded from the model, so
# it is excluded here too.
PANEL = build_panel(data[~data["crop"].isin(EXCLUDED_CROPS)]).sort_index()
KNOWN_SERIES = set(PANEL.index.droplevel("year"))
# state -> crop -> seasons that actually have records. A forecast needs a series to anchor
# on, so the frontend offers only these combinations rather than letting users pick ones
# that can only return a 422.
SERIES_CHOICES = {}
for _st, _cr, _se in sorted(KNOWN_SERIES):
    SERIES_CHOICES.setdefault(_st, {}).setdefault(_cr, []).append(_se)
YEAR_MIN = int(data["year"].min())
YEAR_MAX = int(data["year"].max())
FORECAST_YEAR_MAX = YEAR_MAX + 1   # one season past the data; beyond that no lag exists


def yield_unit(crop: str) -> str:
    return SPECIAL_UNIT_CROPS.get(crop, DEFAULT_UNIT)


def predict_with_interval(model, input_df, lo_pct=5, hi_pct=95):
    """Point forecast plus the spread of the 200 trees that produced it.

    This is a model-agreement interval, not a calibrated prediction interval: it
    reports where the ensemble's members disagree, which understates true predictive
    uncertainty because it cannot see error the whole forest shares. It replaces a
    hardcoded "confidence: 94" that was not measured from anything. Labelled honestly
    in the UI as ensemble agreement.
    """
    per_tree = model.predict_members(input_df)
    point = float(per_tree.mean(axis=0)[0])
    lo = float(np.percentile(per_tree[:, 0], lo_pct))
    hi = float(np.percentile(per_tree[:, 0], hi_pct))
    # relative width of the interval; reported as-is rather than being mapped onto
    # an invented 0-100 "confidence" score
    spread = (hi - lo) / point if point > 0 else 0.0
    return point, lo, hi, float(spread)


# ── Score helpers ──
def soil_health_score(N, P, K, pH):
    npk = N + P + K
    npk_score = min(100, (npk / 180) * 100)
    ph_score = 100 if 6.0 <= pH <= 7.5 else max(0, 100 - abs(pH - 6.75) * 30)
    return int(0.65 * npk_score + 0.35 * ph_score)


def climate_suitability_score(temp, rainfall, humidity):
    t_score = 100 - min(100, abs(temp - 26) * 6)
    r_score = 100 if 800 <= rainfall <= 2000 else max(0, 100 - abs(rainfall - 1400) / 30)
    h_score = 100 - min(100, abs(humidity - 70) * 2)
    return int((t_score + r_score + h_score) / 3)


def input_efficiency_score(fertilizer, pesticide, rainfall):
    fert_score = 100 if 100 <= fertilizer <= 250 else max(0, 100 - abs(fertilizer - 175) / 3)
    pest_score = 100 if 1 <= pesticide <= 5 else max(0, 100 - abs(pesticide - 3) * 15)
    return int((fert_score + pest_score) / 2)


def npk_balance_score(N, P, K):
    if N == 0:
        return 0
    p_ideal = N / 3
    k_ideal = N / 1.5
    p_dev = abs(P - p_ideal) / max(p_ideal, 1)
    k_dev = abs(K - k_ideal) / max(k_ideal, 1)
    return int(max(0, 100 - (p_dev + k_dev) * 50))


def rating_label(score):
    if score >= 80:
        return "Excellent"
    if score >= 65:
        return "Good"
    if score >= 50:
        return "Moderate"
    if score >= 30:
        return "Below avg"
    return "Poor"


# ── Pydantic models ──
# Labels must be ones the model was trained on: an unknown label one-hot encodes to all
# zeros without raising, so the category would be silently dropped from the forecast.
# Numeric bounds are the ranges the frontend controls expose and the dataset spans
# (rainfall peaks at 5,244 mm); anything outside them is a client error, not an input.
LABELS = {"state": set(state_options), "crop": set(crop_options), "season": set(season_options)}


class PredictRequest(BaseModel):
    state: str
    year: int = Field(ge=YEAR_MIN, le=FORECAST_YEAR_MAX)
    crop: str
    season: str
    N: float = Field(ge=0, le=200)
    P: float = Field(ge=0, le=120)
    K: float = Field(ge=0, le=100)
    pH: float = Field(ge=3.5, le=10)
    avg_temp_c: float = Field(ge=5, le=45)
    total_rainfall_mm: float = Field(ge=0, le=6000)
    avg_humidity_percent: float = Field(ge=0, le=100)
    fertilizer_per_ha: float = Field(ge=0, le=1000)
    pesticide_per_ha: float = Field(ge=0, le=20)
    area: float = Field(default=2.5, ge=0, le=100000)

    @field_validator("state", "crop", "season")
    @classmethod
    def known_label(cls, v, info):
        v = v.strip()
        if v not in LABELS[info.field_name]:
            raise ValueError(f"unknown {info.field_name} {v!r}; valid values are listed at /api/options")
        return v


# ── Endpoints ──
# Per-state soil and latest-year climate. v3 does not take `state` as a feature, so
# the State control only means something if selecting one loads that state's actual
# agronomic values -- otherwise the dropdown is inert. Shipped with /api/options so
# the frontend can fill the form on the first paint.
STATE_DEFAULTS = {}
for _st, _g in data.groupby("state"):
    _latest = _g.sort_values("year").iloc[-1]
    STATE_DEFAULTS[_st.strip()] = {
        "N": int(_latest["N"]), "P": int(_latest["P"]), "K": int(_latest["K"]),
        "pH": round(float(_latest["pH"]), 2),
        "avg_temp_c": round(float(_latest["avg_temp_c"]), 2),
        "total_rainfall_mm": round(float(_latest["total_rainfall_mm"]), 2),
        "avg_humidity_percent": round(float(_latest["avg_humidity_percent"]), 2),
        "fertilizer_per_ha": round(float(_latest["fertilizer_per_ha"]), 2),
        "pesticide_per_ha": round(float(_latest["pesticide_per_ha"]), 2),
    }

# Weather varies by state AND year, so the form can track the selected year too.
STATE_YEAR_CLIMATE = {}
for (_st, _yr), _g in data.groupby(["state", "year"]):
    _r = _g.iloc[0]
    STATE_YEAR_CLIMATE.setdefault(_st.strip(), {})[int(_yr)] = {
        "avg_temp_c": round(float(_r["avg_temp_c"]), 2),
        "total_rainfall_mm": round(float(_r["total_rainfall_mm"]), 2),
        "avg_humidity_percent": round(float(_r["avg_humidity_percent"]), 2),
    }


@app.get("/api/options")
def get_options():
    return {
        "states": state_options,
        "seasons": season_options,
        "crops": crop_options,
        "year_min": YEAR_MIN,
        "year_max": YEAR_MAX,
        "forecast_year_max": FORECAST_YEAR_MAX,
        "series": SERIES_CHOICES,
        "state_defaults": STATE_DEFAULTS,
    }


@app.get("/api/state-climate")
def get_state_climate(state: str, year: int):
    """Observed climate for one state-year, so the form tracks both controls."""
    st = STATE_YEAR_CLIMATE.get(state.strip(), {})
    if year in st:
        return {"found": True, **st[year]}
    if st:  # fall back to the nearest year we have
        nearest = min(st, key=lambda y: abs(y - year))
        return {"found": False, "nearest_year": nearest, **st[nearest]}
    return {"found": False}


@app.get("/api/stats")
def get_stats():
    skill = MODEL_METRICS["skill"]
    return {
        "total_records": len(data),
        "crops_covered": len(crop_options),
        "states_covered": len(state_options),
        "model_mae": MODEL_METRICS["headline"]["mae"],
        "baseline_mae": MODEL_METRICS["baselines"][skill["best_baseline"]]["mae"],
        "baseline_name": MODEL_METRICS["baselines"][skill["best_baseline"]]["label"],
        "skill_vs_baseline_pct": skill["vs_best_baseline_pct"],
        "year_min": YEAR_MIN,
        "year_max": YEAR_MAX,
        "years_covered": f"{YEAR_MIN} - {YEAR_MAX}",
    }


HEURISTICS_NOTE = ("Rule-of-thumb indicators with fixed thresholds that apply to every crop alike. "
                   "They are not produced by the model and do not change the forecast.")


def history_error(req):
    """Why a request has nothing to anchor on, in the user's terms."""
    if (req.state, req.crop, req.season) not in KNOWN_SERIES:
        return (f"No records of {req.crop} in {req.state} during {req.season}, "
                "so there is nothing to forecast from.")
    return (f"No {req.crop} yield is recorded for {req.state} ({req.season}) in the "
            f"{len(LAGS)} seasons before {req.year}. A forecast needs at least one.")


@app.post("/api/predict")
def predict(req: PredictRequest):
    N, P, K, pH = req.N, req.P, req.K, req.pH
    crop = req.crop
    payload = req.model_dump(exclude={"area"})

    try:
        input_df = build_row(payload, model_features(), PANEL)
        has_history = input_df["history_seasons"].iloc[0] > 0
        forecast = predict_with_interval(get_model(), input_df) if has_history else None
    except Exception:
        # Never answer a failed forecast with a number: a silent 0.0 here once looked
        # like a real (terrible) prediction. A server fault is a 500.
        logger.exception("prediction failed for %s", payload)
        raise HTTPException(status_code=500, detail="The forecast could not be computed.")
    if forecast is None:
        raise HTTPException(status_code=422, detail=history_error(req))
    prediction, lo, hi, spread = forecast

    row = input_df.iloc[0]
    last_lag = next(k for k in LAGS if not np.isnan(row[f"yield_lag{k}"]))
    baseline = {
        "label": ("Last season's recorded yield" if last_lag == 1
                  else "Mean of the recent seasons on record"),
        "value": round(float(row["yield_anchor"]), 2),
        "last_recorded_year": req.year - last_lag,
        "seasons_used": int(row["history_seasons"]),
    }

    unit = yield_unit(crop)
    # Compared with this series' own record before the forecast year. The crop's all-India
    # average mixes states and seasons whose yields differ several-fold, so it called a
    # series that is always high "HIGH PRODUCTIVITY" however the forecast moved.
    history = PANEL.loc[(req.state, crop, req.season)]
    avg_y = float(history[history.index < req.year].mean())
    diff_pct = (prediction - avg_y) / avg_y * 100 if avg_y > 0 else 0

    # Productivity badge, relative to the series' own average
    ratio = prediction / avg_y if avg_y > 0 else 1
    if ratio >= 1.1:
        badge = "HIGH PRODUCTIVITY"
    elif ratio >= 0.85:
        badge = "NORMAL PRODUCTIVITY"
    else:
        badge = "LOW PRODUCTIVITY"

    # Scores
    soil_s = soil_health_score(N, P, K, pH)
    climate_s = climate_suitability_score(req.avg_temp_c, req.total_rainfall_mm, req.avg_humidity_percent)
    input_s = input_efficiency_score(req.fertilizer_per_ha, req.pesticide_per_ha, req.total_rainfall_mm)
    npk_s = npk_balance_score(N, P, K)

    # Rule-of-thumb notes. Each states the band it tests; none quantifies an outcome the
    # model cannot support (an earlier "yield may increase by 8-12%" had no source).
    recs = []
    if 500 <= req.total_rainfall_mm <= 2500:
        recs.append({"type": "ok", "title": "Rainfall in range",
                     "desc": f"{req.total_rainfall_mm:,.0f} mm is inside the 500-2,500 mm band used here."})
    elif req.total_rainfall_mm < 500:
        recs.append({"type": "warn", "title": "Low Rainfall",
                     "desc": "Rainfall is below 500 mm. Consider irrigation planning."})
    else:
        recs.append({"type": "warn", "title": "High Rainfall",
                     "desc": "Rainfall is above 2,500 mm. Watch for waterlogging and disease risk."})

    if 20 <= req.avg_temp_c <= 32:
        recs.append({"type": "ok", "title": "Temperature in range",
                     "desc": f"{req.avg_temp_c:.1f} °C is inside the 20-32 °C band used here."})
    else:
        recs.append({"type": "warn", "title": "Temperature outside range",
                     "desc": f"{req.avg_temp_c:.1f} °C is outside the 20-32 °C band used here. Monitor crop stress."})

    if 6.0 <= pH <= 7.5:
        recs.append({"type": "ok", "title": "Soil pH in range",
                     "desc": f"pH {pH:.1f} is inside the 6.0-7.5 band used here."})
    elif pH < 6.0:
        recs.append({"type": "warn", "title": "Acidic Soil",
                     "desc": f"pH {pH:.1f} is acidic. Consider liming."})
    else:
        recs.append({"type": "warn", "title": "Alkaline Soil",
                     "desc": f"pH {pH:.1f} is alkaline. Consider sulfur application."})

    n_to_p = N / (P + 0.1)
    if n_to_p > 4:
        recs.append({"type": "warn", "title": "High N:P ratio",
                     "desc": f"N:P is {n_to_p:.1f}. A soil test would show whether phosphorus is limiting."})
    elif n_to_p < 1.5:
        recs.append({"type": "warn", "title": "Low N:P ratio",
                     "desc": f"N:P is {n_to_p:.1f}. Nitrogen may be limiting."})
    else:
        recs.append({"type": "ok", "title": "N:P in range",
                     "desc": f"N:P is {n_to_p:.1f}, inside the 1.5-4 band used here."})

    if baseline["value"] > 0:
        change = (prediction / baseline["value"] - 1) * 100
        recs.append({"type": "info", "title": "Versus the series' own history",
                     "desc": f"The forecast is {change:+.0f}% against {baseline['value']:.2f} {unit} "
                             f"recorded in {baseline['last_recorded_year']}."})

    return {
        "prediction": round(prediction, 2),
        "unit": unit,
        "badge": badge,
        "avg_yield": round(avg_y, 2),
        "diff_pct": round(diff_pct, 1),
        "baseline": baseline,
        "interval": {
            "low": round(lo, 2),
            "high": round(hi, 2),
            "level": "90% ensemble agreement",
            "note": "Range across the 200 trees. Reflects model agreement, not total "
                    "forecast uncertainty.",
        },
        "spread_pct": round(100 * spread, 1),
        "heuristics": {"note": HEURISTICS_NOTE},
        "scores": {
            "soil_health": {"value": soil_s, "rating": rating_label(soil_s),
                            "desc": f"Soil condition is {rating_label(soil_s).lower()}"},
            "climate_suitability": {"value": climate_s, "rating": rating_label(climate_s),
                                    "desc": f"Climate is {rating_label(climate_s).lower()}"},
            "input_efficiency": {"value": input_s, "rating": rating_label(input_s),
                                 "desc": f"Inputs are {rating_label(input_s).lower()}"},
            "npk_balance": {"value": npk_s, "rating": rating_label(npk_s),
                            "desc": f"NPK levels are {rating_label(npk_s).lower()}"},
        },
        "recommendations": recs,
    }


@app.get("/api/model-metrics")
def get_model_metrics():
    """Everything the Model Performance page renders: holdout scores, the honest
    core-staples breakdown, per-crop and per-state error, feature importance,
    input sensitivity vs v2, and the documented data-quality limits."""
    return MODEL_METRICS


# ── District forecasts (Phase 4, first slice) ──
# History-only, publication-lag aware; see district_forecast.py for what is and is not served and why.
_district = None


def get_district():
    global _district
    if _district is None:
        _district = DistrictForecaster()
    return _district


def _district_call(fn, *args):
    try:
        return fn(*args)
    except ForecastError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except FileNotFoundError:
        logger.exception("district forecast files missing")
        raise HTTPException(status_code=503, detail="District forecasts are not available on this server.")
    except Exception:
        logger.exception("district forecast failed for %s", args)
        raise HTTPException(status_code=500, detail="The forecast could not be computed.")


@app.get("/api/district/options")
def district_options():
    """state -> district -> the crop/season series that can be forecast."""
    return _district_call(lambda: get_district().options())


@app.get("/api/district/forecast")
def district_forecast(district_code: int, crop: str, season: str, year: int):
    return _district_call(lambda: get_district().forecast(district_code, crop, season, year))


@app.get("/api/district/map")
def district_map(crop: str, season: str, year: int):
    """Every forecastable district for one crop, season and year."""
    return _district_call(lambda: get_district().map_data(crop, season, year))


@app.get("/api/district/shapes")
def district_shapes():
    """Simplified district outlines (drawn by the map page; not for measuring areas)."""
    return _district_call(lambda: get_district().shapes())


@app.get("/api/district/track-record")
def district_track_record(district_code: int, crop: str, season: str):
    """Past forecasts of this series, each made by a model trained on earlier years only, beside what was recorded."""
    return _district_call(lambda: get_district().track_record(district_code, crop, season))


@app.get("/api/research")
def get_research():
    """Published evaluation artifacts from the study behind the model:
    a baseline sweep, a feature ablation, and paired significance tests."""
    out = {}
    for key, fname in [
        ("baselines", "baseline_comparison.csv"),
        ("ablation", "ablation_study_results.csv"),
        ("model_comparison", "stage3_model_comparison_results.csv"),
    ]:
        path = os.path.join(BASE_DIR, "extra", fname)
        if os.path.exists(path):
            out[key] = pd.read_csv(path).round(4).to_dict(orient="records")
    return out


@app.get("/api/soil-climate")
def get_soil_climate():
    """State soil profiles and the weather series behind them.

    Deliberately exposes the granularity caveat: these are single values per state
    (soil) and per state-year (weather), which is exactly why the model learns a
    regional rather than a field-level response.
    """
    soil = (data.groupby("state")[["N", "P", "K", "pH"]].first().round(2)
            .reset_index().to_dict(orient="records"))
    w = (data.groupby(["state", "year"])[
            ["avg_temp_c", "total_rainfall_mm", "avg_humidity_percent"]]
         .first().round(2).reset_index())
    weather = {}
    for st, g in w.groupby("state"):
        weather[st] = {
            "years": g["year"].tolist(),
            "temp": g["avg_temp_c"].tolist(),
            "rainfall": g["total_rainfall_mm"].tolist(),
            "humidity": g["avg_humidity_percent"].tolist(),
        }
    return {
        "soil": soil,
        "weather": weather,
        "granularity": {
            "soil": "one profile per state, constant across all 24 years",
            "weather": "one observation per state-year",
            "implication": "Every crop sharing a state-year has an identical soil and "
                           "climate vector, so the model resolves regional conditions, "
                           "not individual fields.",
        },
    }


@app.get("/api/historical")
def get_historical(crop: str, state: str = ""):
    crop_data = data[data["crop"] == crop]
    unit = yield_unit(crop)

    if state:
        filtered = crop_data[crop_data["state"] == state]
        if len(filtered) >= 5:
            crop_data = filtered
            label = f"{crop.strip()} — {state}"
        else:
            label = f"{crop.strip()} — All India"
    else:
        label = f"{crop.strip()} — All India"

    trend = crop_data.groupby("year")["yield"].mean().round(3)

    return {
        "label": label,
        "unit": unit,
        "years": trend.index.tolist(),
        "values": trend.values.tolist(),
        "avg": round(trend.mean(), 2) if len(trend) > 0 else 0,
        "min": round(trend.min(), 2) if len(trend) > 0 else 0,
        "max": round(trend.max(), 2) if len(trend) > 0 else 0,
    }


@app.get("/api/trends")
def get_trends():
    """Data for the Historical Trends page."""
    comparable = data[~data["crop"].str.strip().isin(SPECIAL_UNIT_CROPS.keys())]

    yearly = comparable.groupby("year")["yield"].mean().round(3)
    season_y = comparable.groupby("season")["yield"].mean().round(3).sort_values(ascending=False)
    state_y = comparable.groupby("state")["yield"].mean().round(3).sort_values(ascending=False)

    return {
        "yearly": {"years": yearly.index.tolist(), "values": yearly.values.tolist()},
        "by_season": {"seasons": season_y.index.tolist(), "values": season_y.values.tolist()},
        "by_state": {"states": state_y.index.tolist(), "values": state_y.values.tolist()},
    }


@app.get("/api/crop-insights/{crop_name}")
def crop_insights(crop_name: str):
    crop_data = data[data["crop"] == crop_name]
    u = yield_unit(crop_name)

    if len(crop_data) == 0:
        return {"error": "Crop not found"}

    hist_values = crop_data["yield"].dropna().tolist()

    return {
        "crop": crop_name,
        "unit": u,
        "records": len(crop_data),
        "avg_yield": round(crop_data["yield"].mean(), 2),
        "min_yield": round(crop_data["yield"].min(), 2),
        "max_yield": round(crop_data["yield"].max(), 2),
        "histogram_values": hist_values,
    }

"""
FastAPI backend for AgriPredict AI
Serves the ML model and data logic as REST endpoints.
"""

import json
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import joblib
import numpy as np
import pandas as pd

from features import build_row

# ── Config ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "crop_yield_model_v3.pkl")
LEGACY_MODEL_PATH = os.path.join(BASE_DIR, "crop_yield_model_v2_extra_trees.pkl")
METRICS_PATH = os.path.join(BASE_DIR, "model_metrics.json")
DATA_PATH = os.path.join(BASE_DIR, "master_dataset_enhanced.csv")
FALLBACK_DATA_PATH = os.path.join(BASE_DIR, "master_dataset_cleaned.csv")

SPECIAL_UNIT_CROPS = {"Coconut": "nuts/ha", "Coconut ": "nuts/ha"}
DEFAULT_UNIT = "tonnes/ha"

app = FastAPI(title="AgriPredict AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    global _model
    if _model is None:
        path = MODEL_PATH if os.path.exists(MODEL_PATH) else LEGACY_MODEL_PATH
        _model = joblib.load(path)
    return _model


def model_features():
    return list(get_model().feature_names_in_)

data_path = DATA_PATH if os.path.exists(DATA_PATH) else FALLBACK_DATA_PATH
data = pd.read_csv(data_path)

state_options = sorted(data["state"].dropna().unique().tolist())
season_options = sorted(data["season"].dropna().unique().tolist())
crop_options = sorted(c for c in data["crop"].dropna().unique().tolist()
                      if c.strip() not in EXCLUDED_CROPS)
crop_yield_ranges = data.groupby("crop")["yield"].agg(["min", "max", "mean", "median"]).round(3)


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
    pre = model.named_steps["preprocessing"]
    est = model.named_steps["model"]
    Xt = pre.transform(input_df)
    per_tree = np.stack([t.predict(Xt) for t in est.estimators_])
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
class PredictRequest(BaseModel):
    state: str
    year: int
    crop: str
    season: str
    N: float
    P: float
    K: float
    pH: float
    avg_temp_c: float
    total_rainfall_mm: float
    avg_humidity_percent: float
    fertilizer_per_ha: float
    pesticide_per_ha: float
    area: float = 2.5


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
        "states": [s.strip() for s in state_options],
        "seasons": [s.strip() for s in season_options],
        "crops": [c.strip() for c in crop_options],
        "year_min": int(data["year"].min()),
        "year_max": int(data["year"].max()),
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
    return {
        "total_records": len(data),
        "crops_covered": len(crop_options),
        "states_covered": len(state_options),
        "model_accuracy": "%d%%" % round(100 * MODEL_METRICS["headline"]["r2"]),
        "model_accuracy_core": "%d%%" % round(100 * MODEL_METRICS["core_staples"]["r2"]),
        "model_mae": MODEL_METRICS["headline"]["mae"],
        "year_min": int(data["year"].min()),
        "year_max": int(data["year"].max()),
        "years_covered": f"{int(data['year'].min())} - {int(data['year'].max())}",
    }


@app.post("/api/predict")
def predict(req: PredictRequest):
    N, P, K, pH = req.N, req.P, req.K, req.pH
    avg_temp_c = req.avg_temp_c
    total_rainfall_mm = req.total_rainfall_mm
    avg_humidity_percent = req.avg_humidity_percent
    fertilizer_per_ha = req.fertilizer_per_ha
    pesticide_per_ha = req.pesticide_per_ha
    year = req.year
    state = req.state
    season = req.season
    crop = req.crop

    payload = {
        "N": N, "P": P, "K": K, "pH": pH,
        "avg_temp_c": avg_temp_c, "avg_humidity_percent": avg_humidity_percent,
        "total_rainfall_mm": total_rainfall_mm,
        "fertilizer_per_ha": fertilizer_per_ha, "pesticide_per_ha": pesticide_per_ha,
        "year": year, "season": season, "crop": crop,
    }
    model = get_model()
    feats = model_features()
    input_df = build_row(payload, feats)
    N_to_P_ratio = input_df["N_to_P_ratio"].iloc[0] if "N_to_P_ratio" in input_df else N / (P + 0.1)

    try:
        prediction, lo, hi, spread = predict_with_interval(model, input_df)
    except Exception:
        prediction, lo, hi, spread = 0.0, 0.0, 0.0, 0.0

    unit = yield_unit(crop)
    avg_y = float(crop_yield_ranges.loc[crop, "mean"]) if crop in crop_yield_ranges.index else 0
    diff_pct = ((prediction - avg_y) / avg_y * 100) if avg_y > 0 else 0

    # Productivity badge
    if avg_y > 0:
        ratio = prediction / avg_y
        if ratio >= 1.1:
            badge = "HIGH PRODUCTIVITY"
        elif ratio >= 0.85:
            badge = "NORMAL PRODUCTIVITY"
        else:
            badge = "LOW PRODUCTIVITY"
    else:
        badge = "ESTIMATE"

    # Scores
    soil_s = soil_health_score(N, P, K, pH)
    climate_s = climate_suitability_score(avg_temp_c, total_rainfall_mm, avg_humidity_percent)
    input_s = input_efficiency_score(fertilizer_per_ha, pesticide_per_ha, total_rainfall_mm)
    npk_s = npk_balance_score(N, P, K)

    # Recommendations
    recs = []
    if 500 <= total_rainfall_mm <= 2500:
        recs.append({"type": "ok", "title": "Favorable Rainfall",
                     "desc": f"Rainfall is within the optimal range for {crop.strip()}."})
    elif total_rainfall_mm < 500:
        recs.append({"type": "warn", "title": "Low Rainfall",
                     "desc": "Rainfall is below optimal. Consider irrigation planning."})
    else:
        recs.append({"type": "warn", "title": "High Rainfall",
                     "desc": "Very high rainfall — watch for waterlogging and disease risk."})

    if 20 <= avg_temp_c <= 32:
        recs.append({"type": "ok", "title": "Optimal Temperature",
                     "desc": "Temperature conditions are ideal for maximum yield."})
    else:
        recs.append({"type": "warn", "title": "Suboptimal Temperature",
                     "desc": "Temperature is outside ideal range — monitor crop stress."})

    if 6.0 <= pH <= 7.5:
        recs.append({"type": "ok", "title": "Soil pH Optimal",
                     "desc": "Soil pH is in the optimal range for this crop."})
    elif pH < 6.0:
        recs.append({"type": "warn", "title": "Acidic Soil",
                     "desc": f"pH {pH:.1f} is acidic. Consider liming."})
    else:
        recs.append({"type": "warn", "title": "Alkaline Soil",
                     "desc": f"pH {pH:.1f} is alkaline. Consider sulfur application."})

    if N_to_P_ratio > 4:
        recs.append({"type": "warn", "title": "Increase Phosphorus",
                     "desc": "Increase phosphorus by ~10% for better yield outcome."})
    elif N_to_P_ratio < 1.5:
        recs.append({"type": "warn", "title": "Increase Nitrogen",
                     "desc": "Nitrogen is low relative to phosphorus. Boost N inputs."})
    else:
        recs.append({"type": "ok", "title": "Balanced NPK",
                     "desc": "Your N:P ratio is well balanced for most crops."})

    if avg_y > 0:
        if prediction >= avg_y * 1.1:
            recs.append({"type": "info", "title": "Yield Potential",
                         "desc": "With optimized inputs, yield may increase by 8-12%."})
        elif prediction < avg_y * 0.85:
            recs.append({"type": "info", "title": "Optimization Tip",
                         "desc": "Review soil and inputs — historical yields suggest higher potential."})
        else:
            recs.append({"type": "info", "title": "Yield Potential",
                         "desc": "Your inputs align with historically average yields."})
    else:
        recs.append({"type": "info", "title": "Yield Potential",
                     "desc": "Predictions for this crop are based on limited historical data."})

    return {
        "prediction": round(prediction, 2),
        "unit": unit,
        "badge": badge,
        "avg_yield": round(avg_y, 2),
        "diff_pct": round(diff_pct, 1),
        "interval": {
            "low": round(lo, 2),
            "high": round(hi, 2),
            "level": "90% ensemble agreement",
            "note": "Range across the 200 trees. Reflects model agreement, not total "
                    "forecast uncertainty.",
        },
        "spread_pct": round(100 * spread, 1),
        "scores": {
            "soil_health": {"value": soil_s, "rating": rating_label(soil_s),
                            "desc": f"Soil condition is {rating_label(soil_s).lower()} for {crop.strip()}"},
            "climate_suitability": {"value": climate_s, "rating": rating_label(climate_s),
                                    "desc": f"Climate is highly suitable for this crop" if climate_s >= 80 else f"Climate is {rating_label(climate_s).lower()} for this crop"},
            "input_efficiency": {"value": input_s, "rating": rating_label(input_s),
                                 "desc": f"Inputs are {rating_label(input_s).lower()} optimized" if input_s >= 65 else f"Inputs are {rating_label(input_s).lower()}"},
            "npk_balance": {"value": npk_s, "rating": rating_label(npk_s),
                            "desc": f"NPK levels are well balanced for this crop" if npk_s >= 80 else f"NPK levels are {rating_label(npk_s).lower()}"},
        },
        "recommendations": recs,
    }


@app.get("/api/model-metrics")
def get_model_metrics():
    """Everything the Model Performance page renders: holdout scores, the honest
    core-staples breakdown, per-crop and per-state error, feature importance,
    input sensitivity vs v2, and the documented data-quality limits."""
    return MODEL_METRICS


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

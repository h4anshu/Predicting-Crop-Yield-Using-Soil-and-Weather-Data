"""
FastAPI backend for AgriPredict AI.

One dataset (the master table, see data/DATA_CARD.md) behind every endpoint, and one expected-yield method: the mean of the
last three published seasons, with a tested range (a model was tested against it and did not beat it). The master table is
too big to ship, so the service reads the small views derived from it by pipeline/export_serving.py and the files written
by district_forecast.py, all in serving/.
"""

import json
import logging
import os

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from district_forecast import DistrictForecaster, ForecastError

logger = logging.getLogger("agripredict")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVING = os.path.join(BASE_DIR, "serving")
SPECIAL_UNITS = {"Coconut": "nuts/ha"}        # nuts, not tonnes: never averaged with the rest

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
    allow_methods=["GET"],
    allow_headers=["Content-Type"],
)


def _json(*parts):
    with open(os.path.join(SERVING, *parts), encoding="utf-8") as f:
        return json.load(f)


# ── The dataset: small views of the master table ──
DATASET = _json("dataset_stats.json")
CROPS = _json("crop_summary.json")
SOIL_CLIMATE = _json("soil_climate.json")
VIEW = pd.read_parquet(os.path.join(SERVING, "state_view.parquet")).rename(columns={"state_name": "state"})
STATES = sorted(VIEW["state"].unique().tolist())
SEASONS = sorted(VIEW["season"].unique().tolist())
CROP_LIST = sorted(CROPS)
YEAR_MIN, YEAR_MAX = DATASET["year_min"], DATASET["year_max"]

# Two scale-free views, so the mix of crops (sugarcane against pulses) cannot move a comparison:
#   index        a (state, crop, season) series against its own average over the years (1.0 = its typical yield)
#   vs_national  a state's yield against the national yield (production / area) of the same crop, season and year
_own = VIEW.groupby(["state", "crop", "season"])["yield"].transform("mean")
_nat = VIEW.groupby(["crop", "season", "year"])[["production", "area"]].transform("sum")
VIEW = VIEW.assign(index=VIEW["yield"] / _own, vs_national=VIEW["yield"] / (_nat["production"] / _nat["area"]))
# Comparisons use district-sourced rows only: the few state-only rows (Delhi and a handful of other series) come from the original
# dataset and some are not credible (Delhi potato at 66 t/ha, maize at 8 t/ha against a national 12 and 2).
_comparable = VIEW[~VIEW["crop"].isin(SPECIAL_UNITS) & (VIEW["districts"] > 0)]


def yield_unit(crop: str) -> str:
    return SPECIAL_UNITS.get(crop, "tonnes/ha")


# ── What the outlook rests on: method, evidence, the criteria set in advance ──
def model_card():
    try:
        return _json("outlook.json")
    except FileNotFoundError:
        return None


# ── Endpoints ──
@app.get("/api/options")
def get_options():
    return {"states": STATES, "seasons": SEASONS, "crops": CROP_LIST, "year_min": YEAR_MIN, "year_max": YEAR_MAX}


@app.get("/api/stats")
def get_stats():
    """What the dashboard shows: the size and composition of the one dataset, and the headline of the outlook."""
    card = model_card()
    return {"dataset": DATASET, "outlook": card["headline"] if card else None}


@app.get("/api/model")
def get_model():
    """Everything the Model page renders: the method, per-crop results of the mean and the model tested against it, and the criteria set in advance."""
    card = model_card()
    if card is None:
        raise HTTPException(status_code=503, detail="The evaluation is not available on this server.")
    return {**card, "dataset": DATASET}


@app.get("/api/trends")
def get_trends():
    """Data for the Historical Trends page."""
    yearly = _comparable.groupby("year")["index"].mean().mul(100).round(1)
    by_state = _comparable.groupby("state")["vs_national"].mean().mul(100).round(1).sort_values(ascending=False)
    records = _comparable.groupby("state").size()
    return {
        "yearly": {"years": yearly.index.tolist(), "values": yearly.values.tolist()},
        "by_state": {"states": by_state.index.tolist(), "values": by_state.values.tolist(), "records": records[by_state.index].tolist()},
    }


@app.get("/api/historical")
def get_historical(crop: str, state: str = ""):
    """Yield of one crop by year: a state's, or all India's (production over area across districts)."""
    rows = VIEW[VIEW["crop"] == crop]
    label = f"{crop} — All India"
    if state and len(rows[rows["state"] == state]) >= 5:
        rows, label = rows[rows["state"] == state], f"{crop} — {state}"
    by = rows.groupby("year")[["production", "area"]].sum()
    trend = (by["production"] / by["area"]).dropna().round(3)
    return {
        "label": label, "unit": yield_unit(crop),
        "years": trend.index.tolist(), "values": trend.values.tolist(),
        "avg": round(float(trend.mean()), 2) if len(trend) else 0,
        "min": round(float(trend.min()), 2) if len(trend) else 0,
        "max": round(float(trend.max()), 2) if len(trend) else 0,
    }


@app.get("/api/crop-insights/{crop_name}")
def crop_insights(crop_name: str):
    c = CROPS.get(crop_name)
    if c is None:
        return {"error": "Crop not found"}
    return {"crop": crop_name, **c}


@app.get("/api/soil-climate")
def get_soil_climate():
    """Soil Health Card shares by state, and season-window weather by state and year (granularity caveat included)."""
    return SOIL_CLIMATE


# ── District forecasts ──
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

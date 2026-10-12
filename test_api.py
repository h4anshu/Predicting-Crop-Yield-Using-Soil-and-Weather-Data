"""
Guards the API's failure behaviour:  python test_api.py

Each case here used to return HTTP 200 with a plausible-looking number:
  - an unknown crop/season one-hot encoded to zeros and was forecast anyway
  - any exception inside the forecast was swallowed into a prediction of 0.0
  - a state/crop/season with no records was forecast from nothing
Endpoint functions are called directly, which avoids a test-client dependency.
"""

import contextlib
import logging

from fastapi import HTTPException
from pydantic import ValidationError

import api

VALID = dict(
    state="Punjab", year=2019, crop="Wheat", season="Rabi",
    N=150, P=50, K=40, pH=8.0, avg_temp_c=23.3, total_rainfall_mm=1138.97,
    avg_humidity_percent=55.64, fertilizer_per_ha=171.42, pesticide_per_ha=0.37,
)


@contextlib.contextmanager
def rejects(exc, containing=""):
    try:
        yield
    except exc as e:
        text = str(getattr(e, "detail", e))
        assert containing in text, "expected %r in %r" % (containing, text)
    else:
        raise AssertionError("expected %s" % exc.__name__)


def request(**overrides):
    return api.PredictRequest(**{**VALID, **overrides})


def test_valid_forecast():
    out = api.predict(request())
    assert 0 < out["prediction"] < 120
    assert out["interval"]["low"] <= out["prediction"] <= out["interval"]["high"]
    assert out["baseline"]["seasons_used"] == 3 and out["baseline"]["last_recorded_year"] == 2018
    own = api.PANEL.loc[("Punjab", "Wheat", "Rabi")]
    assert out["avg_yield"] == round(float(own[own.index < 2019].mean()), 2), "average is not the series' own"
    assert "model" in out["heuristics"]["note"]
    assert not any("8-12%" in r["desc"] for r in out["recommendations"])


def test_labels_are_validated_and_normalised():
    for field, bad in [("crop", "Quinoa"), ("crop", "Coconut"), ("season", "Monsoon"), ("state", "Atlantis")]:
        with rejects(ValidationError, "unknown %s" % field):
            request(**{field: bad})
    padded = api.predict(request(season="Rabi       ", crop=" Wheat "))
    assert padded["prediction"] == api.predict(request())["prediction"]


def test_numeric_ranges():
    for field, bad in [("pH", 14), ("N", -1), ("total_rainfall_mm", 90000), ("avg_humidity_percent", 130),
                       ("year", api.FORECAST_YEAR_MAX + 1), ("year", api.YEAR_MIN - 1),
                       ("avg_temp_c", float("nan"))]:
        with rejects(ValidationError):
            request(**{field: bad})


def test_no_series_is_a_422_not_a_forecast():
    with rejects(HTTPException, "No records of Rice in Punjab during Winter"):
        api.predict(request(crop="Rice", season="Winter"))
    # a series that exists, asked about the year it starts: nothing earlier to anchor on
    state, crop, season = next(k for k in sorted(api.KNOWN_SERIES)
                               if api.PANEL[k].index.min() > api.YEAR_MIN + 1)
    first = int(api.PANEL[(state, crop, season)].index.min())
    with rejects(HTTPException, "A forecast needs at least one") as _:
        api.predict(request(state=state, crop=crop, season=season, year=first))


def test_model_failure_is_a_500_never_a_zero():
    def broken():
        raise RuntimeError("boom")

    real = api.get_model
    api.get_model = broken
    logging.disable(logging.CRITICAL)   # the traceback is logged on purpose; keep test output clean
    try:
        try:
            api.predict(request())
        except HTTPException as e:
            assert e.status_code == 500 and "boom" not in e.detail
        else:
            raise AssertionError("a failing model must not return a forecast")
    finally:
        logging.disable(logging.NOTSET)
        api.get_model = real


def test_options_only_offer_forecastable_series():
    opts = api.get_options()
    assert opts["forecast_year_max"] == opts["year_max"] + 1
    state = next(iter(opts["series"]))
    crop = next(iter(opts["series"][state]))
    season = opts["series"][state][crop][0]
    api.predict(request(state=state, crop=crop, season=season, year=opts["year_max"]))


def test_cors_is_not_wildcard():
    cors = next(m for m in api.app.user_middleware if m.cls.__name__ == "CORSMiddleware")
    assert "*" not in cors.kwargs["allow_origins"]
    assert not cors.kwargs.get("allow_credentials", False)


def test_stats_report_skill_against_a_baseline():
    s = api.get_stats()
    assert s["baseline_mae"] > 0 and "skill_vs_baseline_pct" in s and "model_accuracy" not in s


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        fn()
        print("  ok  %s" % name)
    print("all %d api checks passed" % len(tests))

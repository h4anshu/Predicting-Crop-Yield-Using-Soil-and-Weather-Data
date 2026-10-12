"""
Guards the API's data endpoints:  python test_api.py      (needs pipeline/export_serving.py and district_forecast.py run first)

Endpoint functions are called directly, which avoids a test-client dependency. What matters here:
  - every figure the app shows about the data comes from one place (the views of the master table), so they must add up
  - the by-year trend is an index that a change in the crop mix cannot move
  - the model description says what the evaluation found, including what failed
"""

from fastapi import HTTPException

import api


def rejects(fn, status):
    try:
        fn()
    except HTTPException as e:
        assert e.status_code == status, e.status_code
    else:
        raise AssertionError("expected HTTP %d" % status)


def test_options_cover_every_state_season_and_crop():
    o = api.get_options()
    assert len(o["states"]) >= 30 and len(o["crops"]) >= 90 and {"Kharif", "Rabi"} <= set(o["seasons"])
    assert set(o["crops"]) == set(api.CROPS) and o["year_max"] >= 2024


def test_stats_describe_one_dataset():
    d = api.get_stats()["dataset"]
    assert d["district_rows"] + d["state_only_rows"] == d["rows"] > 400000
    assert d["districts"] >= 700 and d["year_min"] <= 1997 and d["year_max"] >= 2024
    assert sum(g["columns"] for g in d["groups"]) == d["columns"], "a column belongs to no group"
    assert 0 < d["state_vs_district"]["yield_within_2pct"] <= 100


def test_yearly_trend_is_an_index_not_a_crop_mix():
    y = api.get_trends()["yearly"]
    assert len(y["years"]) >= 25 and all(50 < v < 150 for v in y["values"]), y["values"]
    assert y["values"][-1] > y["values"][0], "yields did not rise over 25 years: the index is wrong"


def test_state_ranking_is_against_the_national_yield_not_the_crop_mix():
    s = api.get_trends()["by_state"]
    assert all(50 < v < 200 for v in s["values"]), s["values"]
    assert s["states"].index("Punjab") < s["states"].index("Bihar"), "Punjab out-yields Bihar crop for crop"
    assert "Delhi" not in s["states"], "Delhi has only state-level rows from the original dataset, which are not comparable"


def test_historical_is_production_over_area():
    h = api.get_historical("Wheat")
    assert h["unit"] == "tonnes/ha" and all(2.0 < v < 4.5 for v in h["values"]), h["values"]
    pb = api.get_historical("Wheat", "Punjab")
    assert pb["label"] == "Wheat — Punjab" and pb["avg"] > h["avg"]
    assert api.get_historical("Coconut")["unit"] == "nuts/ha"


def test_crop_insights_histogram_accounts_for_every_record():
    c = api.crop_insights("Rice")
    assert sum(c["histogram"]["counts"]) == c["records"] and len(c["histogram"]["edges"]) == len(c["histogram"]["counts"]) + 1
    assert c["p5"] < c["p50"] < c["p95"] and "error" in api.crop_insights("Quinoa")


def test_soil_and_climate_are_district_records_summarised():
    s = api.get_soil_climate()
    punjab = s["soil"]["Punjab"]
    assert punjab["samples"] > 0 and all(0 <= punjab[k] <= 1 for k in ("n_low", "n_high", "oc_low", "ph_alkaline"))
    w = s["weather"]["Punjab"]
    assert len(w["years"]) == len(w["kharif_rain"]) and 300 < max(v for v in w["kharif_rain"] if v) < 2500
    assert {"soil", "weather", "implication"} <= set(s["granularity"])


def test_model_card_reports_what_the_evaluation_found():
    m = api.get_model()
    assert {"M1", "M2", "M3", "B1"} <= set(m["criteria"]) and m["dataset"]["rows"] == api.DATASET["rows"]
    h = m["headline"]
    assert h["crops_offered"] == len(m["crops"]) and h["model_crops_beating_mean"] == m["criteria"]["M3"]["crops_served"]
    assert set(m["crops"]) <= set(api.CROPS)
    # "no model cleared the bar" must be what the per-crop numbers say
    cleared = [c for c, v in m["crops"].items()
               if v["model"]["dev"]["n"] >= 300 and v["model"]["dev"]["skill_vs_mean3_pct"] >= 2.0 and v["model"]["years_better_than_mean3"] >= 4
               and (v["model"]["confirm_2024"].get("skill_vs_mean3_pct") if v["model"]["confirm_2024"].get("skill_vs_mean3_pct") is not None else -1) >= 0]
    assert len(cleared) == h["model_crops_beating_mean"], cleared
    assert m["criteria"]["B1"]["pass"] and 0.72 <= m["criteria"]["B1"]["coverage"]["dev"] <= 0.88
    assert api.get_stats()["outlook"] == h


def test_missing_model_description_is_a_503():
    real = api.model_card
    api.model_card = lambda: None
    try:
        rejects(api.get_model, 503)
        assert api.get_stats()["outlook"] is None
    finally:
        api.model_card = real


def test_cors_is_not_wildcard():
    cors = next(m for m in api.app.user_middleware if m.cls.__name__ == "CORSMiddleware")
    assert "*" not in cors.kwargs["allow_origins"] and cors.kwargs["allow_methods"] == ["GET"]
    assert not cors.kwargs.get("allow_credentials", False)


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        fn()
        print("  ok  %s" % name)
    print("all %d api checks passed" % len(tests))

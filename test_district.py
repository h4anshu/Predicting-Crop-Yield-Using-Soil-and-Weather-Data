"""
Guards the district forecast service:  python test_district.py   (needs `python district_forecast.py` run first)

Direct calls, no test-client dependency. What matters here:
  - a forecast for year Y must not see anything published after Y-2 (the publication lag), whatever is in the panel
  - bad requests are refused with a reason instead of answered
  - the interval, baselines and trust flag come back with every forecast
"""

import logging

from fastapi import HTTPException

import api
import district_forecast as D

F = api.get_district()
# a well-populated series: Punjab-like staple in a big district
OPT = F.options()
STATE = "Uttar Pradesh"
DC, INFO = next(iter(OPT[STATE].items()))
WHEAT = next(s for s in INFO["series"] if s["crop"] == "Wheat") if any(s["crop"] == "Wheat" for s in INFO["series"]) else INFO["series"][0]


def test_options_shape():
    assert len(OPT) > 20 and all(isinstance(d, dict) for st in OPT.values() for d in st.values())
    crops = {s["crop"] for st in OPT.values() for d in st.values() for s in d["series"]}
    assert crops <= {"Rice", "Maize", "Wheat"}


def test_forecast_contract():
    out = api.district_forecast(DC, WHEAT["crop"], WHEAT["season"], 2025)
    assert out["forecast"] > 0 and out["interval"]["low"] < out["forecast"] < out["interval"]["high"]
    assert out["baselines"]["last_published"]["year"] <= 2025 - 2
    assert set(out["trust"]) >= {"low_trust", "volatility", "seasons_of_history_used"}
    assert out["model"]["skill"]["dev_2018_2023"]["skill_vs_mean3_pct"] is not None
    assert "no weather or satellite" in out["model"]["inputs"]
    assert all(h["year"] <= D.DATA_END for h in out["history"])


def test_volatile_series_get_wider_intervals():
    seen = {False: [], True: []}
    for st in OPT.values():
        for dc, info in st.items():
            for s in info["series"]:
                try:
                    r = F.forecast(dc, s["crop"], s["season"], 2025)
                except D.ForecastError:
                    continue
                seen[r["trust"]["low_trust"]].append(r["interval"]["relative_half_width"])
            if len(seen[True]) > 30 and len(seen[False]) > 30:
                break
        if len(seen[True]) > 30 and len(seen[False]) > 30:
            break
    assert seen[True] and seen[False] and min(seen[True]) > max(seen[False]) * 0.99


def test_publication_lag_is_enforced():
    """A 2025 forecast may use seasons up to 2023 only. Poisoning 2024 must not move it (it is not yet published),
    and poisoning 2023 must (control: the check can fail)."""
    real = F.panel
    clean = F.forecast(DC, WHEAT["crop"], WHEAT["season"], 2025)["forecast"]
    try:
        for year, should_move in ((2024, False), (2023, True)):
            poisoned = real.copy()
            poisoned[poisoned.index.get_level_values("year") == year] = 999.0
            F.panel = poisoned
            moved = F.forecast(DC, WHEAT["crop"], WHEAT["season"], 2025)["forecast"] != clean
            assert moved == should_move, "poisoning %d: forecast moved=%s, expected %s" % (year, moved, should_move)
    finally:
        F.panel = real


def test_bad_requests_are_refused():
    cases = [(DC, "Sugarcane", "Kharif", 2025), (DC, WHEAT["crop"], WHEAT["season"], 2024), (DC, WHEAT["crop"], WHEAT["season"], 2030),
             (DC, "Wheat", "Kharif", 2025), (999999, "Wheat", "Rabi", 2025)]
    for args in cases:
        try:
            api.district_forecast(*args)
        except HTTPException as e:
            assert e.status_code == 422 and e.detail
        else:
            raise AssertionError("expected a refusal for %r" % (args,))


def test_track_record_is_out_of_sample():
    t = api.district_track_record(DC, WHEAT["crop"], WHEAT["season"])
    assert t["seasons"] and all(2017 <= r["year"] <= 2024 for r in t["seasons"])
    assert t["summary"]["n"] == len(t["seasons"])


def test_madhya_pradesh_carries_the_source_warning():
    dc = next(iter(OPT["Madhya Pradesh"]))
    s = OPT["Madhya Pradesh"][dc]["series"][0]
    out = api.district_forecast(dc, s["crop"], s["season"], 2025)
    assert any("Madhya Pradesh" in n for n in out["notes"])


def test_map_agrees_with_single_forecasts():
    """The map computes ~600 forecasts in one batch. Any district on it must match the forecast page exactly."""
    for crop, season in (("Rice", "Kharif"), ("Maize", "Kharif"), ("Wheat", "Rabi")):
        m = api.district_map(crop, season, 2025)
        assert len(m["districts"]) > 300, (crop, len(m["districts"]))
        for d in m["districts"][:: max(1, len(m["districts"]) // 12)]:
            one = F.forecast(d["district_code"], crop, season, 2025)
            assert one["forecast"] == d["forecast"], (crop, d["name"], one["forecast"], d["forecast"])
            assert one["interval"]["low"] == d["low"] and one["interval"]["high"] == d["high"]
            assert one["trust"]["low_trust"] == d["low_trust"]
            assert one["baselines"]["last_published"]["value"] == d["last_published"]


def test_map_shapes_cover_every_district():
    shapes = api.district_shapes()
    west, south, east, north = shapes["bounds"]
    assert 66 < west < 70 and 6 < south < 8 and 96 < east < 98 and 35 < north < 37
    for crop, season in (("Rice", "Kharif"), ("Wheat", "Rabi")):
        missing = [d["name"] for d in api.district_map(crop, season, 2025)["districts"] if d["shape_id"] not in shapes["shapes"]]
        assert not missing, missing[:5]


def test_map_refusals():
    for args in [("Sugarcane", "Kharif", 2025), ("Wheat", "Kharif", 2025), ("Wheat", "Rabi", 2024)]:
        try:
            api.district_map(*args)
        except HTTPException as e:
            assert e.status_code == 422
        else:
            raise AssertionError("expected a refusal for %r" % (args,))


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        fn()
        print("  ok  %s" % name)
    print("all %d district checks passed" % len(tests))

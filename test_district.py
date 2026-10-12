"""
Guards the district outlook service:  python test_district.py   (needs `python district_forecast.py` run first)

Direct calls, no test-client dependency. What matters here:
  - the expected yield is the mean of the last three PUBLISHED seasons, and a forecast for year Y must not see anything
    published after Y-2 (the publication lag), whatever is in the panel
  - a crop that was not among the tested crops is refused with the reason
  - bad requests are refused with a reason instead of answered
  - the range, baselines and trust flag come back with every outlook, and the map agrees with the outlook page
"""

import logging

import numpy as np
from fastapi import HTTPException

import api
import district_forecast as D

F = api.get_district()
OPT = F.options()
STATES, PAIRS = OPT["states"], OPT["crop_seasons"]
CARD = F.card
OTHER = max((p for p in PAIRS if p["crop"] not in ("Rice", "Maize", "Wheat")), key=lambda p: p["districts"], default=None)   # the best-covered non-staple


def series_of(crop, season):
    """Some district that has this crop and season on offer, largest state first."""
    for st in sorted(STATES, key=lambda s: -len(STATES[s])):
        for dc, info in STATES[st].items():
            if {"crop": crop, "season": season} in info["series"]:
                return st, dc
    raise AssertionError("no district offers %s %s" % (crop, season))


def refused(fn, *args):
    try:
        fn(*args)
    except HTTPException as e:
        assert e.status_code == 422 and e.detail, (args, e.status_code)
        return e.detail
    raise AssertionError("expected a refusal for %r" % (args,))


WHEAT = ("Wheat", "Rabi")


def test_options_offer_only_tested_crops():
    assert len(STATES) > 20 and len(PAIRS) >= 3
    assert {p["crop"] for p in PAIRS} <= set(CARD["crops"]) and OTHER is not None
    assert {p["crop"] for p in PAIRS[:3]} <= {"Rice", "Maize", "Wheat"}, "the staples lead the list"


def test_expected_yield_is_the_mean_of_published_seasons():
    for crop, season in [WHEAT, (OTHER["crop"], OTHER["season"])]:
        _, dc = series_of(crop, season)
        out = api.district_forecast(dc, crop, season, 2025)
        y = F.frame[(F.frame.district_code == dc) & (F.frame.crop == crop) & (F.frame.season == season)].set_index("year")["yield"]
        published = [y[k] for k in (2023, 2022, 2021) if k in y.index]      # a 2025 outlook may use 2023 and earlier only
        assert published and abs(out["forecast"] - round(float(np.mean(published)), 2)) < 0.011, (crop, out["forecast"], published)
        assert out["baselines"]["mean_last_three_published"] == out["forecast"] and out["baselines"]["last_published"]["year"] <= 2023


def test_outlook_contract():
    _, dc = series_of(*WHEAT)
    out = api.district_forecast(dc, *WHEAT, 2025)
    assert out["interval"]["low"] < out["forecast"] < out["interval"]["high"]
    assert set(out["trust"]) >= {"low_trust", "volatility", "seasons_of_history_used"} and out["method"]
    ev = out["evidence"]
    assert ev["mean3"]["n"] > 0 and ev["model"]["dev"]["n"] > 0 and 0.72 <= ev["range_coverage"]["dev"] <= 0.88
    assert all(h["year"] <= D.DATA_END for h in out["history"])


def test_volatile_series_get_wider_ranges():
    """Within a crop, a series flagged volatile gets a wider range than a stable one (the range is calibrated per flag)."""
    for crop, season in [WHEAT, ("Rice", "Kharif"), ("Maize", "Kharif")]:
        seen = {False: [], True: []}
        for st in STATES.values():
            for dc, info in st.items():
                if {"crop": crop, "season": season} not in info["series"]:
                    continue
                try:
                    r = F.forecast(dc, crop, season, 2025)
                except D.ForecastError:                     # a series whose only recent record is 2024 has nothing published for 2025
                    continue
                seen[r["trust"]["low_trust"]].append(r["interval"]["relative_half_width"])
        assert seen[True] and seen[False], (crop, {k: len(v) for k, v in seen.items()})
        assert np.median(seen[True]) > np.median(seen[False]), crop


def test_publication_lag_is_enforced():
    """A 2025 outlook may use seasons up to 2023 only. Poisoning 2024 must not move it (it is not yet published),
    and poisoning 2023 must (control: the check can fail). Run for a staple and for another crop."""
    real = F.panel
    try:
        for crop, season in [WHEAT, (OTHER["crop"], OTHER["season"])]:
            _, dc = series_of(crop, season)
            F.panel = real                                  # the previous crop's last poisoned panel must not leak into this baseline
            clean = F.forecast(dc, crop, season, 2025)["forecast"]
            for year, should_move in ((2024, False), (2023, True)):
                poisoned = real.copy()
                poisoned[poisoned.index.get_level_values("year") == year] = 999.0
                F.panel = poisoned
                moved = F.forecast(dc, crop, season, 2025)["forecast"] != clean
                assert moved == should_move, "%s %s, poisoning %d: moved=%s, expected %s" % (crop, season, year, moved, should_move)
    finally:
        F.panel = real


def test_bad_requests_are_refused():
    _, dc = series_of(*WHEAT)
    for args in [(dc, "Wheat", "Rabi", 2024), (dc, "Wheat", "Rabi", 2030), (dc, "Wheat", "Kharif", 2025), (999999, "Wheat", "Rabi", 2025)]:
        refused(api.district_forecast, *args)


def test_a_crop_outside_the_tested_set_is_refused_with_the_reason():
    _, dc = series_of(*WHEAT)
    for crop in ("Quinoa", "Coconut"):
        assert "No outlook is offered" in refused(api.district_forecast, dc, crop, "Kharif", 2025)
        assert "No outlook is offered" in refused(api.district_map, crop, "Kharif", 2025)


def test_track_record_is_the_mean_of_what_was_published_then():
    _, dc = series_of(*WHEAT)
    t = api.district_track_record(dc, *WHEAT)
    assert t["seasons"] and all(2018 <= r["year"] <= 2024 for r in t["seasons"]) and t["summary"]["n"] == len(t["seasons"])
    y = F.frame[(F.frame.district_code == dc) & (F.frame.crop == "Wheat") & (F.frame.season == "Rabi")].set_index("year")["yield"]
    for r in t["seasons"]:
        earlier = [y[k] for k in (r["year"] - 2, r["year"] - 3, r["year"] - 4) if k in y.index]
        assert abs(r["forecast"] - float(np.mean(earlier))) < 0.011, (r, earlier)


def test_madhya_pradesh_carries_the_source_warning():
    dc = next(iter(STATES["Madhya Pradesh"]))
    s = STATES["Madhya Pradesh"][dc]["series"][0]
    out = api.district_forecast(dc, s["crop"], s["season"], 2025)
    assert any("Madhya Pradesh" in n for n in out["notes"])


def test_map_agrees_with_single_outlooks():
    """The map computes hundreds of outlooks in one batch. Any district on it must match the outlook page exactly."""
    for crop, season in [("Rice", "Kharif"), WHEAT, (OTHER["crop"], OTHER["season"])]:
        m = api.district_map(crop, season, 2025)
        assert len(m["districts"]) > 100, (crop, len(m["districts"]))
        for d in m["districts"][:: max(1, len(m["districts"]) // 12)]:
            one = F.forecast(d["district_code"], crop, season, 2025)
            assert one["forecast"] == d["forecast"], (crop, d["name"], one["forecast"], d["forecast"])
            assert one["interval"]["low"] == d["low"] and one["interval"]["high"] == d["high"]
            assert one["trust"]["low_trust"] == d["low_trust"]
            assert one["baselines"]["last_published"]["value"] == d["last_published"]


def test_map_shapes_cover_every_outlined_district():
    shapes = api.district_shapes()
    west, south, east, north = shapes["bounds"]
    assert 66 < west < 70 and 6 < south < 8 and 96 < east < 98 and 35 < north < 37
    for crop, season in (("Rice", "Kharif"), WHEAT):
        missing = [d["name"] for d in api.district_map(crop, season, 2025)["districts"]
                   if d["shape_id"] is not None and d["shape_id"] not in shapes["shapes"]]
        assert not missing, missing[:5]


def test_map_refusals():
    for args in [("Quinoa", "Kharif", 2025), ("Wheat", "Rabi", 2024), ("Wheat", "Rabi", 2030)]:
        refused(api.district_map, *args)


if __name__ == "__main__":
    logging.disable(logging.CRITICAL)
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        fn()
        print("  ok  %s" % name)
    print("all %d district checks passed" % len(tests))

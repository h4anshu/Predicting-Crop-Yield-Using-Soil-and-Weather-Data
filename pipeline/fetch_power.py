"""
Phase 1A: daily humidity and solar radiation per district, from NASA POWER.

    python pipeline/fetch_power.py [first_year] [last_year]      (default 1997 2024)

IMD supplies rain and temperature but not humidity or radiation, which the old state-level
features used. POWER's native grid is 0.5 deg x 0.625 deg (MERRA-2), so districts that fall in
the same cell get identical numbers: requests are made once per cell, at the cell centre, and the
district -> cell mapping is rebuilt from district_geo.parquet when the data is aggregated.

Reads  data/processed/district_geo.parquet
Writes data/raw/power/<lat>_<lon>.json.gz   {"lat","lon","dates":[...],"RH2M":[...],"ALLSKY_SFC_SW_DWN":[...]}

Sequential, with a pause between calls and a User-Agent naming this project: POWER publishes no fixed
rate limit and says it monitors usage. Resumable (a cell with a file is skipped). -999 is POWER's
missing-value marker and is stored as null.
"""

import gzip
import json
import os
import sys
import time

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEO = os.path.join(ROOT, "data", "processed", "district_geo.parquet")
OUT = os.path.join(ROOT, "data", "raw", "power")
URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMS = "RH2M,ALLSKY_SFC_SW_DWN"
HEADERS = {"User-Agent": "crop-yield-research (district yield forecasting; contact via repo owner)"}


def cell(lat, lon):
    """Centre of the MERRA-2 cell containing the point."""
    return round(round(lat / 0.5) * 0.5, 3), round(round((lon + 180) / 0.625) * 0.625 - 180, 3)


def cells():
    g = pd.read_parquet(GEO)
    g = g[g.shape_id.notna()]
    return sorted({cell(a, o) for a, o in zip(g.lat.astype(float), g.lon.astype(float))})


def path(lat, lon):
    return os.path.join(OUT, "%s_%s.json.gz" % (lat, lon))


def fetch(lat, lon, first, last):
    p = path(lat, lon)
    if os.path.exists(p):
        return "have"
    for attempt in range(1, 4):
        try:
            r = requests.get(URL, headers=HEADERS, timeout=(30, 180), params={
                "parameters": PARAMS, "community": "AG", "latitude": lat, "longitude": lon,
                "start": "%d0101" % first, "end": "%d1231" % last, "format": "JSON"})
            if r.status_code == 200:
                par = r.json()["properties"]["parameter"]
                dates = sorted(par["RH2M"])
                rec = {"lat": lat, "lon": lon, "dates": dates}
                for k in PARAMS.split(","):
                    rec[k] = [None if par[k][d] == -999 else par[k][d] for d in dates]
                os.makedirs(OUT, exist_ok=True)
                with gzip.open(p + ".part", "wt", encoding="utf-8") as f:
                    json.dump(rec, f)
                os.replace(p + ".part", p)
                return "ok"
            print("  (%s, %s) attempt %d: HTTP %d %s" % (lat, lon, attempt, r.status_code, r.text[:100].replace("\n", " ")), flush=True)
        except (requests.RequestException, KeyError, ValueError) as e:
            print("  (%s, %s) attempt %d: %s" % (lat, lon, attempt, repr(e)[:120]), flush=True)
        time.sleep(10 * attempt)
    return "FAILED"


if __name__ == "__main__":
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 1997
    last = int(sys.argv[2]) if len(sys.argv) > 2 else 2024
    todo = cells()
    print("%d cells to cover" % len(todo), flush=True)
    done = 0
    for i, (lat, lon) in enumerate(todo, 1):
        t = time.time()
        s = fetch(lat, lon, first, last)
        done += s in ("ok", "have")
        if s != "have":
            print("%d/%d (%s, %s): %s (%.0fs)" % (i, len(todo), lat, lon, s, time.time() - t), flush=True)
        if s == "ok":
            time.sleep(1.0)
    print("done: %d/%d cells" % (done, len(todo)), flush=True)

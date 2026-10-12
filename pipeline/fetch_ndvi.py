"""
Phase 1A: district NDVI / EVI from MODIS via Google Earth Engine.

    EE_KEY_PATH=D:/secrets/<key>.json python pipeline/fetch_ndvi.py [first_year] [last_year]   (default 2005 2024)

Reads  data/processed/district_geo.parquet, data/raw/boundaries/*ADM2*.geojson
Writes data/raw/ndvi/ndvi_<year>.parquet   shape_id, date, ndvi, evi, n_pix   (one row per district per 16-day composite)

MODIS/061/MOD13A2 (1 km, 16-day). For every district the mean is taken over CROPLAND pixels only (MCD12Q1 2018,
IGBP classes 12 and 14), so forest, scrub and towns do not dilute the signal, and only pixels with
SummaryQA <= 1 (good or marginal). NDVI and EVI are scaled by 0.0001. A district with no cropland pixel in
a composite gets null, not zero.

Credentials: a service-account JSON key, read from the path in the EE_KEY_PATH environment variable. The key
lives outside the repository and is never printed or committed. The account email and project are not secret.
Polygons are simplified to 0.002 degrees (~220 m, below the pixel size) so a request stays small; they go in
chunks of CHUNK districts, and one call maps over a year's composites server-side. Resumable per year. Stops cleanly, without burning retries, when the project's daily EE quota is used up.
"""

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import ee
import pandas as pd
from shapely.geometry import mapping, shape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "raw", "ndvi")
EMAIL = "geo-service@plant-disease-503711.iam.gserviceaccount.com"
PROJECT = "plant-disease-503711"
CHUNK, WORKERS, SIMPLIFY = 60, 1, 0.002
COLLECTION = "MODIS/061/MOD13A2"   # 1 km, 16-day: 16x fewer pixels than MOD13Q1 (250 m); a district is ~1,000+ km2, so a 1 km mean is adequate
SCALE = 1000


class QuotaExhausted(RuntimeError):
    pass


def init():
    ee.Initialize(ee.ServiceAccountCredentials(EMAIL, os.environ["EE_KEY_PATH"]), project=PROJECT)


def polygons():
    geo = pd.read_parquet(os.path.join(ROOT, "data", "processed", "district_geo.parquet"))
    want = set(geo.shape_id.dropna())
    gj = json.load(open(os.path.join(ROOT, "data", "raw", "boundaries", "geoBoundaries-IND-ADM2_simplified.geojson"), encoding="utf-8"))
    out = []
    for f in gj["features"]:
        sid = f["properties"]["shapeID"]
        if sid in want:
            g = shape(f["geometry"]).simplify(SIMPLIFY, preserve_topology=True)
            out.append((sid, mapping(g)))
    return out


def chunk_task(year, chunk):
    fc = ee.FeatureCollection([ee.Feature(ee.Geometry(g, None, False), {"shape_id": s}) for s, g in chunk])
    crop = ee.ImageCollection("MODIS/061/MCD12Q1").filterDate("2018-01-01", "2019-01-01").first().select("LC_Type1")
    crop = crop.eq(12).Or(crop.eq(14))
    col = (ee.ImageCollection(COLLECTION).filterDate("%d-01-01" % year, "%d-01-01" % (year + 1))
           .filter(ee.Filter.calendarRange(5, 5, "month").Not()))   # May is in no season window
    red = ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True)

    def per_image(img):
        ok = img.select("SummaryQA").lte(1).And(crop)
        v = img.select(["NDVI", "EVI"]).multiply(0.0001).updateMask(ok)
        date = img.date().format("YYYY-MM-dd")
        return v.reduceRegions(collection=fc, reducer=red, scale=SCALE, tileScale=4).map(lambda f: f.set("date", date))

    feats = col.map(per_image).flatten().getInfo()["features"]
    return [(f["properties"]["shape_id"], f["properties"]["date"], f["properties"].get("NDVI_mean"),
             f["properties"].get("EVI_mean"), f["properties"].get("NDVI_count")) for f in feats]


def run_with_retry(year, chunk):
    for attempt in range(1, 5):
        try:
            return chunk_task(year, chunk)
        except Exception as e:  # EE raises many types: quota, timeout, transient
            if "exceeded the custom quota" in str(e) or "quota" in str(e).lower() and "exceeded" in str(e).lower():
                raise QuotaExhausted(str(e)[:200])
            print("  %d chunk attempt %d: %s" % (year, attempt, str(e)[:120].replace("\n", " ")), flush=True)
            time.sleep(15 * attempt)
    raise RuntimeError("chunk failed for %d" % year)


def fetch_year(year, polys):
    path = os.path.join(OUT, "ndvi_%d.parquet" % year)
    if os.path.exists(path):
        return "have"
    chunks = [polys[i:i + CHUNK] for i in range(0, len(polys), CHUNK)]
    with ThreadPoolExecutor(WORKERS) as ex:
        parts = list(ex.map(lambda c: run_with_retry(year, c), chunks))
    df = pd.DataFrame([r for p in parts for r in p], columns=["shape_id", "date", "ndvi", "evi", "n_pix"])
    os.makedirs(OUT, exist_ok=True)
    df.to_parquet(path, index=False)
    return "ok (%d rows, %.0f%% with NDVI)" % (len(df), 100 * df.ndvi.notna().mean())


if __name__ == "__main__":
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 2005
    last = int(sys.argv[2]) if len(sys.argv) > 2 else 2024
    init()
    polys = polygons()
    print("%d district polygons" % len(polys), flush=True)
    try:
        for y in range(first, last + 1):
            t = time.time()
            print("%d: %s (%.0fs)" % (y, fetch_year(y, polys), time.time() - t), flush=True)
    except QuotaExhausted as e:
        print("STOPPED: Earth Engine daily quota used up (%s). Years already written are kept; rerun later to resume." % e, flush=True)
        sys.exit(2)
    print("done", flush=True)

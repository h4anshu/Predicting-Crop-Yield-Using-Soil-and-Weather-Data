"""
Phase 4: district outlines small enough to draw in a browser.

    python pipeline/build_map_shapes.py

Reads  data/raw/boundaries/geoBoundaries-IND-ADM2_simplified.geojson (8 MB), data/processed/district_geo.parquet
Writes data/processed/district_shapes.json    {"bounds": [west, south, east, north], "shapes": {shape_id: [ring, ...]}}

Only the polygons some district in the yield panel is matched to are kept. Each ring is a list of [lon, lat] with 2
decimals (about 1 km). Outlines are simplified to 0.02 degrees (about 2 km), which is fine for a national map and
not for measuring areas. Holes are dropped and parts smaller than MIN_AREA square degrees (specks, tiny islands) are
dropped, so the picture is a map and not a boundary dataset.
"""

import json
import os

import pandas as pd
from shapely.geometry import shape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "raw", "boundaries", "geoBoundaries-IND-ADM2_simplified.geojson")
GEO = os.path.join(ROOT, "data", "processed", "district_geo.parquet")
OUT = os.path.join(ROOT, "data", "processed", "district_shapes.json")
TOLERANCE, MIN_AREA = 0.02, 0.0004


def main():
    want = set(pd.read_parquet(GEO).shape_id.dropna())
    shapes = {}
    for f in json.load(open(SRC, encoding="utf-8"))["features"]:
        sid = f["properties"]["shapeID"]
        if sid not in want:
            continue
        g = shape(f["geometry"]).simplify(TOLERANCE, preserve_topology=True)
        parts = list(g.geoms) if g.geom_type == "MultiPolygon" else [g]
        rings = [[[round(x, 2), round(y, 2)] for x, y in p.exterior.coords] for p in parts if p.area >= MIN_AREA]
        if not rings:                                   # a district made only of specks: keep its biggest part
            big = max(parts, key=lambda p: p.area)
            rings = [[[round(x, 2), round(y, 2)] for x, y in big.exterior.coords]]
        shapes[sid] = rings
    xs = [x for rs in shapes.values() for r in rs for x, _ in r]
    ys = [y for rs in shapes.values() for r in rs for _, y in r]
    out = {"bounds": [min(xs), min(ys), max(xs), max(ys)], "shapes": shapes}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"))
    pts = sum(len(r) for rs in shapes.values() for r in rs)
    print("%d shapes | %d points | bounds %s | %.2f MB" % (len(shapes), pts, out["bounds"], os.path.getsize(OUT) / 1e6))


if __name__ == "__main__":
    main()

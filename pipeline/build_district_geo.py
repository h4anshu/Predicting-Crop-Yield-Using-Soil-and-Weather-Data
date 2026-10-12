"""
Phase 1A: tie every district in the yield panel to a boundary polygon, so weather and soil can be
sampled by district.

    python pipeline/build_district_geo.py        (needs shapely, requirements-data.txt)

Reads  data/processed/district_yield.parquet
       data/raw/boundaries/geoBoundaries-IND-ADM{1,2}_simplified.geojson   (geoBoundaries, ODbL, 2021 boundaries)
Writes data/processed/district_geo.parquet   one row per yield-panel district:
       district_code, state_name, district_name, shape_id (or NaN), lon, lat, match_type, score

geoBoundaries carries a district NAME but no state and no LGD code, and 7 names occur in more than
one state (Bilaspur, Aurangabad, ...). So the state of each polygon is found by locating its
representative point in the ADM1 polygons, and a district is matched on (state, name):

  exact    normalised names are equal inside the state
  fuzzy    best difflib ratio >= 0.80 inside the state, and clearly ahead of the runner-up
  none     no polygon: districts created after the 2021 boundaries (e.g. 2022-23 splits), or spelling
           too far apart. They are listed, never guessed. Downstream, such a district has no weather
           and is dropped from the weather-based model rather than given a neighbour's climate.
"""

import difflib
import json
import os
import re
import unicodedata

import pandas as pd
from shapely.geometry import shape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
B = os.path.join(ROOT, "data", "raw", "boundaries")
YIELD = os.path.join(ROOT, "data", "processed", "district_yield.parquet")
OUT = os.path.join(ROOT, "data", "processed", "district_geo.parquet")

# panel state -> how geoBoundaries ADM1 spells it, after norm()
STATE_ALIASES = {"jammuandkashmir": "jammukashmir", "andamanandnicobarislands": "andamannicobar",
                 "dadraandnagarhaveli": "dadranagarhavelidamandiu", "damananddiu": "dadranagarhavelidamandiu",
                 "dadraandnagarhavelianddamananddiu": "dadranagarhavelidamandiu",
                 "nctofdelhi": "delhi", "orissa": "odisha", "uttaranchal": "uttarakhand"}


# Districts the panel spells with their CURRENT name and geoBoundaries (2021) with the old one. Each pair is
# the same district; every polygon named here was also left unclaimed by the exact/fuzzy pass in the state.
# Sikkim's four old districts were redrawn into six in 2021, so two panel districts share a polygon there:
# at weather resolution (0.25 deg) that is a close approximation, and the match_type says "alias".
ALIASES = """
Assam|Kamrup Metro|Kamrup Metropolitan
Assam|Karbi Anglong|Karbi Anglong East
Assam|West Karbi Anglong|Karbi Anglong West
Assam|Sribhumi|Karimganj
Chhattisgarh|Balodabazar-Bhatapara|Baloda Bazar
Chhattisgarh|Balrampur-Ramanujganj|Balrampur
Chhattisgarh|Korea|Koriya
Gujarat|Botad|Batod
Gujarat|Dahod|Dohad
Gujarat|Dangs|The Dangs
Haryana|Gurugram|Gurgaon
Haryana|Nuh|Mewat
Jammu And Kashmir|Poonch|Punch
Jharkhand|East Singhbum|Purbi Singhbhum
Jharkhand|West Singhbhum|Pashchimi Singhbhum
Karnataka|Ballari|Bellary
Karnataka|Belagavi|Belgaum
Karnataka|Bengaluru Rural|Bangalore Rural
Karnataka|Bengaluru Urban|Bangalore
Karnataka|Kalaburagi|Gulbarga
Karnataka|Mysuru|Mysore
Karnataka|Vijayapura|Bijapur
Ladakh|Leh Ladakh|Leh(Ladakh)
Madhya Pradesh|Agar-Malwa|Agar
Madhya Pradesh|Narmadapuram|Hoshangabad
Maharashtra|Ahilyanagar|Ahmadnagar
Maharashtra|Beed|Bid
Maharashtra|Chhatrapati Sambhajinagar|Aurangabad
Maharashtra|Dharashiv|Osmanabad
Maharashtra|Raigad|Raigarh
Odisha|Anugola|Anugul
Odisha|Baragada|Bargarh
Odisha|Debagada|Debagarh
Odisha|Kataka|Cuttack
Odisha|Nayagada|Nayagarh
Odisha|Sundaragada|Sundargarh
Punjab|Sri Muktsar Sahib|Muktsar
Punjab|S.A.S Nagar|Sahibzada Ajit Singh Nagar
Sikkim|Gangtok|East District
Sikkim|Pakyong|East District
Sikkim|Mangan|North District
Sikkim|Namchi|South District
Sikkim|Gyalshing|West District
Sikkim|Soreng|West District
Telangana|Bhadradri Kothagudem|Bhadradri
Telangana|Jayashankar Bhupalapally|Jayashankar
Telangana|Jogulamba Gadwal|Jogulamba
Telangana|Kumuram Bheem Asifabad|Komaram Bheem
Telangana|Medchal Malkajgiri|Medchal
Telangana|Warangal|Warangal (R)
Telangana|Hanumakonda|Warangal (U)
Uttar Pradesh|Amroha|Jyotiba Phule Nagar
Uttar Pradesh|Ayodhya|Faizabad
Uttar Pradesh|Bhadohi|Sant Ravidas Nagar (Bhadohi)
Uttar Pradesh|Hathras|Mahamaya Nagar
Uttar Pradesh|Kasganj|Kanshiram Nagar
Uttar Pradesh|Prayagraj|Allahabad
Uttarakhand|Pauri Garhwal|Garhwal
West Bengal|Cooch Behar|Koch Bihar
West Bengal|Hooghly|Hugli
West Bengal|Howrah|Haora
West Bengal|North 24 Parganas|North Twenty Four Parganas
West Bengal|South 24 Parganas|South Twenty Four Parganas
West Bengal|Purba Bardhaman|Barddhaman
"""


def norm(s):
    # geoBoundaries spells names with diacritics (Bihār, Gujarāt): fold them to plain letters first,
    # otherwise stripping non-letters deletes the accented one and the names no longer match.
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    s = re.sub(r"\(.*?\)", "", s.lower()).replace("&", "and")
    return re.sub(r"[^a-z]", "", s)


def state_key(s):
    k = norm(s)
    return STATE_ALIASES.get(k, k)


def load_polys(path):
    return [(f["properties"]["shapeName"], f["properties"]["shapeID"], shape(f["geometry"]))
            for f in json.load(open(path, encoding="utf-8"))["features"]]


def build():
    states = load_polys(os.path.join(B, "geoBoundaries-IND-ADM1_simplified.geojson"))
    polys = []
    for name, sid, geom in load_polys(os.path.join(B, "geoBoundaries-IND-ADM2_simplified.geojson")):
        pt = geom.representative_point()
        st = next((state_key(sn) for sn, _, sg in states if sg.contains(pt)), None)
        c = geom.centroid
        polys.append({"name": name, "shape_id": sid, "state": st, "lon": c.x, "lat": c.y})
    geo = pd.DataFrame(polys)
    print("polygons %d | with a state %d | state keys: %d" % (len(geo), geo.state.notna().sum(), geo.state.nunique()))

    y = pd.read_parquet(YIELD)
    d = (y.sort_values("year").groupby("district_code")
         [["state_name", "district_name"]].last().reset_index())
    d["skey"] = d.state_name.map(state_key)
    d["nkey"] = d.district_name.map(norm)
    missing_states = sorted(set(d.skey) - set(geo.state.dropna()))
    if missing_states:
        print("panel states with no polygon state match:", missing_states)

    alias = {(state_key(s), norm(p)): norm(g) for s, p, g in
             (ln.split("|") for ln in ALIASES.strip().splitlines())}
    rows, used = [], set()
    for r in d.itertuples():
        cand = geo[(geo.state == r.skey)]
        hit = cand[cand.name.map(norm) == r.nkey]
        mtype, score = "none", 0.0
        if len(hit) == 1:
            mtype, score = "exact", 1.0
        elif (r.skey, r.nkey) in alias:
            hit = cand[cand.name.map(norm) == alias[(r.skey, r.nkey)]]
            if len(hit) == 1:
                mtype, score = "alias", 1.0
        if mtype == "none" and len(cand):
            sc = sorted(((difflib.SequenceMatcher(None, r.nkey, norm(n)).ratio(), i)
                         for i, n in zip(cand.index, cand.name)), reverse=True)
            if sc and sc[0][0] >= 0.80 and (len(sc) == 1 or sc[0][0] - sc[1][0] >= 0.05):
                hit, mtype, score = cand.loc[[sc[0][1]]], "fuzzy", sc[0][0]
        row = {"district_code": r.district_code, "state_name": r.state_name, "district_name": r.district_name,
               "match_type": mtype, "score": round(score, 3), "shape_id": None, "lon": None, "lat": None,
               "geo_name": None}
        if mtype != "none":
            h = hit.iloc[0]
            row.update(shape_id=h.shape_id, lon=h.lon, lat=h.lat, geo_name=h["name"])
            used.add(h.shape_id)
        rows.append(row)
    out = pd.DataFrame(rows)
    # a polygon claimed by two districts through the automatic passes is ambiguous: keep the better
    # score, drop the other. (Alias pairs that share a polygon are deliberate and exempt.)
    auto = out[out.match_type.isin(["exact", "fuzzy"])]
    dup = auto.duplicated("shape_id", keep=False)
    if dup.any():
        worst = auto[dup].sort_values("score").groupby("shape_id").head(1).index
        out.loc[worst, ["match_type", "shape_id", "lon", "lat", "geo_name"]] = ["none", None, None, None, None]
    return out, y


def report(out, y):
    print("\nmatch types:", out.match_type.value_counts().to_dict())
    fz = out[out.match_type == "fuzzy"].sort_values("score")
    print("\nfuzzy matches, lowest score first (check these):")
    print(fz.head(25)[["state_name", "district_name", "geo_name", "score"]].to_string(index=False))
    # how many yield rows / recent rows lose weather because their district has no polygon
    rows = y.merge(out[["district_code", "match_type"]], on="district_code")
    stap = rows[rows.crop.isin(["Rice", "Wheat", "Maize"]) & rows.valid_yield]
    print("\nstaple rows with a polygon: %.1f%% overall | by year:" % (100 * (stap.match_type != "none").mean()))
    print((stap.groupby("year").apply(lambda g: round(100 * (g.match_type != "none").mean(), 1),
                                      include_groups=False)).loc[[2000, 2010, 2018, 2020, 2022, 2023, 2024]].to_dict())
    un = out[out.match_type == "none"]
    print("\nunmatched districts (%d), by state:" % len(un), un.state_name.value_counts().head(12).to_dict())
    print(un.sample(min(15, len(un)), random_state=0)[["state_name", "district_name"]].to_string(index=False))


if __name__ == "__main__":
    geo, yld = build()
    geo.to_parquet(OUT, index=False)
    report(geo, yld)
    print("\nwrote %s" % OUT)

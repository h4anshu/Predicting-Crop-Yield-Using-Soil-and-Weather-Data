"""
Phase 1A: season NDVI/EVI features per district, at several lead times.

    python pipeline/build_ndvi_features.py

Reads  data/raw/ndvi/ndvi_<year>.parquet            (pipeline/fetch_ndvi.py)
Writes data/processed/season_ndvi.parquet           shape_id, year, window, lead, n_comp, ndvi_max, ndvi_mean,
                                                    ndvi_int, evi_max, evi_mean

Windows (year = START year of the agricultural year, as in the yield panel):
    Kharif   Jun 1 - Oct 31 of `year`
    Rabi     Nov 1 of `year` - Apr 15 of `year + 1`   (reaches wheat's grain-filling)
`lead` is how many days after the window opens the composites are allowed to run: 60, 90, 120, or 999 (the whole
window). A lead-60 row uses only what a satellite had seen two months into the season, which is what a forecast
issued then could actually know; the full-window row is the hindsight ceiling. ndvi_int = mean NDVI x number of
composites in the window (a greenness integral that does not depend on how many composites were cloud-free).
"""

import glob
import os
import warnings

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw", "ndvi")
OUT = os.path.join(ROOT, "data", "processed", "season_ndvi.parquet")
WINDOWS = {"Kharif": ((6, 1), (10, 31), 0), "Rabi": ((11, 1), (4, 15), 1)}
LEADS = (60, 90, 120, 999)


def load():
    d = pd.concat([pd.read_parquet(p) for p in sorted(glob.glob(os.path.join(RAW, "ndvi_*.parquet")))], ignore_index=True)
    d["date"] = pd.to_datetime(d["date"])
    return d


def build(d):
    ids = sorted(d.shape_id.unique())
    dates = pd.DatetimeIndex(sorted(d.date.unique()))
    nd = d.pivot(index="shape_id", columns="date", values="ndvi").reindex(index=ids, columns=dates).to_numpy()
    ev = d.pivot(index="shape_id", columns="date", values="evi").reindex(index=ids, columns=dates).to_numpy()
    rows = []
    for y in range(dates[0].year, dates[-1].year + 1):
        for name, ((m0, d0), (m1, d1), carry) in WINDOWS.items():
            s, e = pd.Timestamp(y, m0, d0), pd.Timestamp(y + carry, m1, d1)
            for lead in LEADS:
                cut = min(e, s + pd.Timedelta(days=lead)) if lead != 999 else e
                if cut > dates[-1]:
                    continue    # a lead is usable as soon as ITS cutoff is covered, not only when the whole window is
                sel = (dates >= s) & (dates <= cut)
                if sel.sum() == 0:
                    continue
                a, b = nd[:, sel], ev[:, sel]
                rows.append(pd.DataFrame({
                    "shape_id": ids, "year": y, "window": name, "lead": lead, "n_comp": int(sel.sum()),
                    "ndvi_max": np.nanmax(a, axis=1), "ndvi_mean": np.nanmean(a, axis=1),
                    "ndvi_int": np.nanmean(a, axis=1) * int(sel.sum()),
                    "evi_max": np.nanmax(b, axis=1), "evi_mean": np.nanmean(b, axis=1)}))
    return pd.concat(rows, ignore_index=True)


if __name__ == "__main__":
    warnings.filterwarnings("ignore", category=RuntimeWarning)
    d = load()
    print("composite rows %d | districts %d | years %d-%d" % (len(d), d.shape_id.nunique(), d.date.dt.year.min(), d.date.dt.year.max()))
    out = build(d)
    out.to_parquet(OUT, index=False)
    print("season_ndvi rows %d" % len(out))
    print(out.groupby(["window", "lead"]).agg(n_comp=("n_comp", "first"), ndvi_max=("ndvi_max", "mean"),
                                               present=("ndvi_max", lambda s: round(float(s.notna().mean()), 3))).round(3).to_string())

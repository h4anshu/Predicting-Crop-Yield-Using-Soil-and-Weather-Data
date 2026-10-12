"""
Phase 1A: download the IMD gridded archive (rain 0.25 deg, tmax/tmin 1 deg), one file per year.

    python pipeline/fetch_imd.py [first_year] [last_year]      (default 1997 2024)

Source: imdpune.gov.in (same endpoints imdlib uses; file layout compatible with imdlib.open_data).
Writes data/raw/imd/{rain,tmax,tmin}/<year>.{grd,GRD}.

Sequential on purpose: the server is slow (about 2 minutes per rainfall year) and this is a shared
public service. Resumable: a file whose size is exactly right is skipped, so a rerun only fetches
what is missing. A year the archive does not have yet (the newest ones) is logged and skipped.

Expected size is grid cells x days x 4 bytes (float32): rain 135 x 129, temperature 31 x 31.
A wrong size means a truncated download or an error page, and the file is discarded.
"""

import calendar
import os
import sys
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "raw", "imd")
VARS = {  # name: (url, form field, cells, extension)
    "tmax": ("https://imdpune.gov.in/cmpg/Griddata/maxtemp.php", "maxtemp", 31 * 31, "GRD"),
    "tmin": ("https://imdpune.gov.in/cmpg/Griddata/mintemp.php", "mintemp", 31 * 31, "GRD"),
    "rain": ("https://imdpune.gov.in/cmpg/Griddata/rainfall.php", "rain", 135 * 129, "grd"),
}


def expected_size(cells, year):
    return cells * (366 if calendar.isleap(year) else 365) * 4


def fetch(var, year):
    url, field, cells, ext = VARS[var]
    path = os.path.join(OUT, var, "%d.%s" % (year, ext))
    want = expected_size(cells, year)
    if os.path.exists(path) and os.path.getsize(path) == want:
        return "have"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for attempt in range(1, 4):
        try:
            r = requests.post(url, data={field: year}, timeout=(60, 300), stream=True)
            tmp = path + ".part"
            n = 0
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
                    n += len(chunk)
            if r.status_code == 200 and n == want:
                os.replace(tmp, path)
                return "ok"
            os.remove(tmp)
            if r.status_code == 200 and n < 100_000:
                return "unavailable (%d bytes)" % n          # an error page, not a grid
            print("  %s %d attempt %d: status %s, %d bytes, wanted %d" % (var, year, attempt, r.status_code, n, want), flush=True)
        except requests.RequestException as e:
            print("  %s %d attempt %d: %s" % (var, year, attempt, repr(e)[:120]), flush=True)
        time.sleep(15 * attempt)
    return "FAILED"


if __name__ == "__main__":
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 1997
    last = int(sys.argv[2]) if len(sys.argv) > 2 else 2024
    for var in ("tmax", "tmin", "rain"):
        for year in range(first, last + 1):
            t = time.time()
            status = fetch(var, year)
            print("%s %d: %s (%.0fs)" % (var, year, status, time.time() - t), flush=True)
    print("done", flush=True)

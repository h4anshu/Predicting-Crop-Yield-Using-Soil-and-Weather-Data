# Data card — district yield panel (Phase 1A, step 1)

Retrieved 2026-10-11. Rebuild: `python pipeline/build_district_yield.py` (needs `requirements-data.txt`).
Raw files live in `data/raw/` and the output in `data/processed/`; both are gitignored.

## Sources

| File (`data/raw/`) | Source | Years | Size | Licence |
|---|---|---|---|---|
| `des_apy_1997_2023.csv` | DES crop-wise Area, Production, Yield, via [India Data Portal](https://ckandev.indiadataportal.com/dataset/area-production-yield-apy) (original: `data.desagri.gov.in`) | 1997-98 → 2022-23 | 56.2 MB | ODC-BY |
| `upag_2013_2025.csv` | DES district-wise data via UPAG (`upag.gov.in`), same portal, 31 field crops | 2013-14 → 2024-25 | 14.2 MB | ODC-BY |
| `icrisat_apportioned_apy.txt` | ICRISAT-TCI District Level Database, apportioned (`data.icrisat.org/dldAPI/apportioned/area-production-yield`) | 1966 → 2017 | 12.0 MB | not stated on the site |

Attribution is required under ODC-BY. The official DES portals could not be opened from the
research environment, so the mirror was used; its source data is DES's.

## What the panel contains

441,075 rows · 752 districts · 117 crops · 1997–2024 · one row per district × crop × season × year.
`year` is the **start** year of the agricultural year (1997-98 → 1997), matching the existing
state-level dataset. Area is hectares, production tonnes, `yield` tonnes/ha.

Staple coverage (districts with a valid, unflagged yield) is 400–700 per crop per year for every
year 2000–2024, with no gap at 2020–2021.

| Year | Rice | Wheat | Maize |
|---|---|---|---|
| 2000 | 523 | 451 | 472 |
| 2010 | 562 | 509 | 535 |
| 2020 | 667 | 535 | 633 |
| 2022 | 675 | 553 | 655 |
| 2023 | 695 | 534 | 693 |
| 2024 | 626 | 482 | 618 |

## Rules applied

1. **`Total` season dropped** from APY: it is the sum of the others and double-counts.
2. **Autumn and Winter folded into Kharif** and summed, as UPAG reports them (area then agrees within 1% on 97.5% of rows).
3. **Source precedence:** a (year, district, crop) that APY has under any season is taken from APY only; UPAG fills where APY has nothing (all of 2023–24, plus ~12,000 rows 2013–2022, mostly "Other Pulses", Jute & Mesta). Joining on season too would double-count crops the sources file under different seasons.
4. **Crop names:** nine UPAG names mapped to APY's (Tur → Arhar/Tur, Lentil → Masoor, …). Cotton is **not** mapped to Cotton(Lint) because the bale-to-tonne basis of APY is unconfirmed.
5. **Yield recomputed** as production ÷ area where both are positive, else NaN (a reported 0 is a missing report). The reported yield agreed within 1% on 99.8% (APY) and 99.8% (UPAG) of rows.
6. **Outliers flagged, not removed:** `flag_outlier` = yield > 3 × the crop's 99th percentile (219 rows; APY has a maize row at 1,494 t/ha).

## Checks performed

- APY and UPAG agree to <0.1% on 98.8% of 22,607 overlapping staple rows; the disagreements are concentrated in Mizoram.
- One district code maps to one name and one state; no duplicate keys in the output (asserted in the build script).
- Area-weighted all-India yields track known national figures: rice 1.9 → 3.0, wheat 2.7 → 3.6, maize 1.8 → 3.5 t/ha (2000 → 2024).

## Known issues

- **District sums overshoot official national production by about 15–20%** (wheat 2020: 131 Mt vs ~110 Mt published). Punjab (17.2 Mt), Haryana (11.4) and Bihar (6.6) look right; most of the excess sits in Madhya Pradesh, where the panel has 9.8 Mha of wheat. This was not verified against an independent MP figure. Yield is a ratio, so it is less affected, but **do not use these tables for absolute production totals** until reconciled with state-level statistics.
- **2024-25 is partial** in UPAG (670 districts, 29 states, versus 738 in 2023-24). Treat 2024 as incomplete, and do not use it as a clean test year.
- **Season labels drift at the handoff.** 94.3% of staple series present in 2022 continue under the same season label in 2023; the rest (mostly crops APY files as "Whole Year" and UPAG as Kharif) lose their history there.
- **Maize:** 320 district-years carry "Whole Year" alongside seasonal rows, a possible double count. Model each (district, crop, season) series separately rather than summing seasons.
- **Districts split over time** (512 in 1997-98, 736 in 2022-23). A new district has a short series and its parent's history stops mid-way. Yield is intensive so this matters less than for area, but short series have less history to forecast from.
- 54 UPAG rows have no district code and are dropped.

## Added 2026-10-11: boundaries, weather, soil, static attributes

| Raw (`data/raw/`) | Source | Size | Licence / terms | Script |
|---|---|---|---|---|
| `boundaries/` | geoBoundaries India ADM2 (736 districts, LGD-based, 2021) and ADM1, simplified | 8.0 + 5.1 MB | ODbL 1.0 | `build_district_geo.py` |
| `imd/{rain,tmax,tmin}/` | IMD gridded archive, `imdpune.gov.in` (rain 0.25°, temp 1°), 1997–2024 | ~0.7 GB (rain 25.4 MB/yr, temp 1.4 MB/yr) | none stated on the IMD page or imdlib docs | `fetch_imd.py` |
| `power/` | NASA POWER daily humidity + radiation, one call per 0.5°×0.625° cell, 1997–2024 | 569 cells | free, no fixed rate limit published | `fetch_power.py` |
| `soil/soil_nutrient_analysis.csv` | Soil Health Card via India Data Portal, 2023–25, village level | 1.1 GB | ODC-BY | `build_soil.py` |
| `icrisat/*.json` | ICRISAT-TCI irrigation, land use, fertilizer, soil type, rainfall (9 files) | 21.9 MB | not stated | `build_static.py` |

- **District ↔ polygon (`district_geo.parquet`).** geoBoundaries has names only (no state, no LGD code, 7 duplicate names), so each polygon's state comes from point-in-polygon on ADM1 and a district matches on (state, name): 597 exact, 62 through an explicit alias table (renamed districts such as Gurugram/Gurgaon, Prayagraj/Allahabad, Warangal Urban/Hanumakonda), 49 fuzzy (difflib ≥ 0.80), 44 none. Staple rows with a polygon: **98.9%** overall, ~96% for 2022–24. The 44 without one are districts created after the 2021 boundaries (Nandyal, Phalodi, five new Nagaland districts, …); they have no weather and are left out of weather-based models, not given a neighbour's climate. Sikkim's four old districts were redrawn into six, so two panel districts share a polygon there.
- **Weather.** District value = mean of the grid cells whose centre lies inside the polygon, else the nearest cell with data (usual on the 1° temperature grid). Seasonal windows are fixed national calendar windows, not district crop calendars: Kharif Jun–Oct, Rabi Nov–Mar, Summer Mar–Jun, Whole Year Jun–May. Features: rainfall total, rainy days, first-30-day rain, 60-day pre-season rain, longest dry spell, mean tmax/tmin, days ≥ 35 °C, mean RH, mean radiation.
- **Soil.** The card data is the *number of samples at each level* (Low/Medium/High, Acidic/Neutral/Alkaline, …), not N, P, K in kg/ha. District features are shares and a 1–3 index. It is a 2023–25 snapshot applied to every year, an assumption.
- **ICRISAT static attributes.** A current district is attached to its 1966-boundary unit by name (246 units) or the nearest unit centroid within 100 km in the same state (flagged `icr_match`). 582 of 752 districts get values; the other 170 are mostly in states ICRISAT does not cover (North-East, Jammu & Kashmir, Goa, Delhi). Irrigation and land use are 2016–2020 means, fertilizer 2013–2017 (the files' last years).
- **IMD server.** Slow (~2 minutes per rainfall year) and it times out at connection now and then; `fetch_imd.py` is resumable and checks each file's exact byte size.

## Added 2026-10-11 (free sources): crop calendar, official state totals, HYV

| Raw (`data/raw/`) | Source | Size | Use |
|---|---|---|---|
| `crop_calendar/*.crop.calendar.fill.nc.gz` (Rice, Rice.2, Maize, Maize.2, Wheat.Winter, Wheat) + `README.txt` | SAGE crop calendar, Sacks et al. 2010, 0.5° | 0.7 MB | `build_calendar_weather.py`: weather over each district's planting-to-harvest window. Terms are not stated on the page; the authors ask users to tell them how it is used (not done). |
| `stats/agricultural_statistics_at_a_glance_2022.pdf` | DA&FW, via PARI (`ruralindiaonline.org`); `desagri.gov.in` could not be reached | 5.3 MB | Cross-check of district sums against official state totals (below) |
| `icrisat/high-yielding-varieties.json` | ICRISAT-TCI | 2.0 MB | Downloaded, **not used**: data ends 2011 and only about half the units have it for 2005–11; rice and wheat are already ~90% HYV, so it carries little signal |

- **SAGE caveats.** Windows come from sparse observations extrapolated to 0.5°; the README calls the extrapolated start/end dates the least certain. Median windows came out plausible (wheat 18 Nov → 10 Apr, Kharif rice 1 Jul → 1 Nov, maize 17 Jun → 27 Sep). The `Wheat` (spring) file gives nonsense for India and was not used. Second-season rice exists for only 62 districts, and there is no second-season maize for India.
- **District sums vs the Centre's official state figures, wheat 2020-21** (Agricultural Statistics at a Glance 2022, table 2.5(b), fourth advance estimates):

  | State | Official area Mha / production Mt | Panel | Gap |
  |---|---|---|---|
  | Uttar Pradesh | 9.85 / 35.51 | 9.85 / 37.48 | production +5.5% |
  | **Madhya Pradesh** | **6.08 / 18.18** (2,989 kg/ha) | **9.83 / 35.67** (3,630 kg/ha) | **area +62%, production +96%, yield +21%** |
  | Punjab | 3.53 / 17.19 | 3.53 / 17.18 | exact |
  | Maharashtra | 1.13 / 2.07 | 1.13 / 2.07 | exact |
  | Bihar | 2.22 / 6.15 | 2.22 / 6.64 | production +8% |
  | Rajasthan | 3.00 / 11.04 | 3.24 / 12.68 | production +15% |
  | Haryana | 2.56 / 12.39 | 2.35 / 11.41 | −8% (fewer districts reporting) |

  So the earlier suspicion is confirmed: **Madhya Pradesh is the outlier**, and the gap is in the district source itself (area and production both, not a merge artefact: the panel has one row per district-crop-season-year). Most states match closely or exactly. Both figures are official but come from different bodies (state department vs Centre's advance estimates); which is closer to the truth is not established here. District yield levels for MP should be treated with caution; changes year to year inside MP are less affected than levels.

## Added 2026-10-12: satellite NDVI/EVI (Google Earth Engine)

- **Source.** `MODIS/061/MOD13A2` (1 km, 16-day) via Earth Engine, 2005–2024, one row per district per composite (`data/raw/ndvi/ndvi_<year>.parquet`, 14,826 rows a year; about 94–95% of district-composites have a value, the rest have no cropland pixel). Script `pipeline/fetch_ndvi.py`; features `pipeline/build_ndvi_features.py`.
- **Cropland only.** The mean is over pixels that MCD12Q1 (2018, IGBP classes 12 and 14) marks as cropland and whose SummaryQA is good or marginal, so forest and towns do not dilute it. A 2018 land-cover mask is applied to every year, an assumption.
- **Season windows** are fixed (Kharif Jun 1–Oct 31; Rabi Nov 1–Apr 15), with features at 60, 90, 120 days and the full window. May composites are skipped (in no window).
- **Resolution was reduced twice, before any NDVI was modelled,** because the project's daily Earth Engine quota ran out (250 m → 500 m → 1 km). Pixel-level detail is lost, so a district mean at 1 km is adequate for district yield but is not field-level.
- **Access and cost.** Non-commercial Earth Engine project; the monthly non-commercial limit is 540,000 EECU-seconds and extraction used a small fraction. The service-account key is kept outside the repository (never committed or printed). The daily quota was raised from 18,000 to 72,000 EECU-seconds, and the change took several minutes to take effect.
- **Usage terms.** Earth Engine non-commercial terms apply, and MODIS data are public. Attribution to NASA LP DAAC is appropriate.

## Not done yet

- **ICRISAT yields (`icrisat_apportioned_apy.txt`) are downloaded but not merged.** 311 districts on 1966 boundaries, 19 states, 1966–2017. Only its irrigation, land use and fertilizer files are used (as static attributes, see above). Using its yields for pre-1997 history needs a proper boundary crosswalk.
- Reconciliation of district totals with state-level statistics (see Known issues).
- No free district-wise irrigation or fertilizer after 2020 / 2017 was found (state-by-state or paid sources only).
- Per-district crop calendars (the weather windows are fixed national ones), and weather by forecast lead time (Phase 2).
- Not used: SoilGrids (REST API paused; WCS needs large raster downloads) and Open-Meteo (its weighted free quota cannot cover 737 districts × 25 years).

# AgriPredict AI — Production Roadmap

Research date: 2026-10-10. Two parts: **what the field and market look like**, and **what that means for this repo**. Every number labelled *measured here* was computed on this repository's data (scripts in §8). Everything else is cited in §9, with a confidence note where the source was weak.

---

## 1. The one thing to know first

**The shipped model loses to trivial baselines.** Same temporal holdout as `train_v3.py` (train < 2018, test 2018–2020, Coconut excluded, 2,162 rows). *Measured here.*

| Predictor | R² | MAE (t/ha) |
|---|---|---|
| Crop mean (train years) | 0.676 | 2.27 |
| State × crop × season mean | 0.892 | 1.07 |
| **v3 model (shipped)** | **0.921** | **1.00** |
| Mean of last 3 train years, per state × crop × season | **0.941** | **0.68** |
| Last year's actual yield (persistence) | 0.924 | 0.62 |

Follow-up experiments (gradient boosting, one untuned run, so read as directional):

| Variant | MAE |
|---|---|
| crop + season + state + weather, no history | 1.07 |
| + yield history (lag 1–3, 3-yr mean, trend) | 0.76 |
| + yield history + weather | 0.755 |
| 3-yr-mean baseline on the same rows | **0.70** |
| Leave-states-out, 5 folds, no history (what an unseen region would get) | **2.02** (crop-mean baseline: 2.27) |

What this says:

1. **Weather and soil add essentially nothing** once history is known (0.760 → 0.755). That confirms `ENGINEERING_NOTES.md` §3.1 and §12.1: state-level climate cannot explain yield variation. It is a data problem, not an algorithm problem.
2. **The model never sees history.** `master_dataset_enhanced.csv` has `yield_lag1` / `yield_ma2` columns that `train_v3.py` does not use. (Check `yield_ma2` for leakage before use; I recomputed lags myself.)
3. **Dropping `state` made the model worse at its stated job** (forecasting a state's next season) to buy slider responsiveness. The notes are candid about the trade-off. It is the wrong trade for a forecasting product.
4. On unseen regions the agronomic inputs improve on a crop-mean guess by only ~11% (2.02 vs 2.27).

`ENGINEERING_NOTES.md` already reports honest R² numbers, but R² against zero is the wrong yardstick. **Skill versus a naive baseline** is what technical reviewers, insurers and agronomists ask for first. CY-Bench (§3) is built around exactly that comparison.

---

## 2. The market: what already exists

| Player | What it does | Gap relevant to you |
|---|---|---|
| **MNCFC FASAL / KRISHI-DSS** (Govt of India) | Pre-harvest national/state production forecasts for ~9–11 crops from optical + radar satellite, agro-met, field data | Official, not open at district/crop granularity for outsiders; not an API product |
| **DGCES / PMFBY crop-cutting** | Digital geotagged yield surveys (reported in 23 states as of Aug 2026 by a secondary source); pilots to cut the number of crop-cutting experiments with AI + satellite | A live government priority; the *method* (satellite + model → fewer samples) is what a credible open project can contribute to |
| **SatSure** | Satellite + weather + ML yield estimates at district/village level, sold to insurers, agritech, commodity exchanges. Vendor claims 12+ states, 18+ crops | B2B, closed, unverified claims |
| **Farmonaut** | Sentinel-2 NDVI/NDRE, SAR soil moisture, WhatsApp advisory, yield estimates | Field monitoring, vendor-reported numbers only |
| **Cropin** | Digitised CCEs for PMFBY (vendor case study); farm-management stack | Enterprise |
| **Google ALU / AMED APIs** | Field boundaries, crop type, season, 3-year history, ~biweekly refresh; trusted-tester access in 11 countries | Gated access; it gives *what is planted where*, not a yield forecast |
| **Digital Green Farmer.Chat** | Voice/WhatsApp GenAI advisory (Bhashini speech), 4,500+ extension agents; 54% of frontline workers report saving time (self-reported survey) | Advisory, not forecasting; impact evaluations still in progress |
| **Plantix** | Photo disease diagnosis, offline library, peer Q&A; pilots show mixed trust | Diagnosis, not yield |
| **Kisan Suvidha** | Weather, mandi prices, dealers, call-centre link; ~3 lakh active users (2016–17 figure) | Information app |
| **Climate FieldView** | Farm-data platform for large US farms (16% of surveyed farms in a 2019 Purdue survey) | Not smallholder |

**Pattern:** the winners either (a) own the data (government, satellite vendors), (b) own the channel (WhatsApp/voice, call centres), or (c) own the workflow (insurance, procurement). A form where you type N/P/K and get a number is none of these. It is the Kaggle tutorial that every crop-yield GitHub repo already is.

**The open slot:** there is no open, benchmarked, calibrated, district-level yield forecaster for India. SatSure/Cropin are closed. FASAL is official but not an API. Academic work is mostly single-district case studies (Punjab MODIS wheat, Bareilly Sentinel-2, tehsil-level LSTM across seven states). Nobody has shipped the combination of **rigorous evaluation + calibrated uncertainty + open data + a usable interface**.

---

## 3. What the research says

| Finding | Source | Implication |
|---|---|---|
| Random k-fold CV inflates R² by 0.22–0.38 vs leave-one-country-out; spatial CV drops UAV corn r from 0.81 to ~0.4. Temporal leakage via lag/rolling features is a parallel trap | arXiv 2605.08113 and related spatial-CV studies | Your temporal holdout is good. Add **leave-states-out** and report both |
| CY-Bench: standardised sub-national yield-forecasting benchmark (maize, wheat; 25+ countries), from AgML / Wageningen; ESSD 18:3997 (2026) | essd.copernicus.org | Copy its protocol (baselines, time-split, forecast lead times). **Build an India crop-yield benchmark in the same format** |
| Feeding crop-model (APSIM) outputs into ML cut RMSE 7–20% in the US Corn Belt; drought stress and water-table depth were the key variables | Shahhosseini et al., PMC7810832 | Raw weather is not enough; a *water-stress feature* is. A simple soil-water-balance feature is a cheap proxy |
| Forecast accuracy improves as the season advances; ensembles of models beat single ones | Corn ensembles (arXiv 2001.09055); Australian wheat hybrid | Product = **forecast that updates through the season**, not a one-shot form |
| For small tabular sets, TabPFN matched XGBoost/RF in seconds vs a 14-day tuning workflow | South Africa maize/soy/sunflower study | Cheap strong baseline to add |
| Fine-tuned Prithvi-EO beats the same architecture from scratch for pixel-level canola yield. Frozen foundation-model embeddings were tested leave-one-country-out for African maize (results not verified here) | FARM/CYPRESS (arXiv 2510.26609); arXiv 2605.08113 | Powerful, but only worth it once you have district-level labels and satellite pipelines. Do not start here |
| MODIS-based district yield: rice at ~500 m reached r = 0.85, MAE 0.15 t/ha vs district stats, 2003–2015 India; Punjab wheat per-index R² only 0.13–0.37 | Remote Sensing 2017 (RS13122379); Gupta et al. | Remote sensing helps but varies widely by crop and setup. Expect work, not magic |
| Split-conformal gave ~0.90 empirical coverage on 90% yield intervals (single paper, design unverified); coverage can fail inside subgroups, so group-conditional calibration exists | AgroX-MoE, JCIS 2026; Melki et al., ICCVW 2023 | Replace the current tree-agreement interval with **calibrated** intervals and publish the coverage |
| Deep learning wins mostly with time-series/satellite inputs; on plain tabular data gradient boosting is competitive and far cheaper. Reviews note CNN/RNN are often applied to artificially reshaped tabular data | Systematic reviews, WUR / FAO AGRIS | Do **not** bolt a deep net onto the state-level table |

---

## 4. Data: the real bottleneck

The notes say the model is capped by data, and the experiments agree. Fixes, cheapest first:

| Source | Gives you | Notes |
|---|---|---|
| **TCI–ICRISAT District-Level Database** | 571 districts, 20 states, 1966–2017, area/production/yield, irrigation, rainfall, fertiliser, prices | Free and open. Boundary changes are apportioned. Ends 2017, so you will need a newer yield source for 2018+. Soil not confirmed in it |
| **data.gov.in / DES APY statistics** | Newer district area-production-yield | Verify availability and format; not confirmed in my searches |
| **CHIRPS** | ~5 km daily rainfall | Free; sample inside district polygons |
| **NASA POWER** | Temperature, radiation, humidity, ~50 km | Coarse; adjacent districts get identical values |
| **SoilGrids** | 250 m pH, SOC, texture, N, CEC (CC-BY 4.0) | Real district-level soil; replaces the 30 constants per state |
| **MODIS / Sentinel-2 via Google Earth Engine** | NDVI/EVI/LAI time series | Phase 3 |
| **ERA5-Land, Open-Meteo** | Finer reanalysis and soil moisture | Not verified from official docs in this research; check terms first |

Moving from 30 states to ~570 districts multiplies distinct input vectors ~20×. That is the single change that lets weather and soil carry signal.

Also verify the Kaggle-origin `fertilizer` / `pesticide` columns: they look like state-level totals divided by area, not field inputs. If so, "fertiliser per ha" sliders mislead users the same way the old `confidence: 94` did.

---

## 5. Positioning: pick a wedge (your call)

| Wedge | What it is | Fit |
|---|---|---|
| **A. Open, benchmarked India yield forecaster** | District-level, in-season, calibrated intervals, public benchmark, API | Matches your skills and the empty slot. Differentiator is rigour |
| **B. Risk layer for insurers / lenders / FPOs** | Probability that a district falls below the PMFBY threshold yield; early-warning alerts | Where money and policy interest are (PMFBY CCE reduction) |
| **C. Farmer advisory (voice/WhatsApp, multilingual)** | Natural-language assistant | Crowded (Farmer.Chat), channel-heavy, needs partners. Skip for now |

**Recommendation: A, with B as the first product on top of it.** A makes the forecasts credible; B gives them a user. C is a later add-on over the same API.

---

## 6. Roadmap

### Phase 0 — Stop the bleeding (days) — done 2026-10-11

Outcome: MAE 1.00 → 0.68 t/ha, but **skill is still −9.6%** against repeating last season (0.62). The history features closed most of the gap; weather and soil add nothing on top (ablation), which is the case for Phase 1. Details and the numbers behind each item are in `ENGINEERING_NOTES.md` §15.

- [x] **Add baselines to `train_v3.py` and publish skill score** (`1 − MAE_model / MAE_baseline`). Four baselines on identical rows; Model Performance now leads with skill.
- [x] Use yield history as features (lag 1–3, rolling mean, trend), computed per state × crop × season. `state` re-added. `yield_ma2` and `yield_change` contain the current season's yield (94.9% of rows) and are not used; `yield_lag1` is recomputed.
- [x] Add leave-states-out CV and a leave-last-years-out check; report both. Leave-states-out (5 folds) and rolling origin (test years 2015–2020).
- [x] `api.py:253` — `except Exception: prediction = 0.0` returns a fake zero forecast silently. Now logs and returns 500.
- [x] Validate inputs: unknown `crop`/`season`/`state` and out-of-range numbers are 422; so is a series with no recorded season in the previous three years.
- [x] Remove or label invented content: the "8–12%" and "~10%" claims are gone; scores and notes are labelled as fixed-threshold rules of thumb.
- [x] CORS `allow_origins=["*"]` with `allow_credentials=True`: now an allow-list from `CORS_ORIGINS`. **Set it on Cloud Run before deploying** or the production frontend will be blocked.
- [x] Pick one deploy target: Cloud Run + Vercel. `Procfile` and `railway.json` removed.

### Phase 1 — Real data (1–2 weeks)

- [x] **Step 0: check label coverage first (see §10.4).** Done 2026-10-11. The mirror's "2020 <50%, 2021 3%" warning is outdated: DES APY has 706–712 districts in 2020-21 and 2021-22, and UPAG adds 2013-14 → 2024-25 (2024-25 partial). 2000–2024 is covered for every staple. ICRISAT ends in 2017 and has 311 districts on 1966 boundaries, not 571.
- [x] Yield labels: DES APY + UPAG merged into `data/processed/district_yield.parquet` (441k rows, 752 districts, 1997–2024; `pipeline/build_district_yield.py`). ICRISAT yields downloaded but **not merged** (needs a boundary crosswalk); its irrigation / land use / fertilizer are used as static attributes.
- [x] Boundaries, weather, soil (2026-10-11): geoBoundaries ADM2 matched to 708 of 752 districts (98.9% of staple rows); IMD rain/tmax/tmin 1997–2024; NASA POWER humidity/radiation; Soil Health Card (1.1 GB) aggregated to 738 districts. Open-Meteo and SoilGrids were not used (see data card).
- [x] C1–C3 evaluated (see criteria above): C1 pass (+1.8%), C2 pass as written (+18.6%, inflated; strict +0.2%), **C3 fail** (+0.2%). Exploratory: weather helps Kharif Rice + Maize in 6/6 years (+2.5%) and hurts Wheat.
- [~] Reproducible pipeline: raw files outside git, processed output gitignored, one script per source. Yield done; weather and soil pending. No `make` on Windows, so plain `python pipeline/<script>.py`.
- [~] Data card: `data/DATA_CARD.md` written for the yield panel (sources, licences, rules, known issues). Open item: district sums overshoot official national production by ~15–20%, mostly in Madhya Pradesh; reconcile with state statistics. Coconut unit track still open.

#### Phase 1 pass/fail criteria (written 2026-10-11, before any district-level model was run)

Scope: Rice, Wheat, Maize; each (district, crop, season) series forecast one season ahead; train < 2018, test 2018–2023 (2024 excluded, partial); a row needs at least one yield in the three seasons before it. Baselines: last season repeated, 3-season mean, district series mean, state × crop mean.

- **C1.** Model MAE beats "last season repeated" on the pooled holdout **and** in at least 4 of the 6 single test years (rolling origin).
- **C2.** Positive skill in leave-districts-out (5 folds, whole districts withheld, their own history still an input).
- **C3.** Weather and soil count as useful only if adding them to history lowers MAE by at least 2% against the history-only model. Otherwise the result is reported as "no measurable gain".
- All three are reported whatever the outcome. The criteria are not changed after seeing results; any later change is recorded as a change, with the reason.

**Results so far (district history only, no weather or soil; `pipeline/district_baseline.py`, 2026-10-11):**

| Check | Result |
|---|---|
| C1 pooled 2018–2023 (n = 15,453) | MAE 0.446 vs 0.454 for last season: **+1.8%, PASS**. Better in 6 of 6 single years (+0.9% to +7.4%). |
| …against other baselines | −0.5% vs the 3-season mean (0.444); Maize −0.5%; Rice +5.5%, Wheat +3.7%. |
| C2 leave-districts-out as written | +18.6%, **PASS as written**, but misleading: the training folds contain other districts' rows from the *same years* tested, so the model can learn a year's common shock (a drought) that is not knowable in advance. |
| Extra (added after C2 passed, not a pre-registered criterion): unseen districts **and** unseen years | MAE 0.4536 vs 0.4543: **+0.2%, effectively zero.** This is the honest figure for a district the model has not seen. |

Reading: with only a district's own past, a model barely beats repeating last season, and it adds nothing for districts it has not been trained on. Whatever weather and soil add (C3) is what makes the product worth building.

**C3 result (`pipeline/district_weather_eval.py`, 706 districts with a polygon, identical rows for all models):**

| Model, 2018–2023 holdout (n = 15,241) | MAE | vs history-only |
|---|---|---|
| History only | 0.4440 | — |
| + season weather (IMD rain/temp, POWER humidity/radiation, raw + anomalies) | 0.4430 | +0.2% |
| + weather + Soil Health Card + ICRISAT irrigation/intensity/fertilizer | 0.4444 | −0.1% |

**C3: FAIL** (needs ≥ 2%). Single test years range from −0.5% to +3.4%. Per crop on the holdout: Rice −1.0%, Wheat −7.2%, Maize +2.0%. This is an upper bound (it uses the weather that actually fell over the season, unknown at forecast time), so weather does not clear the bar even with hindsight.

**Exploratory follow-up, run after C3 failed, so not pre-registered and not to be quoted as a pass:**

| Subset (rolling origin, each year trained on earlier years only) | Result |
|---|---|
| Kharif Rice + Maize, 28,203 rows, 701 districts | weather helps in **6 of 6** test years (+0.3% to +4.6%); pooled MAE 0.4359 → 0.4249, **+2.5%** |
| Rabi Wheat, 12,188 rows, 602 districts | weather **hurts** in 3 of 6 years; pooled −2.6% |
| Holdout split by irrigation (Kharif) | rainfed-leaning districts +8.1%, irrigated +4.3%; Rabi overall +1.8% |
| Detrended yield variation explained by season weather (OLS, district effects) | Rice 3.9%, Maize 1.1%, Wheat 5.1% |

Reading: weather carries a modest, consistent signal for the monsoon (Kharif) crops, and for wheat the same features are noise that hurts. The pooled test hid the first by averaging in the second. Because the subsets were chosen after seeing C3, this needs a fresh, pre-registered test (Phase 2: per-season models, and weather by forecast lead time rather than realised season weather) before it counts. Seasonal totals explain only a few percent of within-district variation, so the fixed calendar windows and season totals are probably too coarse to capture much more.

#### C4: calendar-aligned weather (criteria written 2026-10-11, before this test was run)

Motivation: the C3 weather windows were fixed national calendar windows. For wheat the Rabi window (Nov–Mar) ends before the harvest SAGE gives for most wheat districts (April–May), so it misses the grain-filling heat that most affects wheat. New windows run from each district's SAGE mean planting day to mean harvest day (0.5° gridded crop calendar, Sacks et al. 2010), plus last-30-days-before-harvest temperature features. Rice (main) and Kharif Maize use SAGE's main-season calendars, Wheat uses `Wheat.Winter`, Rice Rabi/Summer uses `Rice.2` where it exists, and everything else keeps the fixed window.

Same protocol as before: one model per group, rolling origin over test years 2018–2023, each year trained only on earlier years, identical rows for every compared model.

- **C4a (Wheat):** calendar-window weather beats history-only pooled by ≥ 1.0% **and** is better in ≥ 4 of 6 years. (Fixed-window weather was −2.6% and worse in 3 of 6.)
- **C4b (Kharif Rice + Maize):** calendar-window weather beats history-only pooled by ≥ 2.5%, the figure fixed windows reached post hoc, **and** in ≥ 4 of 6 years.
- Both are reported whatever the outcome. Neither re-opens C3, which stays FAIL.

**C4 result (`pipeline/district_calendar_eval.py`, rolling origin 2018–2023, identical rows within each group):**

| Group | History only | Fixed-window weather | Calendar-window weather | Calendar + static |
|---|---|---|---|---|
| Wheat (Rabi), 12,188 rows | 0.3004 | 0.3082 (−2.6%) | 0.3005 (**−0.0%**, better in 3/6 years) | 0.3038 (−1.1%) |
| Kharif Rice + Maize, 28,138 rows | 0.4379 | 0.4249 (**+3.0%**, 6/6) | 0.4289 (**+2.1%**, 6/6) | 0.4267 (+2.6%) |

**C4a (Wheat): FAIL** (needed ≥ +1.0% and ≥ 4/6 years; got −0.0%, 3/6). **C4b (Kharif Rice + Maize): FAIL** (needed ≥ +2.5%; got +2.1%, 6/6 years).

Reading: calendar-aligned windows removed the harm weather did to wheat (−2.6% → 0.0%) but gave no gain, and for Kharif they were slightly *worse* than the crude fixed windows (+2.1% vs +3.0%), so the SAGE calendar (0.5°, extrapolated from sparse observations) did not beat a fixed Jun–Oct window. For Kharif Rice + Maize the weather signal is real and consistent (6/6 years in both versions) but small, about 2–3% of MAE. Static attributes (irrigation, intensity, fertilizer) did not add reliably. The hypothesis that mis-timed windows explained the wheat result is not supported.

#### C5: satellite NDVI/EVI (criteria written 2026-10-11, before any NDVI was extracted or modelled)

Source: MODIS MOD13Q1 v061 (250 m, 16-day) via Google Earth Engine, averaged over cropland pixels only (MCD12Q1 2018, classes 12 and 14), pixels with SummaryQA ≤ 1, per district polygon, 2000–2024. Season windows are the fixed ones (Kharif Jun 1–Oct 31; Rabi Nov 1–Apr 15, so wheat's grain-filling is included). Features: peak, mean and accumulated NDVI/EVI over the window, and the same as anomalies from the district's own training-year norm.

Protocol as before: one model per group (Kharif Rice + Maize; Wheat/Rabi), rolling origin 2018–2023, each year trained on earlier years only, identical rows for every compared model.

- **C5a (ceiling, full-season NDVI):** history + weather + NDVI lowers MAE versus history + weather by ≥ 3.0% pooled **and** in ≥ 4 of 6 years, in at least one of the two groups.
- **C5b (the product question, lead time):** NDVI truncated at 60 days after the window opens (what is known about two months into the season), added to history alone, beats history-only by ≥ 2.0% pooled **and** in ≥ 4 of 6 years, in at least one group. Lead times of 90 and 120 days are reported as well, not scored.
- Reported whatever the outcome. C1–C4 are not re-opened.
- *Amendment, same day, before any NDVI was modelled:* the project's Earth Engine daily compute quota ran out during extraction, twice, even at 500 m. NDVI therefore comes from MOD13A2 (1 km, 16× fewer pixels than the 250 m product), May composites (in no window) are skipped, and extraction starts at 2005, so training begins in 2005–06. Criteria are unchanged.

**C5 result (`pipeline/district_ndvi_eval.py`; MOD13A2 1 km NDVI/EVI over cropland pixels, 706 districts, 2005–2024; rolling origin 2018–2023, identical rows within each group):**

| Group | history | + weather | + weather + NDVI (full) | history + NDVI @60 d | @90 d | @120 d | full season |
|---|---|---|---|---|---|---|---|
| Wheat (Rabi), 9,043 rows | 0.3059 | 0.3065 (−0.2%) | 0.3073 (−0.5%) | **0.2991 (+2.2%)** | 0.2964 (+3.1%) | 0.2981 (+2.5%) | 0.2976 (+2.7%) |
| Kharif Rice + Maize, 20,576 rows | 0.4552 | 0.4422 (+2.9%) | 0.4372 (**+4.0%**) | 0.4518 (+0.7%) | 0.4510 (+0.9%) | 0.4473 (+1.7%) | 0.4433 (+2.6%) |

(percentages are versus history only.)

- **C5a: FAIL.** NDVI over history + weather: Wheat −0.3% (2/6 years), Kharif +1.1% (6/6 years). Needed ≥ +3.0% and ≥ 4/6 in at least one group.
- **C5b: FAIL, narrowly in Wheat.** NDVI at 60 days over history: Wheat +2.2% pooled, which clears the 2.0% bar, but better in only 3 of 6 years (needed 4); Kharif +0.7%, 3/6.

Reading (not scored, so not claims): for **Wheat**, NDVI helps while weather does not (+2.2% to +3.1% at every lead from 60 days to full season, against −0.2% for weather), which is consistent with the earlier finding that weather totals are noise for wheat. For **Kharif Rice + Maize**, weather and NDVI both help a little and NDVI adds a consistent extra ~1% on top of weather in every test year (6/6), for +4.0% over history in total, but this uses the whole season (hindsight); at 60 days NDVI gives only +0.7%. The wheat lead-time pattern (4 of 6 years better at 90 days) was seen after the fact and needs a fresh test. 2024 (NDVI extracted, yields partial) has not been used anywhere and should be the untouched confirmation set in Phase 2.

#### Phase 2 protocol and criteria (written 2026-10-12, before any Phase 2 model was run)

What changes from the C-series tests: every feature is limited to what is known **at the forecast date**. Weather and NDVI at lead *L* use only days from the window opening (Kharif Jun 1, Rabi Nov 1) up to day *L*. Earlier tests used the whole season (hindsight).

- **Groups and inputs** (chosen from the exploratory findings above, so this design is itself post hoc): *Kharif Rice + Maize* = district history + to-date weather + NDVI; *Wheat (Rabi)* = district history + NDVI, no weather.
- **Leads:** 0 (history only, "at sowing"), 60, 90, 120 days. Reported as an accuracy-versus-lead-time curve.
- **Model:** the anchored Extra Trees used so far, configuration fixed now, no tuning. (LightGBM, TabPFN and SHAP from the original Phase 2 list are not attempted here.)
- **Evaluation:** rolling origin 2018–2023 as development (these years have been seen in earlier tests, so they are not clean) and **2024 as the confirmation set**, never used for any decision, model trained on years ≤ 2023. 2024 yields are partial (UPAG 2024-25), so n and coverage are reported with it.
- **P2-1, skill:** at lead 90, pooled over both groups, MAE beats **last season repeated** by ≥ 3.0% on rolling 2018–2023 and in ≥ 4 of 6 years, **and** by ≥ 2.0% on 2024.
- **P2-2, intervals:** 80% intervals from split conformal calibration (the previous year's out-of-sample forecast residuals, on a relative scale) have empirical coverage between 72% and 88%, pooled on 2018–2023 and on 2024.
- **P2-3, trust flags:** rows whose recent yield volatility is in the top 20% of training rows are flagged low-trust, and their MAE is ≥ 1.3× that of unflagged rows on the test years.
- Everything is reported whatever happens; the criteria are not changed after seeing results.

**Phase 2 results (`pipeline/phase2_forecast.py`; 2026-10-12; protocol above).** Kharif Rice + Maize (21,681 rows, 668 districts) and Wheat/Rabi (9,498 rows, 553 districts); each year trained on earlier years only; 2024 untouched until the confirmation run.

| Lead (days into season) | 2018–23 MAE | vs last season repeated | vs 3-season mean | 2024 MAE | vs last season | vs 3-season mean |
|---|---|---|---|---|---|---|
| baselines | persistence 0.4192, 3-yr mean 0.4031 | | | persistence 0.3908, 3-yr mean 0.3862 | | |
| 0 (history only) | 0.4093 | +2.4% | −1.6% | 0.3704 | +5.2% | +4.1% |
| 60 | 0.4009 | +4.4% | +0.5% | 0.3593 | +8.1% | +7.0% |
| **90** | **0.3999** | **+4.6%** | **+0.8%** | **0.3518** | **+10.0%** | **+8.9%** |
| 120 | 0.3969 | +5.3% | +1.5% | 0.3511 | +10.1% | +9.1% |

- **P2-1 PASS** (lead 90 vs last season repeated): +4.6% on 2018–2023 and better in 6 of 6 years (+1.0% to +10.7%), +10.0% on 2024.
- **P2-2 PASS:** 80% intervals cover 80.8% on 2018–2023 and 86.9% on 2024.
- **P2-3 PASS:** flagged (top-20% volatility) rows have 1.65× the MAE of unflagged on 2018–2023 and 1.66× on 2024.

**What the pass does not say (checks run after the criteria were scored, so labelled as such):**
- **The criterion's baseline was last season repeated, but on 2018–2023 the 3-season mean is the stronger baseline in these groups.** Against it the model is +0.8% at lead 90 (Wheat +0.0%, Kharif +1.0%). The honest headline for 2018–2023 is a small gain, not a large one.
- **2024 looks much better (+10.0%) partly because it is an easier, partial year:** every method's error is lowest in 2024 (model 0.352 vs 0.380–0.43 in other years), and 2024 covers 28 states with 1,544 forecasts rather than ~1,700. Treat +10% as an upper estimate. For Wheat in 2024 the model is only +2.8% over last season, though +14.1% over the 3-season mean.
- **What weather and NDVI add over history-only (lead 0 → lead 90):** Kharif +2.1% (2024: +6.1%), Wheat +3.1% (2024: +1.2%). Gains arrive early: most of it is there by day 60.
- **Intervals are wide:** median half-width ±26% of the forecast (0.68 t/ha). With the pre-registered single calibration value, coverage of the flagged (volatile) rows is only 62% (2018–23) and 68% (2024), and Madhya Pradesh 70% in 2018–23. A **Mondrian (per-flag) conformal** version, an exploratory post-hoc fix needing no refit, gives flagged coverage 79% and 80% with half-width ±42% and ±38%, unflagged ±22–24%, overall coverage unchanged (80.1%, 87.0%). That is the version to serve.
- Year-to-year coverage on 2018–23 ranges 77%–84%.

Not done in Phase 2: TabPFN, SHAP, LightGBM, a water-balance feature, forecasts that include a weather forecast for the rest of the season (no historical forecasts were collected), crops other than Rice, Maize and Wheat, and any change to the deployed API (it still serves the state-level v3.1 model).

#### Gate G1 before Phase 4: publication lag (criteria written 2026-10-12, before it was run)

Every backtest above assumes the previous season's district yield is known when the forecast is made. It is not: district yields are published with a lag (the DES APY mirror held 2022-23 in Dec 2023; UPAG 2024-25 appeared in Sept 2026), so a Kharif *Y* forecast issued around August *Y* can use seasons up to *Y*−2 at best, not *Y*−1. G1 re-runs the Phase 2 protocol with that lag: the history features come only from seasons ≤ *Y*−2 (`lag1` = the most recent *available* season), and the baselines are the same-information ones (the last available season repeated, the mean of the last three available). Weather and NDVI are unchanged.

- **G1 pass:** at lead 90, pooled over both groups, MAE beats **the last available season repeated** by ≥ 3.0% on 2018–2023 and in ≥ 4 of 6 years, and by ≥ 2.0% on 2024; 80% interval coverage between 72% and 88% on both.
- If G1 fails, the product may not claim that skill; it would have to be offered as a monitoring tool, or only where the data lag is zero. Reported whatever happens.

> **Superseded in part (Amendment A1, below):** the rolling origin used for G1, the model-size table and Phase 2 trained each test year on rows through *Y*−1, which the publication lag does not allow. Re-tested lag-consistently, the staple models' skill against the 3-season mean was Kharif +1.4% and Wheat +4.0% on 2018–23 and negative on 2024. The figures below are kept as they were reported.

**G1 result (`HIST_SHIFT=1 python pipeline/phase2_forecast.py`; 2026-10-12): PASS.** With a one-season publication lag (history from seasons ≤ *Y*−2; Kharif Rice + Maize 21,416 rows, Wheat 9,398 rows):

| Lead | 2018–23 MAE | vs last available season | vs 3-season mean | 2024 MAE | vs last available | vs 3-season mean | 80% coverage (dev / 2024) |
|---|---|---|---|---|---|---|---|
| baselines | persistence 0.4852, 3-yr mean 0.4535 | | | persistence 0.4902, 3-yr mean 0.4564 | | | |
| 0 (history only) | 0.4412 | +9.1% | +2.7% | 0.4370 | +10.9% | +4.3% | 80.6% / 82.3% |
| 60 | 0.4368 | +10.0% | +3.7% | 0.4385 | +10.6% | +3.9% | 80.7% / 83.1% |
| **90** | **0.4362** | **+10.1%** (6/6 years, +5.1% to +13.6%) | **+3.8%** | **0.4400** | **+10.2%** | **+3.6%** | **80.7% / 82.3%** |
| 120 | 0.4344 | +10.5% | +4.2% | 0.4414 | +10.0% | +3.3% | 80.5% / 82.7% |

What it means, plainly:
- **The skill survives the lag, but the forecast gets worse in absolute terms:** lead-90 MAE 0.436 t/ha with the lag against 0.400 without it. Skill percentages look larger because the naive baseline, a season staler, degrades more than the model does. The fairer reading is the 3-season mean: **+3.8% (2018–23) and +3.6% (2024)**.
- **Most of the skill comes from the history-only model (lead 0).** Adding in-season weather and NDVI moves 2018–23 MAE from 0.4412 to 0.4362, about 1.1%, and **does not help at all in 2024** (lead 0 is the best lead there, 0.4370 vs 0.4400). Wheat 5.0% and Kharif 11.4% over last available season on 2018–23 at lead 90.
- **Consequence for the "live data" idea:** under a realistic publication lag, live weather and NDVI are worth about 1% of MAE on the development years and nothing on 2024, while the history-only forecast needs no live feed. A live pipeline is a larger engineering cost than the accuracy it buys; the first product slice is therefore the history-only forecast with an in-season update as an optional later layer.
- Intervals: 80% coverage 80.7% (dev) and 82.3% (2024) with the single calibration value. Trust-flag MAE ratio 1.51 (dev) and 1.70 (2024).

#### Model size for serving (criteria written 2026-10-12, before any smaller model was run)

Deploys are triggered by pushing to GitHub, so whatever the district service needs must be in git, and anything committed stays in history. The two served models are 32.7 MB + 22.4 MB. Candidates are Extra Trees configurations that differ from the current one only in `min_samples_leaf`, `n_estimators` and `max_depth`. Each is evaluated under the Gate G1 protocol (history-only, one-season publication lag, rolling origin 2018–2024), serving's lead 0.

- **Accept** a configuration if (a) the two models together pickle (compress=3) to **≤ 15 MB**, (b) pooled MAE on 2018–2023 is within **+1.0%** of the current 0.4412 t/ha, and (c) MAE on 2024 is within **+1.5%** of the current 0.4370.
- Among those that pass, take the **most accurate** on 2018–2023 (not the smallest). If none passes, the current models ship unchanged and are committed once, deliberately.
- The interval calibration and trust flags are recomputed from the chosen configuration's own rolling-origin residuals, never reused from the larger model.

**Model size result (`pipeline/shrink_experiment.py`, 2026-10-12), lead 0, one-season publication lag, rolling origin 2018–2024:**

| Configuration | Both models, pickled | MAE 2018–23 | MAE 2024 | Accepted |
|---|---|---|---|---|
| current (leaf 2, 200 trees) | 55.1 MB | 0.4412 | 0.4370 | reference |
| leaf 5, 200 trees | 30.6 MB | 0.4381 | 0.4318 | no (size) |
| leaf 5, 100 trees | 15.4 MB | 0.4387 | 0.4322 | no (size) |
| leaf 10, 100 trees | 8.9 MB | 0.4367 | 0.4365 | yes |
| **leaf 20, 100 trees** | **5.0 MB** | **0.4364** | 0.4411 (+0.9%) | **yes, chosen** |

The rule picked leaf 20 / 100 trees (most accurate on 2018–23 among the accepted); it is a near-tie with leaf 10 (0.4364 vs 0.4367), and 2024 is 0.9% worse than the large model, inside the allowed 1.5%. The smaller trees are more regularised, so they were slightly *better* on the development years, not just smaller. Served as of 2026-10-12; calibration, trust flag and skill figures are recomputed from this configuration's own forecasts. Per group (history-only, one-season lag): **Wheat +6.1% / +8.8%** and **Kharif Rice + Maize +11.1% / +2.2%** against the last published season / the 3-season mean on 2018–23 (2024: Wheat +6.7% / +7.0%, Kharif +11.0% / +2.2%). These replace the figures quoted from the large model (Wheat +7.0%, Kharif +1.4% vs the 3-season mean; Wheat 2024 +15.6% was a high reading that the smaller model does not reproduce).

#### One table, one model (criteria written 2026-10-12, before any model was trained on `master_panel.parquet`)

The served models so far were trained from the pipeline's separate files, for three staples only, on rows that also had NDVI and to-date weather (2005 onward). The master table holds 100 crops. This block trains from the master table alone and decides what the service may claim. `pipeline/train_master.py` implements exactly what is written here.

**Fixed for every step.** Rows: `level == "district"`, `valid_yield`, not `flag_outlier`, year ≤ 2024, Coconut excluded (nuts, not tonnes); no polygon needed. Series = (district, crop, season). One-season publication lag (Gate G1): history from seasons ≤ *Y*−2; a row is forecastable if at least one of its three lags exists. Rolling origin: test years 2018–2023 (development) and 2024 (confirmation); each test year is predicted by a model trained on earlier years only; 2017 is predicted only to calibrate 2018. Extra Trees as served (100 trees), anchored on the last published season. Baselines on identical rows: the last published season repeated, and the mean of the last three published ("3-season mean"). Skill = 1 − MAE_model / MAE_baseline, **per crop or group, never pooled across crops** (units differ by 100×).

- **M1, staples from the master table.** Kharif Rice + Maize and Wheat (Rabi), one model each, the current design (absolute change from the anchor, leaf 20), trained on every forecastable row. *Pass* if skill against the 3-season mean on 2018–23 is ≥ +1.2% (Kharif) and ≥ +7.8% (Wheat), i.e. not more than 1.0 point below the published +2.2% and +8.8%, and is > 0 on 2024 for both. The same figures are also reported on the old rows (those with NDVI at day 120) so a change in row set cannot hide a change in skill. *Fail* → serving keeps the old row rule.
- **M2, do the other master columns help the staples?** Add the columns known before any season: `soil_*`, `icr_*`, `irr_*`, `cropping_intensity`, `fert_npk_per_ha`, `lon`, `lat`. *Pass* if pooled over the two groups MAE is ≥ 2.0% lower than M1 on 2018–23, lower in ≥ 4 of 6 years, and not higher on 2024. *Fail* → the served model stays history-only. (Weather and NDVI were settled by Phase 2 and Gate G1: ≈1% under the lag, nothing in 2024, and they need a live feed.)
- **M3, one pooled model for every crop.** Target = yield ÷ last published yield − 1 (relative, so sugarcane and pulses share a model); features: year, history seasons, the three lags, 3-season mean and trend divided by the anchor, log anchor, and crop / season / state as categories. Extra Trees, 100 trees, `min_samples_leaf` ∈ {20, 50, 100}: take the most accurate on 2018–23 whose full-data pickle (compress=3) is ≤ **15 MB**. A crop is **served** if, on 2018–23, it has ≥ 300 test rows, skill against the 3-season mean ≥ **+2.0%** and is better than it in ≥ 4 of 6 years, and its 2024 skill against the 3-season mean is ≥ 0. Every other crop is shown as history and the 3-season mean only, labelled "the model adds nothing here". About 40 crops are tested, so a few will pass by chance; the year-count and 2024 conditions are the guard, and the served list is reported with its 2024 numbers. The pooled model **replaces** the M1 group models only if on the two staple groups its skill against the 3-season mean (2018–23) is within **1.0 point** of M1's; otherwise staples keep the M1 models and the pooled one serves the other crops.
- **M4, intervals and trust flag for what is served.** Mondrian conformal by volatility flag (top 20% of the training rows' volatility), calibrated on the previous year's out-of-sample relative residuals of the served crops. *Pass* if pooled 80% coverage over served crops is within 72–88% on 2018–23 and on 2024, flagged-row coverage is ≥ 70% on both, and the flagged ÷ unflagged MAE ratio is ≥ 1.3 on 2018–23. A failure is published with the achieved coverage, not tuned away.

Reported whatever happens. Nothing here is tuned after seeing the results; the only free choice, the leaf size, is made by the rule in M3.

**Amendment A1 (2026-10-12; written after M1 and M2 had run as above and before any M3 result was seen).** A check on the two staple groups showed the rolling origin as first written is not lag-consistent. For a test year *Y* it trains on rows through *Y*−1, but with a one-season publication lag the yields of *Y*−1 are not yet known when a *Y* forecast is made, and the model can carry *Y*−1's shocks into *Y* through `year`, `state` and `crop`. Trained on rows through *Y*−2 instead, skill against the 3-season mean on 2018–23 fell from +2.2% to +1.4% (Kharif Rice + Maize) and from +8.3% to +4.0% (Wheat), and on 2024 from +1.4% to −1.9% and from +6.5% to −1.8%. So every figure from the earlier protocol (Gate G1, the model-size table, the Phase 2 results) overstates what a forecaster could have achieved, and the District Forecast page quoted them. From here on:
- (a) the model for test year *Y* is trained on rows with year ≤ *Y*−2; (b) the interval for *Y* is calibrated on the out-of-sample residuals of year *Y*−2, the latest whose yields are known; (c) test years run 2016–2024, with 2016 and 2017 used only to calibrate 2018 and 2019; (d) the trust-flag threshold comes from the same training rows.
- M2, M3 and M4 keep every bar as written and are re-run under this protocol; their first-protocol results (M2: +1.40%, fail) stay on record beside them. M1's bars were set against the earlier published numbers, so M1 keeps its first-protocol verdict (pass) and its lag-consistent figures are reported without a verdict.

**Amendment A2 (2026-10-12; written after M3 returned no served crop under the lag-consistent protocol, and before anything below was computed).** M3's own rule says a crop that does not clear the bar is shown as history and the 3-season mean only. With no crop clearing it, nothing is forecast by a model, and the service can honestly offer one thing: the mean of the last three published seasons as the expected yield, with a range. Its range is a new item with its own bar, set here:
- **B1, range around the 3-season mean.** 80% range = mean × (1 ± *q*), with *q* the 80% quantile (finite-sample corrected) of |y − mean| ÷ mean over the rows of year *Y*−2 for the same crop and the same volatility flag (flag = top 20% of volatility among rows through *Y*−2). A crop with fewer than 100 such rows in a flag class uses that class's pooled quantile over all crops. *Pass* if coverage pooled over all crops is within 72–88% on 2018–23 and on 2024, and flagged-series coverage is ≥ 70% on both. A failure is published with the coverage achieved, not tuned away.
- The served ranges pool three years (2022–24) per crop and flag instead of one, because a single year was too noisy in Phase 2; the pass/fail test above uses the single-year rule.
- Also reported, not a bar: how often the 3-season mean beat repeating the last published season, per crop, since that is the reason to offer it.

**Results (`python pipeline/train_master.py`, 2026-10-12; `master_models_metrics.json`).** Master table: 348,287 forecastable district rows, 77 crops (after the one-season lag), 733 districts.

| Step | As first written (trained through *Y*−1) | Lag-consistent (Amendment A1; trained through *Y*−2) | Verdict |
|---|---|---|---|
| M1, staples, skill vs 3-season mean, 2018–23 (2024) | Kharif Rice + Maize **+2.2%** (+1.4%), Wheat **+8.3%** (+6.5%) | Kharif **+1.4%** (−1.9%), Wheat **+4.0%** (−1.8%); better than the mean in 4 and 2 of 6 years. On the old NDVI-covered rows: +1.5% / +4.1% | first protocol **PASS** (bars +1.2% / +7.8%); lag-consistent reported without a verdict |
| M2, soil + irrigation + location columns, pooled MAE gain | +1.40% (2024 +1.10%), better in 6 of 6 years | **+0.80%** (2024 +1.32%), better in 6 of 6 years | **FAIL** both (bar +2.0%) |
| M3, one pooled model, crops served | not run | **0 of 63 crops** (53 with ≥ 300 unseen forecasts). Leaf 20, 7.3 MB (leaf 50 and 100: 6.0 and 4.9 MB, less accurate) | **FAIL** |
| M4, ranges for the served crops | not run | not applicable: nothing was served | n/a |
| B1 (A2), 80% range around the 3-season mean | not run | coverage **82.5%** (2018–23), **80.1%** (2024); volatile series 82.4% and 79.0%; stable 82.6% | **PASS** |

What it means, plainly:
- **No crop's model beat the 3-season mean by the bar.** Six crops reached +2.0% on 2018–23 but each missed another condition: Other Oilseeds (+9.1%, 5 of 6 years, but no 2024 yields published), Khesari (+3.4%, 3 of 6 years, no 2024), Groundnut (+2.7%, 5 of 6 years, 2024 −0.1%), Gram (+2.6%, 3 of 6, 2024 −3.2%), Wheat (+2.5%, 4 of 6, 2024 −5.3%), Rice (+2.4%, 5 of 6, 2024 −7.8%). The pooled model is worse than the separate staple models (Kharif +0.2%, Wheat +2.6%) and breaks down on a few crops with extreme records (sugarcane, turmeric, ginger: skill below −400%).
- **The earlier figures were optimistic.** Training each test year on the year before it lets the model carry that year's shocks into the next, which the publication lag forbids. Every number from Gate G1, the model-size table and the District Forecast page that came from that protocol (Wheat +8.8%, Kharif +2.2%, "+3.8% against the 3-season mean") is superseded by the lag-consistent ones above.
- **What is offered instead.** The expected yield is the mean of the last three published seasons. It had lower error than repeating the last published season for 42 of the 63 crops (+3.3% pooled over rows), and its 80% range held. The model that was tested is reported on the Model & Evidence page and is not served. Weather, satellite, soil and irrigation columns remain unused: each failed its bar, weather and NDVI under the more generous protocol.
- **Not claimed:** that no model could do better. Untried, each needing its own bar before it runs: crop-specific models, a robust target for the pooled model (extreme ratios dominate it), the in-season weather and NDVI at lead times with a live feed, and state advance estimates that are published earlier than district yields.

### Phase 2 — Forecasting that deserves the name (2–3 weeks)

- [~] LightGBM/CatBoost on district × crop × year with history + weather + water-balance feature. Done with the anchored Extra Trees on district history + to-date weather + NDVI, 3-yr-mean baseline in every report; LightGBM, CatBoost and a water-balance feature not tried.
- [x] **Forecast at lead times** (0, 60, 90, 120 days). Accuracy per lead time is reported above, under "Phase 2 results"; every input is limited to what is known at the lead.
- [ ] Add TabPFN and a simple ensemble as comparison rows. Not attempted.
- [x] **Calibrated intervals**: split conformal on the previous year's out-of-sample residuals; coverage published. Group-conditional (by trust flag) version fixes under-coverage of volatile series.
- [ ] SHAP for the explanation panel, replacing the hand-written recommendations. Not attempted.
- [x] "Do not trust" flag from recent yield volatility (district level). Per-crop and per-region flags beyond that, including the Madhya Pradesh source discrepancy, are not wired in.

### Phase 3 — Satellite (4+ weeks, only after Phase 2 beats baseline)

- [ ] MODIS/Sentinel-2 NDVI/EVI seasonal curves via Earth Engine as features for rice/wheat first, where literature shows signal.
- [ ] Optional: a Prithvi-EO embedding feature as an experiment, judged with leave-states-out, not random CV.

### Phase 4 — Product

- [~] District forecast service and page, first slice (2026-10-12): `district_forecast.py`, `/api/district/{options,forecast,track-record}`, **District Forecast** page. Serves history-only forecasts for Rice and Maize (Kharif) and Wheat (Rabi) for 2025 and 2026, with an 80% range calibrated per trust flag, the last published season and 3-season mean beside it, a volatile/stable flag, a Madhya Pradesh source warning, and a track record of out-of-sample past forecasts. The skill sentence is generated from the numbers, so for Kharif Rice + Maize it says the model is only a little better than the 3-season average (+2.2% on 2018–23); the wording has three tiers (below 2%, 2–5%, above 5%). **District map** added the same day (`/api/district/map`, `/api/district/shapes`, **District Map** page): 706 outlines drawn in plain SVG (no map library, 0.43 MB), coloured by change vs last published season, vs the 3-season mean, or by level; volatile series hatched; hover for the range and baselines; a click opens that district on the forecast page, and `test_district.py` checks that a district on the map and on the forecast page agree exactly. Still to do: **change since last update** (needs a refresh, which the history-only model does not have) and any weekly refresh. **Superseded the same day by the next item: the model figures quoted here came from the too-generous protocol.**
- [x] **One dataset behind every page, and an honest outlook (2026-10-12).** Dashboard, Historical Trends, Crop Insights, Soil & Climate, Model & Evidence, District Outlook and District Map all read small views of `master_panel.parquet` (`pipeline/export_serving.py`, `district_forecast.py`); the state-level model, `/api/predict` and the Prediction page are retired. What is served is the mean of the last three published seasons with a tested 80% range (63 crops, 38,429 series, 751 districts), because no model beat that mean by the pre-registered bar once the test respected the publication lag (see "One table, one model", Amendments A1 and A2). Still to do: ship and verify on Cloud Run/Vercel (the live site still serves the earlier version and its optimistic figures), then the items below.
- [ ] B2B endpoint: `GET /v1/forecast?district=&crop=&season=` with intervals and P(yield < threshold); API keys and rate limits.
- [ ] Alerts: email/WhatsApp when a district's forecast drops below a threshold.
- [ ] Hindi plus 1–2 regional languages; browser voice input before any chatbot.
- [ ] Reframe the what-if sliders as "compare with regional baseline" only if validated; otherwise remove.

### Phase 5 — Production engineering

- [ ] CI (GitHub Actions): `test_model.py`, API tests, frontend lint + `check-constants.mjs`, container build. Not started. Note that a clean CI checkout will not contain the gitignored models and processed data the district endpoints need; this is the model-registry/DVC item below.
- [ ] Model registry and tracking (MLflow) plus DVC for data/models; stop committing 17–35 MB pickles.
- [ ] Model card + data card in the repo and linked in the UI.
- [ ] Drift monitoring on inputs (Evidently-style KS/JS tests), logged predictions, scheduled retrain.
- [~] Deployed and verified live 2026-10-12 (commit `f6dc55e`, Cloud Run revision `agripredict-api-00014-5bc`, Vercel; see ENGINEERING_NOTES §16.3). Local container test first (`deploy/stage_build.py`, memory 213 MiB with the 5 MB models). Still to do: move serving to `asia-south1` (live latency from here is 0.5–2 s per call in `europe-west1`), a health endpoint, request logging.
- [ ] Prefer a portable model format (ONNX or native LightGBM) over pickle for serving.

### Phase 6 — Credibility

- [ ] **Publish the India benchmark**: splits, baselines, leaderboard script, CY-Bench-style. This is the item that makes the project stand out.
- [ ] Back-test against official FASAL/DES estimates where public.
- [ ] Write it up (short paper/preprint or blog) with the negative result: a state-level model with weather and soil does not beat a 3-year mean.

---

## 7. What not to do

- A deep-learning model on the current state-level table (no signal to learn; reviews warn of this).
- A general LLM chatbot "for farmers": Farmer.Chat already exists with Bhashini speech and partner distribution.
- More engineered features: the ablation already shows < 1% effect for most groups.
- A mobile app before the forecast is better than a baseline.
- Quoting R² without a baseline anywhere in the UI or README.

---

## 8. Reproducing the measurements

Scripts were run from the repo root against `master_dataset_enhanced.csv` (scratch copies were kept outside the repo). Baselines use only train-year information, except last-year persistence, which uses the prior year's actual as it would be known in deployment. Lag features were recomputed per state × crop × season. Gradient boosting runs were single-seed and untuned.

If you want these under `tests/` or in `train_v3.py`, that is Phase 0, item 1.

---

## 9. Sources and confidence

**Solid (peer-reviewed or primary documentation)**
- [CY-Bench, ESSD 2026](https://essd.copernicus.org/articles/18/3997/2026/) · [repo](https://github.com/BigDataWUR/AgML-CY-Bench)
- [Coupling ML and crop modeling, US Corn Belt](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7810832/) · [Forecasting corn yield with ML ensembles](https://arxiv.org/pdf/2001.09055)
- [Foundation-model embeddings, leave-one-country-out (also source for the CV inflation numbers)](https://arxiv.org/pdf/2605.08113)
- [FARM / CYPRESS: fine-tuning Prithvi-EO for yield](https://arxiv.org/pdf/2510.26609)
- [Google Agricultural Landscape Understanding API](https://developers.google.com/agricultural-understanding/api)
- [CropNet dataset (US county-level, KDD 2024)](https://huggingface.co/datasets/CropNet/CropNet)
- [Wheat yield, deep LSTM, tehsil level, India](https://ar5iv.labs.arxiv.org/html/2011.01498) · [ICRISAT/MNCFC GP-level pilot report](https://oar.icrisat.org/12147/1/MNCFC_GP-Croplevel_Yield%20assessment_Report_Rabi_2020_21.pdf)
- [SoilGrids](https://www.isric.org/explore/soilgrids) · [NASA POWER client docs](https://pynasapower.readthedocs.io/)
- [TCI–ICRISAT district database](https://pressroom.icrisat.org/tci-and-icrisat-continue-partnership-to-improve-access-to-indian-food-systems-data)

**Use with care (vendor, secondary, or design not verified)**
- SatSure: [AWS Marketplace listing](https://aws.amazon.com/marketplace/pp/prodview-f53uqvekg2bai) — vendor claims.
- Farmonaut: third-party profile sites only.
- Cropin PMFBY: [vendor case study](https://www.cropin.com/project/cropin-reduces-time-and-cost-of-crop-cutting-experiments-for-pmfby-government-of-india-with-its-agtech-stack). Nothing reliable found on the private company Fasal.
- DGCES "23 states, Aug 2026": [one UPSC explainer](https://plutusias.com/?p=236519); confirm with Ministry of Agriculture releases.
- Farmer.Chat: [Digital Green FY25 annual report](https://digitalgreen.org/wp-content/uploads/2025/07/Digital-Green-FY25-Annual-Report.pdf) — self-reported; the 100× cost claim is a projection.
- Conformal yield intervals: [AgroX-MoE](https://journals.iub.edu.pk/index.php/JCIS/article/view/4398) single paper; [group-conditional CP](https://arxiv.org/pdf/2308.15094) is classification, not yield.
- TabPFN study and the 2026 IIETA 17-model benchmark: read abstracts only.
- Kisan Suvidha user count is a ~2016–17 government figure.
- ERA5-Land and Open-Meteo: not verified from official docs.

---

## 10. Addendum (2026-10-11): users, ecosystem and demand

Second research pass on who actually uses this, what India's ecosystem already offers, and where demand is. Searches were run with a US-only search tool; many sources are secondary. Confidence is marked per item.

### 10.1 A yield forecast alone is not what a farmer acts on

- **Decisions tied to action work.** The UChicago/Google monsoon-onset programme sent SMS forecasts to ~38M farmers in Kharif 2025 (with the Ministry of Agriculture). One secondary summary says 31–52% of surveyed farmers changed sowing or land preparation. *Not verified against an official source.*
- **Adoption is not outcome.** Cole & Fernando (Avaaj Otalo, voice advisory, 1,200 cotton farmers in Gujarat): farmers trusted the service and adopted recommended inputs, but the paper finds no systematic gain in yield or profit. *Peer-reviewed.* Wording of the Economic Journal version not checked.
- **Channel beats app.** Meghdoot (IMD/IITM/ICAR) has ~4.16 lakh cumulative registrations by Nov 2025 (not active users). The same advisories also go out via ~16,140 WhatsApp groups (~1.2 lakh villages), SMS and Kisan Suvidha. *Government sources.*
- **Funding.** Indian agritech raised $202M in 2025 vs $269M in 2024 (about -25%). The source also argues that products built on AgriStack and sold to governments, enterprises and lenders beat standalone paid advisory apps. *Weak source (dev-agency blog, quoting Inc42).*
- **Forecast value for smallholders is mixed.** Senegal (practice changes in ~75% of cases) and Benin (SMS forecasts, higher yield and income) are small trials; Zimbabwe is simulation-only and gains appear mainly in drought years. Value depends on year, region and what the farmer can change.

**Implication:** primary users are insurers, lenders, FPOs, extension officers and state agriculture departments. Farmers are reached through intermediaries and existing channels (WhatsApp, SMS, IVR), not a standalone slider app.

### 10.2 PMFBY / YES-TECH: the clearest demand signal

- PMFBY compensates every farmer in an insurance unit when actual yield (from crop-cutting experiments, CCEs) falls below the threshold yield.
- **YES-TECH** (DA&FW, 2023) replaces or blends CCEs with satellite + weather + analytical models. Five models are prescribed for paddy and wheat. The accepted blend is reported as 70:30 (CCE : technology), with a minimum 30% technology weight; Madhya Pradesh gives it 100%.
- Reported accuracy is 75–95% for paddy and wheat (HARSAC presentation, vendor/agency material). **The committee's exact accuracy threshold was not found.**
- Trust is the open problem: soybean farmers in MP report lower payouts after adoption (insurers say past CCE data was manipulated); Haryana MPs raised a ~Rs 300 crore cotton dispute (the ministry says cotton is not under YES-TECH). CSE says tech estimates need independent assessment.
- Continuation approval ran to FY 2025-26; **whether weights and terms continue beyond that was not confirmed.**

**Implication:** an open, reproducible, baseline-aware benchmark and audit of technology-based yield estimates is a real gap. This strengthens wedge B in §5.

### 10.3 Closest existing work

| Item | What it is | Note |
|---|---|---|
| De Clercq & Mahdi 2024, [arXiv 2403.07967](https://arxiv.org/abs/2403.07967) | 247 districts, 20 years, Kharif rice, climate reanalysis + satellite LAI, 19 models, R² up to 0.82; proof-of-concept dashboard of districts expected to rise or fall vs last year | Baseline comparison is vague; code link not confirmed; CC BY-NC-ND. Template for the district map, beatable with proper baselines |
| Krishi-DSS (Aug 2024) | Geospatial platform from Ministry of Agriculture + Dept of Space (weather, soil, crop health, reservoirs, crop mapping) | Planner-facing data, not a yield-forecast API. Open data download not documented |
| Mobile Mandi (Imperial College) | Daily retail prices, 22 commodities, 157 markets, LSTM next-day forecast vs persistence baseline, low-literacy UI, WhatsApp | Same lesson as §1: compare to persistence |
| Agmarknet price forecasting (arXiv 1812.05173) | 1,000+ markets, collaborative filtering, nearest-neighbour uncertainty, mobile web | Academic prototype |
| Kisan e-Mitra (Wadhwani AI, Bhashini) | PM-KISAN grievance chatbot, 11 languages, 49 query categories, 3M+ grievances for 290k+ farmers (Mar–Aug 2024) | Self-reported, not independently audited. No independent impact evaluation found for it or any Bhashini agriculture chatbot |
| Farmer.Chat (Digital Green) | GenAI advisory; reported growth from 15k to 250k India users in under a year, 40% women | Secondary source; already integrates partners. Treat as a channel to plug into |

### 10.4 Data risks found

- **DES APY** (`data.desagri.gov.in`) is the official district source after 2017. A mirror lists coverage 1997–2023 (last updated Dec 2023) but notes ~<50% coverage for 2020 and ~3% for 2021 at source. **Current completeness is unconfirmed.** Count rows per year before committing to the district plan.
- **AgriStack**: 10.31 crore Farmer IDs (Aug 2026 Rajya Sabha reply, via BioVoice); Digital Crop Survey covered 31.3 crore plots across 648 districts in Rabi 2025-26 (secondary; figures differ between sources). **No public developer API or onboarding was found.** Do not depend on it. The RBI Unified Lending Interface is the documented integration route for lenders.
- **IMD forecasts** (block-level, ~6,970 blocks, 5-day, updated Tue/Fri) are usable inputs, but licence and access terms were not checked.
- **Privacy**: DPDP Act obligations were not researched. Needed before collecting any farmer-level data.

### 10.5 Additions to the roadmap

**Credibility**
- [ ] Back-test the forecasts against whatever official district yields or CCE-derived numbers are public, and publish the gap per crop and state (YES-TECH-style audit).
- [ ] Show, next to every forecast: baseline, calibrated interval, "unreliable here" flag, and the data's last-updated date.

**Users**
- [ ] Insurer / state analyst view: district map, forecast vs threshold, P(yield < threshold), CSV/PDF export.
- [ ] Extension officer / FPO alerts over WhatsApp or SMS, Hindi plus 1–2 regional languages; voice input before any chatbot.
- [ ] Forecast API that existing chatbots (Farmer.Chat, Kisan e-Mitra) can call as a tool. Build the service, not another chatbot.
- [ ] Action-linked advice (sowing window, irrigation, sell vs hold) driven by weather feeds and mandi prices (Agmarknet, 3,000+ mandis, 1–2 day lag). Treat mandi prices as a separate, later module; sources on it were thin.
- [ ] Low-bandwidth PWA.

**Validation**
- [ ] Interview 5–10 real users (FPO, KVK/extension officer, insurer analyst) before building the user views above.
- [ ] If a farmer-facing pilot happens, measure an outcome (sowing change, loss avoided), not just usage.

### 10.6 Not verified in this pass

YES-TECH committee accuracy threshold · AgriStack/Krishi-DSS public API · DES APY completeness for 2018–2023 · DPDP obligations · SatSure, Cropin and Fasal user numbers (vendor claims only) · Krishi Saathi and Kisan Sarathi (no usable results).

### 10.7 Sources (addendum)

- [MoES/PIB: Meghdoot usage](https://moes.gov.in/sites/default/files/PIB2202382.pdf) · [IMD press release, Aug 2022](https://internal.imd.gov.in/press_release/20220824_pr_1790.pdf) · [MoES 2025 reply](https://www.moes.gov.in/sites/default/files/2253English.pdf)
- [AgriStack Farmer IDs](https://biovoicenews.com/india-10-31-crore-farmer-ids-agristack/) · [ICRISAT AgriStack overview](https://issca.icrisat.org/scalable-solutions/digital-public-infrastructure-for-agriculture-agristack)
- [Down To Earth: YES-TECH](https://www.downtoearth.org.in/amp/story/agriculture/can-technology-make-indias-crop-insurance-payouts-more-accurate) · [HARSAC YES-TECH slides](https://hsac.org.in/harsac/Upload/GeoSpatial%20Technology%20for%20Crop%20yield%20Estimation%20(YES-TECH)_20260219153429063.pdf) · [CSE report](https://www.cseindia.org/content/downloadreports/13110)
- [UChicago monsoon SMS programme](https://humancenteredforecasts.climate.uchicago.edu/news/ai-based-monsoon-forecasts-help-38-million-indian-farmers-make-planting-decisions/) · [Google blog](https://blog.google/technology/research/indian-farmers-monsoon-prediction/)
- [Cole & Fernando, Avaaj Otalo](https://www.atai-research.org/wp-content/uploads/2018/04/20190699_accepted.pdf)
- [De Clercq & Mahdi, district rice yield](https://arxiv.org/abs/2403.07967)
- [Mobile Mandi](https://www.doc.ic.ac.uk/~axgopala/papers/ictd22-abs.html) · [Agmarknet price forecasting](https://arxiv.org/pdf/1812.05173)
- [Kisan e-Mitra / Wadhwani AI](https://www.wadhwaniai.org/empowering-millions-of-indian-farmers-with-instant-ai-chatbot-support/)
- [DES APY mirror](https://ckandev.indiadataportal.com/dataset/area-production-yield-apy)
- [Agritech funding analysis](https://ecorpit.com/ecorpit-agritech-farm-app-development-service-india-2026/) · [Farmer.Chat profile](https://www.briter.co/companies/farmer-chat-by-digital-green)
- Smallholder forecast-value studies (Senegal, Zimbabwe, Benin, Ethiopia): found via search summaries only; primary papers not opened.

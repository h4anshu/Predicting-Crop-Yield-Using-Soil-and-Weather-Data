# AgriPredict AI — Engineering Notes

A record of the backend work: what was changed, what was found, and why each decision
was made. Written so that someone who did not do the work can evaluate the reasoning,
reproduce the numbers, and understand what the system cannot do.

Every figure quoted here was measured on this repository. Commands to reproduce them
are given at the end.

---

## Table of contents

1. [Starting point](#1-starting-point)
2. [The dropdown delay](#2-the-dropdown-delay)
3. [Investigating the model](#3-investigating-the-model)
4. [A correction to an earlier claim](#4-a-correction-to-an-earlier-claim)
5. [What we decided to change, and why](#5-what-we-decided-to-change-and-why)
6. [`train_v3.py` — the retrain](#6-train_v3py--the-retrain)
7. [`features.py` — one place for derived features](#7-featurespy--one-place-for-derived-features)
8. [`api.py` — the serving layer](#8-apipy--the-serving-layer)
9. [`test_model.py` — what we guard](#9-test_modelpy--what-we-guard)
10. [Bugs found and fixed](#10-bugs-found-and-fixed)
11. [Results](#11-results)
12. [Known limitations](#12-known-limitations)
13. [File manifest](#13-file-manifest)
14. [Reproducing everything](#14-reproducing-everything)

---

## 1. Starting point

The system had three parts:

| Part | Stack | Hosting |
|---|---|---|
| Model | scikit-learn `ExtraTreesRegressor` in a `Pipeline` | 35 MB pickle in the repo |
| API | FastAPI (`api.py`) | Google Cloud Run, `europe-west1` |
| Frontend | React + Vite + Recharts | Vercel |

The model reported **R² 0.9506**, trained on 19,689 records covering 55 crops and 30
states from 1997–2020. There was also a Streamlit app (`app.py`) predating the React
frontend, and a folder of research artifacts in `extra/` — a baseline sweep, a feature
ablation, and significance tests — that nothing in the running product referenced.

---

## 2. The dropdown delay

**Symptom.** On the live site, the State / Crop / Season dropdowns rendered empty and
filled in a few seconds later.

**Cause.** The options came from a network call. `App.jsx` initialised its state to
`null`, and the `<select>` elements rendered `options?.states?.map(...)`, so until the
fetch resolved each dropdown contained **zero `<option>` elements**.

Two things made that wait long:

1. **Cold start.** Cloud Run scales to zero. `api.py` called `joblib.load()` on the
   35 MB model at *module import*, measured locally at **3.5 s**, and nothing served
   until it finished — including `/api/options`, which only needs the CSV.
2. **Distance.** The service is in `europe-west1`; users are in India. Measured
   round-trip when warm: **~450 ms**.

**Fix.** The option lists are static — 30 states, 54 crops, 6 seasons, a fixed year
range, all derived from a CSV that does not change between retrains. There was no
reason to ask the network for them. They are now bundled in
`frontend/src/constants.js` and used as the initial state, with the fetch still
running in the background to overwrite them after a retrain.

Two details that matter:

- The background fetch is **guarded** (`if (d?.states?.length)`). Without that, a
  cold-start error page returning `{}` would blank out working dropdowns.
- `check-constants.mjs` fails the build-time check if the bundled seed drifts from the
  live API, so the copy cannot silently go stale.

**Verified** by pointing `API_BASE` at an unreachable host, rebuilding, and loading the
page: all dropdowns rendered fully populated (30 / 29 / 55 / 6) with the backend
completely down.

This also motivated a backend change — see [lazy model loading](#82-lazy-model-loading).

---

## 3. Investigating the model

Before building the remaining pages, the model itself was examined. Three findings.

### 3.1 The dataset has no within-region variation

This is the root fact that explains everything else.

Grouping the training data by `(state, year)`:

| Column | Distinct values inside one state-year |
|---|---|
| `total_rainfall_mm` | 1 |
| `avg_temp_c` | 1 |
| `avg_humidity_percent` | 1 |
| `N`, `P`, `K`, `pH` | 1 each |

Concretely — **Punjab, 2015**: 16 crop records. All 16 carry `rainfall = 1130.12` and
`N = 150`. Their actual yields range from **0.35 to 77.09 t/ha**.

Inside that cell, rainfall and N have *zero* power to explain why one crop yielded 0.35
and another 77. Only `crop` explains it. `data/state_soil_data.csv` has **one row per
state** with no year column, so only 30 distinct soil profiles exist across all 19,689
records.

A tree-based model splitting on `state` rather than on rainfall is doing the
statistically correct thing. The signal is genuinely not in the data.

### 3.2 The headline R² was inflated by one preprocessing artifact

`master_dataset_enhanced.csv` winsorises yield at **104.2733866960**. 197 rows sit
exactly on that cap:

| Crop | Rows at cap |
|---|---|
| Coconut | 164 |
| Sugarcane | 23 |
| Onion | 3 |
| Potato | 3 |
| Banana | 2 |
| Maize | 1 |
| Cashewnut | 1 |

Coconut is the problem. Indian government records count **individual nuts per
hectare**, not tonnes — raw max in `data/crop_yield.csv` is **21,105**. Those values
were dropped into a tonnes/ha column and then clipped, collapsing **164 of Coconut's
172 rows** to one identical number.

The consequence: v2 scored a **test MAE of exactly 0.000** on Coconut. That is not
accuracy, it is memorising a constant. And `crop_Coconut` alone carried **38%** of the
model's total feature importance, with `crop_Sugarcane` another **33%** — 71% of the
model's attention on two crops that are 3.9% of the rows.

Removing just those two crops from the test set — 3.2% of rows — moved the score:

> **R² 0.9506 → 0.8186**

The v2 figure of 0.9506 was reproduced exactly before drawing this conclusion, so the
pipeline under test was the one being shipped.

### 3.3 Sensitivity to user-editable inputs was uneven

A model can score well while ignoring the inputs a user can actually change. Measured
by sweeping each input across its realistic range and recording how far the forecast
moved (median over 200 held-out staple rows, derived features rebuilt each time):

| Input | v2 median move |
|---|---|
| pH | **1.13%** |
| temperature | 2.43% |
| rainfall | 2.77% |
| K | 16.12% |
| N | 32.71% |
| P | 43.39% |

N and P worked. **pH and temperature were effectively inert** — a pH slider moving the
forecast by 1% is decorative.

---

## 4. A correction to an earlier claim

An earlier version of this analysis stated that *"a tenfold rainfall change moves the
forecast by 0.2%"* and that the soil and climate controls were entirely decorative.
**That was overstated, and the measurement behind it was wrong.**

Two methodology errors:

1. **Measured on a single row.** One row is far too noisy to characterise a 200-tree
   ensemble; an unlucky row can make a responsive model look dead.
2. **Derived features were not rebuilt.** Rainfall also feeds `moisture_index`,
   `temp_rainfall_interaction` and `fertilizer_rainfall_ratio`. Perturbing only the raw
   column left the model reading three stale copies of the old value, which suppressed
   its apparent response.

The corrected method — many rows, median, derived features rebuilt through
`features.py` — produced the v2 table in §3.3. The direction of the work was right; the
severity quoted was not. Findings §3.1 and §3.2 were measured correctly and stand.

This is recorded here rather than quietly fixed because the fix changed a number that
was used to justify a decision.

---

## 5. What we decided to change, and why

### 5.1 Drop `state` from the feature set

If `state` is unavailable, the model still has to know *where* it is, and the only
remaining location signal is the soil/climate vector — which is effectively a state
fingerprint. So it is forced to use those columns.

Measured on identical data and hyperparameters (2018–2020 holdout):

| Config | R² | R² excl. Coconut+Sugarcane | MAE | rainfall response |
|---|---|---|---|---|
| **A.** current (crop+season+state) | 0.9496 | 0.8129 | 0.997 | 0.2%\* |
| **B.** no `state` | 0.9444 | 0.7913 | 1.023 | 3.0%\* |
| **C.** no `state`, no Coconut/Sugarcane | 0.8014 | 0.8014 | **0.868** | 4.5%\* |
| **D.** no `state`, no `crop` | 0.3913 | 0.3913 | 2.375 | 1.6%\* |

\* *single-row measurements from the first pass; superseded by the corrected
methodology in §4. The R² and MAE columns are unaffected.*

Reading B against A: accuracy barely moves (0.9496 → 0.9444) while responsiveness
rises across the board. **Roughly half a point of R² buys a model that responds to its
inputs.** Row D is the control — stripping `crop` too collapses the model to 0.39,
confirming `crop` carries the real signal, which is expected.

### 5.2 Exclude Coconut, but keep Sugarcane

The initially agreed option was to drop both. **We kept Sugarcane**, and this deviation
is deliberate:

- **Coconut is a data error.** nuts/ha inside a tonnes/ha column. It does not belong in
  a model that predicts tonnes per hectare, at any accuracy level.
- **Sugarcane is real agronomy.** It genuinely yields ~51 t/ha. It is a major Indian
  crop. Dropping it would remove it from the product entirely — a functional regression
  that was not asked for, to make a number look different.

Measured both ways:

| Config | n (test) | R² | MAE |
|---|---|---|---|
| excl. Coconut only (**shipped**) | 2162 | 0.9212 | 1.0014 |
| excl. Coconut + Sugarcane | 2109 | 0.8014 | 0.868 |

The gap is not an artifact: Sugarcane's large range adds genuinely explainable
variance. Rather than pick one number, **both are reported** — `headline` and
`core_staples` — and the UI leads with the lower one.

### 5.3 Report the conservative number first

The Model Performance page opens by explaining why two figures exist and shows the
0.9212 → 0.8053 drop. This is a deliberate credibility decision: a technical evaluator
who discovers the Coconut artifact themselves stops trusting every other number on the
page. Finding it first, and documenting it, reads as engineering maturity instead.

---

## 6. `train_v3.py` — the retrain

One script, reproducible, emitting both the model and every number the UI renders.

### 6.1 Pipeline

Structurally identical to v2 so the comparison is fair — only the feature set changed.

```
ColumnTransformer
  num (25 cols) -> SimpleImputer(median)        -> StandardScaler
  cat (2 cols)  -> SimpleImputer(most_frequent) -> OneHotEncoder(handle_unknown='ignore')
ExtraTreesRegressor(n_estimators=200, max_depth=20,
                    min_samples_split=5, min_samples_leaf=2, random_state=42)
```

27 features total: 25 numeric, plus `crop` and `season`. `state` removed.

### 6.2 Validation strategy

**Temporal holdout: train < 2018, test 2018–2020.** Chosen over a random split because
the production task is forecasting a future season. A random split would leak
neighbouring years of the same state-crop series into training and inflate the score.

The **shipped** `.pkl` is then refit on all years, which is standard practice — no
reason to discard three years of recent data in production. This creates an obvious
trap, so `model_metrics.json` carries an explicit `note`:

> *Reported metrics come from the holdout fit. The shipped .pkl is refit on all years
> for production use; it is never evaluated on data it has seen.*

A 5-fold CV MAE is also reported (**0.856 ± 0.021**). The tight spread matters more
than the value — it shows the score is not an artifact of one lucky split.

### 6.3 Sensitivity measurement

Given §4, this is done carefully:

- **Many rows, median.** 200 held-out staple rows, not one.
- **Derived features rebuilt** through `features.add_derived()` for every perturbation.
- **p25 / p75 recorded** alongside the median, because the distribution is wide.
- **v2 measured on the same rows** so the before/after is like-for-like.

### 6.4 Grouped feature importance

One-hot columns are summed back into their source feature. Without this, `crop` appears
as 50+ individually weak columns instead of one dominant signal, which misrepresents
what drives a prediction. After grouping, `crop` is **0.695** — the model is
overwhelmingly crop-driven, and saying so plainly is more useful than hiding it behind
a long tail.

### 6.5 Detecting the clip cap

The cap is **derived from the data**, not hardcoded:

```python
clip_value = float(d['yield'].max())
at_cap = d['yield'] >= clip_value - 1e-6
```

An earlier version hardcoded the rounded literal `104.2734`. That literal is
numerically **above** the true cap `104.2733866960`, so `>= 104.2734` matched **zero
rows** and the artifact silently vanished from the report — the page rendered
"0 rows clipped" with an empty list. Deriving it from the data removes the failure mode.

### 6.6 Outputs

- `crop_yield_model_v3.pkl` — **16.8 MB** vs v2's 35 MB (`compress=3`), which also
  roughly halves the cold start.
- `model_metrics.json` — headline and core scores, CV, sensitivity for v3 and v2,
  grouped importance, per-crop error (53 crops), per-state error (30 states), 1,200
  scatter points, and the full `data_quality` block.

---

## 7. `features.py` — one place for derived features

The model consumes 12 engineered columns that are functions of the raw inputs. Before
this module, that arithmetic was written out **twice** — once inline in `api.py`, once
in the training code — with no guarantee they agreed.

Two reasons this is now one module:

1. **Correctness.** A caller that sets a raw input without recomputing its derived
   children leaves the model reading stale values, silently suppressing its response to
   that input. This is exactly the bug that corrupted the first sensitivity measurement
   (§4). Every path — prediction, evaluation, tests — now goes through
   `add_derived()`.
2. **Label normalisation.** See §10.1.

`add_derived()` is vectorised, so the same function serves a single prediction and a
200-row evaluation sweep.

---

## 8. `api.py` — the serving layer

### 8.1 Model version

Points at `crop_yield_model_v3.pkl`, falling back to the v2 pickle if the new file is
absent — so a deploy that ships code before the model artifact degrades rather than
crashes.

### 8.2 Lazy model loading

The model now loads **on first prediction**, not at import:

```python
_model = None

def get_model():
    global _model
    if _model is None:
        path = MODEL_PATH if os.path.exists(MODEL_PATH) else LEGACY_MODEL_PATH
        _model = joblib.load(path)
    return _model
```

Cloud Run scales to zero, so an import-time unpickle put the full model-load cost in
front of *every* cold request — including `/api/options` and `/api/stats`, which only
need the CSV. Those endpoints no longer wait on it.

### 8.3 Prediction intervals replace a fabricated confidence score

The old response contained a hardcoded `"confidence": 94`. It was not computed from
anything.

`predict_with_interval()` now takes the per-tree predictions from the 200 estimators
and reports the 5th–95th percentile of their spread.

**This is labelled honestly.** It is a *model-agreement* interval, not a calibrated
prediction interval: it shows where ensemble members disagree, and it **understates**
true predictive uncertainty because it cannot see error the whole forest shares. Both
the API response and the UI say so. A single invented 0–100 "confidence" number was
also dropped in favour of reporting the relative interval width directly.

Example — Punjab wheat: `4.69 t/ha, interval 4.08–4.99, spread 19.4%`.

### 8.4 State defaults — closing a hole the retrain opened

Dropping `state` from the model had a consequence that would have made things worse,
not better: **the State dropdown would do nothing at all.** Verified directly — Punjab,
Kerala and Bihar all returned `1.060` for identical soil/climate inputs.

Trading a near-dead pH slider for a completely dead State dropdown is not an
improvement. So `/api/options` now ships `state_defaults`: per-state soil and
latest-year climate, letting the frontend fill the form when a state is picked. A
companion `/api/state-climate?state=&year=` serves one state-year so the form tracks
the year control too.

The result is agronomically credible and state-differentiated:

| State | N | pH | rainfall | Wheat forecast | interval |
|---|---|---|---|---|---|
| Punjab | 150 | 8.0 | 1139 mm | **4.68 t/ha** | 4.08–4.99 |
| Bihar | 85 | 7.2 | 922 mm | 2.56 t/ha | 1.45–4.35 |
| Kerala | 65 | 5.7 | 1778 mm | 1.51 t/ha | 1.22–1.82 |
| Karnataka | 72 | 6.9 | 818 mm | 1.23 t/ha | 0.81–2.30 |

Punjab wheat at ~4.7 t/ha matches the real-world figure. Note also that the intervals
are informative: Punjab is tight, Bihar wide — the model is genuinely less certain there.

### 8.5 New endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/model-metrics` | Everything the Model Performance page renders |
| `GET /api/research` | Baseline sweep, ablation, model comparison from `extra/` |
| `GET /api/soil-climate` | Per-state soil profiles + full weather series, with granularity caveats |
| `GET /api/state-climate` | One state-year's observed climate, for form autofill |

`/api/trends` and `/api/crop-insights/{crop}` **already existed** and were never called
by the frontend. They now back the Historical Trends and Crop Insights pages — no new
backend work needed for either.

`/api/soil-climate` deliberately returns a `granularity` block describing the
one-profile-per-state limitation, so the constraint travels with the data instead of
living only in a comment.

### 8.6 Corrected reporting

`/api/options` now returns **stripped** labels (see §10.1) and excludes Coconut, so the
UI cannot offer a crop the model does not support. `/api/stats` reports the real,
current numbers — `model_accuracy`, `model_accuracy_core`, `model_mae` — instead of a
hardcoded `"95%"` string.

---

## 9. `test_model.py` — what we guard

Accuracy alone would never have caught v2's inert pH control, so **responsiveness is
asserted directly**:

1. `state` must not reappear in the feature set.
2. Coconut must remain excluded.
3. Predictions must be numerically plausible.
4. **Each input must move the forecast by at least a floor percentage.** Floors sit
   well below measured medians so ordinary retraining noise will not trip them, while a
   slide back toward v2's 1.13% pH response fails loudly.
5. `model_metrics.json` must carry the honest breakdown — `core_staples.r2` must be
   *lower* than `headline.r2`, and the limitations text must be present.

The test uses the same methodology as the training script: many rows, median,
derived features rebuilt.

---

## 10. Bugs found and fixed

### 10.1 Silent label mismatch (correctness)

The source CSV pads its category labels — `'Rabi       '`, `'Coconut '` — while v3
trains on the stripped forms. An unstripped label **does not raise**:
`OneHotEncoder(handle_unknown='ignore')` encodes it as all zeros, silently dropping the
category from the prediction with no error anywhere in the stack.

The frontend was sending the padded form. Fixed in `features.py`, the one choke point
every prediction passes through — rather than at each call site, where the next caller
would reintroduce it.

### 10.2 Fabricated confidence score

`"confidence": 94`, hardcoded. Replaced with the real ensemble interval (§8.3).

### 10.3 State dropdown made inert by the retrain

Caught by testing the consequence rather than assuming it. Fixed via `state_defaults`
(§8.4).

### 10.4 Clip detection matching zero rows

A rounded float literal compared with `>=`. Fixed by deriving the cap (§6.5).

### 10.5 Stale hardcoded accuracy in three places

`"95%"` in `/api/stats`, in the Dashboard KPI card, and in the sidebar; the About page
still quoted `Test R²: 0.9506` and `55 crops`. All now read live values, so the pages
cannot contradict each other.

---

## 11. Results

### Accuracy (2018–2020 temporal holdout)

| Metric | Value |
|---|---|
| R² — all crops | **0.9212** |
| R² — core staples (excl. Sugarcane) | **0.8053** |
| MAE — all crops | 1.0014 t/ha |
| MAE — core staples | 0.8871 t/ha |
| RMSE | 3.3525 |
| 5-fold CV MAE | 0.856 ± 0.021 |
| Test records | 2,162 |
| Training records | 17,355 (19,517 for the shipped refit) |

### Input responsiveness — v2 vs v3

Median move over 200 held-out staple rows, derived features rebuilt:

| Input | v2 | v3 | Change |
|---|---|---|---|
| **pH** | 1.13% | **6.35%** | **5.6×** |
| K | 16.12% | 26.98% | 1.7× |
| temperature | 2.43% | 4.71% | 1.9× |
| rainfall | 2.77% | 5.24% | 1.9× |
| P | 43.39% | 59.22% | 1.4× |
| N | 32.71% | 33.78% | 1.0× |

Every input improved. pH went from effectively inert to genuinely responsive.

### Where the model works

Best and worst per-crop MAE on the holdout:

| | Crop | n | MAE | mean actual |
|---|---|---|---|---|
| Worst | Onion | 55 | 5.771 | 15.587 |
| | Sugarcane | 53 | 5.550 | 58.677 |
| | Banana | 23 | 5.191 | 37.970 |
| Best | Masoor | 37 | 0.158 | 0.831 |
| | Khesari | 8 | 0.170 | 0.718 |

Absolute error tracks magnitude, so mean actual yield is reported alongside — Sugarcane's
5.55 on a mean of 58.7 is ~9% relative error, better than Onion's 5.77 on 15.6 (~37%).

### Other outcomes

- Model artifact **35 MB → 16.8 MB**, halving cold-start unpickle time.
- `/api/options` and `/api/stats` no longer block on model loading at all.
- Dropdowns render on first paint even with the backend fully down.

---

## 12. Known limitations

**State these before anyone else finds them.**

### 12.1 Response is regional, not field-level

This is the important one. Because soil is one profile per state and weather is one
observation per state-year (§3.1), the model learns *"regions averaging 1100 mm with
N=150 tend to yield X for wheat"* — a regional climate effect, **not** "your field with
this much rain will yield this."

Adjusting soil inputs explores how a field differing from its regional baseline might
perform. It is useful for comparison. It is **not** a substitute for a soil test.

Closing this gap requires district-level soil and weather records. It is a **data
acquisition problem, not a modelling one** — no algorithm change on the current CSV
produces field-level response.

### 12.2 Ensemble intervals understate uncertainty

The reported interval is tree disagreement. It cannot capture error shared by the whole
forest, so true predictive uncertainty is wider. Labelled as such everywhere it appears.

### 12.3 The ablation does not justify most engineered features

From `extra/ablation_study_results.csv`: only the input-efficiency group produced a
material gain (**~8.4%** MAE reduction). The NPK-ratio, climate and soil-quality groups
moved MAE by **well under 1%** — within noise. They are retained because they cost
nothing at inference, **not** because the ablation proved them necessary. The Model
Performance page says this.

### 12.4 Coconut is unsupported

Excluded entirely. Its source data is unit-inconsistent and the clipping destroyed it.
Recovering it would mean rebuilding from `data/crop_yield.csv` with a separate
nuts/ha unit track — viable, but out of scope so far.

### 12.5 The research artifacts predate v3

The baseline sweep and ablation in `extra/` were produced with Coconut included and
`state` present. They justify the **algorithm choice**; they do not describe the
shipped model. The UI labels them accordingly.

### 12.6 Model accuracy is bounded by crop, not agronomy

Grouped importance puts `crop` at 0.695. The model is mostly learning per-crop yield
baselines. That is legitimate and useful, but it means the agronomic inputs refine a
crop-level prior rather than driving the forecast.

---

## 13. File manifest

### Added

| File | Purpose |
|---|---|
| `train_v3.py` | Retrains the model and emits all evaluation artifacts |
| `features.py` | Derived-feature construction and label normalisation |
| `test_model.py` | Contract tests, including direct responsiveness assertions |
| `model_metrics.json` | Generated; consumed by `/api/model-metrics` |
| `crop_yield_model_v3.pkl` | Generated; the shipped model (16.8 MB) |

### Modified

| File | Change |
|---|---|
| `api.py` | v3 model, lazy loading, intervals, 4 new endpoints, corrected stats |

### Retained

`crop_yield_model_v2_extra_trees.pkl` is kept — as the fallback in `get_model()`, as
the comparison baseline in `train_v3.py`, and as the evidence behind the before/after
table on the Model Performance page.

### Deployment note

`api.py` requires `model_metrics.json` at startup. Both it and the `.pkl` must be
committed and present in the container image, or the service will fail to boot.

---

## 14. Reproducing everything

Retrain and regenerate every metric (~30 s):

```bash
python train_v3.py
```

Verify the model contract, including that inputs still move the forecast:

```bash
python test_model.py
```

Confirm the bundled frontend seed data still matches the live API:

```bash
node frontend/check-constants.mjs
```

Check the within-state-year variation claim from §3.1 yourself:

```bash
python -c "import pandas as pd; d=pd.read_csv('master_dataset_enhanced.csv'); print(d.groupby(['state','year'])[['total_rainfall_mm','N','pH']].nunique().max())"
```

All three commands should be run after any change to the dataset or the model.

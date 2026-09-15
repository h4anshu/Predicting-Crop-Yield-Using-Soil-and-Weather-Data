"""
Derived-feature construction, in one place.

The model consumes 12 engineered columns that are functions of the raw field inputs
(rainfall drives moisture_index, temp_rainfall_interaction and fertilizer_rainfall_ratio;
N/P/K drive the ratio and balance columns). Any caller that sets a raw input without
recomputing these leaves the model reading stale derived values, which silently
suppresses its response to that input -- so prediction, evaluation and the sensitivity
tests all go through this module rather than rebuilding the formulas locally.
"""

import pandas as pd

# The raw inputs a caller supplies; everything else is derived from them.
RAW_INPUTS = [
    "N", "P", "K", "pH", "avg_temp_c", "total_rainfall_mm", "avg_humidity_percent",
    "fertilizer_per_ha", "pesticide_per_ha", "year", "season", "crop",
]

YEAR_ZERO = 1997  # dataset start; years_since_start is measured from here


def add_derived(df):
    """Recompute every engineered column from the raw inputs. Vectorised, so it
    serves both a single prediction and a full evaluation sweep."""
    df = df.copy()
    # The source CSV pads its category labels ('Rabi       ', 'Coconut '), and the
    # model is trained on the stripped forms. An unstripped label does not raise --
    # OneHotEncoder(handle_unknown='ignore') silently encodes it as all zeros, so the
    # category is dropped from the prediction with no error anywhere. Normalise here,
    # because every caller reaches the model through this function.
    for col in ("crop", "season", "state"):
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    df["NPK_total"] = df["N"] + df["P"] + df["K"]
    df["N_to_P_ratio"] = df["N"] / (df["P"] + 0.1)
    df["N_to_K_ratio"] = df["N"] / (df["K"] + 0.1)
    df["P_to_K_ratio"] = df["P"] / (df["K"] + 0.1)
    df["NPK_balance_score"] = (df["N"] / 3 - df["P"]).abs() + (df["N"] / 1.5 - df["K"]).abs()
    df["temp_rainfall_interaction"] = df["avg_temp_c"] * df["total_rainfall_mm"]
    df["temp_humidity_interaction"] = df["avg_temp_c"] * df["avg_humidity_percent"]
    df["moisture_index"] = df["total_rainfall_mm"] * df["avg_humidity_percent"] / 100
    df["growing_degree_days"] = (df["avg_temp_c"] - 10).clip(lower=0)
    df["pH_optimal"] = ((df["pH"] >= 6.0) & (df["pH"] <= 7.5)).astype(int)
    df["soil_fertility_score"] = df["NPK_total"] / 200 * 0.7 + df["pH_optimal"] * 0.3
    df["fertilizer_rainfall_ratio"] = df["fertilizer_per_ha"] / (df["total_rainfall_mm"] + 1)
    df["pesticide_efficiency"] = df["pesticide_per_ha"] / 10
    df["input_intensity"] = (df["fertilizer_per_ha"] / 500 + df["pesticide_per_ha"] / 20) / 2
    df["years_since_start"] = df["year"] - YEAR_ZERO
    return df


def build_row(payload, model_features):
    """One request dict -> a single-row frame ordered for the model."""
    return add_derived(pd.DataFrame([payload])).reindex(columns=model_features, fill_value=0)

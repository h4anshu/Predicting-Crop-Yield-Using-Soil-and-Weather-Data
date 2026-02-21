# main_pipeline.py
# Shared pipeline logic extracted from main notebook
# No logic modified — only structured for reuse


# ==============================
# IMPORTS
# ==============================

import pandas as pd
import numpy as np

from sklearn.ensemble import ExtraTreesRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.impute import SimpleImputer


# ==============================
# DATA LOADING
# ==============================

def load_data(path):
    df = pd.read_csv(path)
    return df


# ==============================
# TEMPORAL SPLIT
# ==============================

def temporal_split(df):
    train = df[df["year"] <= 2017]
    test = df[df["year"] >= 2018]
    return train, test


# ==============================
# FEATURE GROUP DEFINITIONS
# ==============================

def get_feature_groups():

    # Group 1: Base Features
    group1 = [
        "N", "P", "K", "pH",
        "avg_temp_c",
        "total_rainfall_mm",
        "avg_humidity_percent",
        "fertilizer_per_ha",
        "pesticide_per_ha",
        "NPK_total"
    ]

    # Group 2: NPK Ratios
    group2 = [
        "N_to_P_ratio",
        "N_to_K_ratio",
        "P_to_K_ratio",
        "NPK_balance_score"
    ]

    # Group 3: Climate Interactions
    group3 = [
        "temp_rainfall_interaction",
        "temp_humidity_interaction",
        "moisture_index",
        "growing_degree_days"
    ]

    # Group 4: Soil Quality
    group4 = [
        "pH_optimal",
        "soil_fertility_score"
    ]

    # Group 5: Input Efficiency
    group5 = [
        "fertilizer_rainfall_ratio",
        "pesticide_efficiency",
        "input_intensity"
    ]

    return group1, group2, group3, group4, group5


# ==============================
# FINAL MODEL CONFIGURATION
# ==============================

def get_final_model():

    model = ExtraTreesRegressor(
        n_estimators=100,
        max_depth=15,
        random_state=42
    )

    return model


# ==============================
# EVALUATION METRICS
# ==============================

def evaluate_model(model, X_test, y_test):

    preds = model.predict(X_test)

    mae = mean_absolute_error(y_test, preds)
    rmse = np.sqrt(mean_squared_error(y_test, preds))
    r2 = r2_score(y_test, preds)

    return mae, rmse, r2

# ==============================
# PIPELINE BUILDER
# ==============================




# ==============================
# PIPELINE BUILDER
# ==============================

from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.impute import SimpleImputer


def build_pipeline(feature_list, model=None):

    if model is None:
        model = get_final_model()

    def _create_preprocessor(X):
        num_cols = X.select_dtypes(
            include=['int64','float64']
        ).columns.tolist()

        cat_cols = X.select_dtypes(
            include=['object']
        ).columns.tolist()

        numeric_pipeline = Pipeline([
            ('imputer', SimpleImputer(strategy='median')),
            ('scaler', StandardScaler())
        ])

        categorical_pipeline = Pipeline([
            ('imputer', SimpleImputer(strategy='most_frequent')),
            ('encoder', OneHotEncoder(handle_unknown='ignore'))
        ])

        return ColumnTransformer([
            ('num', numeric_pipeline, num_cols),
            ('cat', categorical_pipeline, cat_cols)
        ])

    pipeline = Pipeline([
        ('preprocessing', 'passthrough'),
        ('model', model)
    ])

    return pipeline
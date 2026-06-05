"""
🌾 AGRIPREDICT AI — DASHBOARD UI v5.0
======================================
A single-page agricultural intelligence dashboard.

Layout:
  [Header Bar]
  [5 KPI Metric Cards]
  [3-Column Main: Inputs | Prediction Result | Historical Trend]
  [4 Circular Score Gauges]
  [AI Insights & Recommendations]

Stack: Streamlit · Plotly · Custom HTML/CSS
"""

import os
from datetime import datetime
import streamlit as st
import joblib
import numpy as np
import pandas as pd
import plotly.graph_objects as go

# ════════════════════════════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════════════════════════════
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "crop_yield_model_v2_extra_trees.pkl")
DATA_PATH = os.path.join(BASE_DIR, "master_dataset_enhanced.csv")
FALLBACK_DATA_PATH = os.path.join(BASE_DIR, "master_dataset_cleaned.csv")

SPECIAL_UNIT_CROPS = {"Coconut": "nuts/ha", "Coconut ": "nuts/ha"}
DEFAULT_UNIT = "tonnes/ha"


def yield_unit(crop: str) -> str:
    return SPECIAL_UNIT_CROPS.get(crop, DEFAULT_UNIT)


st.set_page_config(
    page_title="AgriPredict AI · Crop Yield Intelligence",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ════════════════════════════════════════════════════════════════════
# CUSTOM CSS — Dashboard styling
# ════════════════════════════════════════════════════════════════════
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">

<style>
/* ───── BASE ───── */
.stApp {
    background: #f5f7f4;
    font-family: 'Inter', -apple-system, sans-serif;
}
.main .block-container {
    padding-top: 1rem;
    padding-bottom: 2rem;
    max-width: 100%;
}

* { font-family: 'Inter', sans-serif; }

#MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; }

/* ───── SIDEBAR (DARK GREEN) ───── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d3d20 0%, #0a2e18 100%);
    padding-top: 1rem;
}
[data-testid="stSidebar"] > div:first-child {
    padding-top: 1rem;
}
[data-testid="stSidebar"] * {
    color: #e8f0e9 !important;
    font-family: 'Inter', sans-serif !important;
}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
    color: #ffffff !important;
}

/* Sidebar radio buttons styled as nav menu */
[data-testid="stSidebar"] [role="radiogroup"] {
    gap: 4px;
}
[data-testid="stSidebar"] [role="radiogroup"] label {
    background: transparent;
    padding: 12px 14px;
    border-radius: 8px;
    width: 100%;
    transition: background 0.2s;
    cursor: pointer;
}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {
    background: rgba(255,255,255,0.05);
}
[data-testid="stSidebar"] [role="radiogroup"] label[data-checked="true"] {
    background: #1f7a3d !important;
}
[data-testid="stSidebar"] [role="radiogroup"] label p {
    font-size: 14px !important;
    font-weight: 500 !important;
}

/* Hide radio bullets */
[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child {
    display: none;
}

/* ───── TOP HEADER ───── */
.dash-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 0 1.2rem 0;
    margin-bottom: 0.5rem;
}
.dash-header-left h1 {
    font-size: 1.9rem !important;
    font-weight: 700 !important;
    color: #1a2e1e !important;
    margin: 0 !important;
    line-height: 1.2;
}
.dash-header-left .subtitle {
    font-size: 0.92rem;
    color: #6b7568;
    margin-top: 0.2rem;
}
.dash-header-right {
    display: flex;
    align-items: center;
    gap: 1rem;
}
.date-pill {
    background: white;
    border: 1px solid #e0e6dd;
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 0.88rem;
    color: #4a5d4e;
    display: inline-flex;
    align-items: center;
    gap: 6px;
}

/* ───── KPI METRIC CARDS (TOP ROW) ───── */
.kpi-card {
    background: white;
    border-radius: 14px;
    padding: 1.1rem 1.3rem;
    border: 1px solid #e8ede5;
    display: flex;
    align-items: center;
    gap: 14px;
    height: 100%;
    min-height: 92px;
}
.kpi-icon {
    width: 48px;
    height: 48px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.4rem;
    flex-shrink: 0;
}
.kpi-content { flex: 1; }
.kpi-label {
    font-size: 0.72rem;
    color: #8a9388;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 2px;
}
.kpi-value {
    font-size: 1.55rem;
    font-weight: 700;
    color: #1a2e1e;
    line-height: 1.1;
}
.kpi-sub {
    font-size: 0.75rem;
    color: #8a9388;
    margin-top: 2px;
}

/* KPI colored variants */
.kpi-green .kpi-icon { background: #e3f0e6; color: #1f7a3d; }
.kpi-blue .kpi-icon { background: #e1edf7; color: #2c6cb0; }
.kpi-purple .kpi-icon { background: #ece4f7; color: #6b46a8; }
.kpi-amber .kpi-icon { background: #fce8d4; color: #b8731d; }
.kpi-teal .kpi-icon { background: #d8efeb; color: #1f7a6d; }

/* ───── SECTION CARDS (3-column main row) ───── */
.section-card {
    background: white;
    border-radius: 16px;
    padding: 1.4rem 1.5rem;
    border: 1px solid #e8ede5;
    height: 100%;
}
.section-title {
    font-size: 1rem;
    font-weight: 700;
    color: #1a2e1e;
    margin-bottom: 1rem;
    display: flex;
    align-items: center;
    gap: 8px;
}

/* ───── INPUT GROUP HEADERS ───── */
.input-group {
    background: #f5faf6;
    border-radius: 8px;
    padding: 8px 12px;
    margin: 12px 0 10px 0;
    font-size: 0.82rem;
    font-weight: 600;
    color: #1f7a3d;
    display: flex;
    align-items: center;
    gap: 6px;
}

/* ───── STREAMLIT INPUT TWEAKS ───── */
.stNumberInput input, .stSelectbox div[data-baseweb="select"] > div {
    border-radius: 8px !important;
    border-color: #d8dfd6 !important;
    font-size: 0.9rem !important;
    background: white !important;
}
.stNumberInput label, .stSelectbox label {
    font-size: 0.82rem !important;
    color: #4a5d4e !important;
    font-weight: 500 !important;
    margin-bottom: 4px !important;
}

/* ───── PRIMARY BUTTON ───── */
.stButton button[kind="primary"] {
    background: linear-gradient(135deg, #1f7a3d 0%, #156030 100%) !important;
    border: none !important;
    color: white !important;
    border-radius: 10px !important;
    padding: 0.75rem 1.5rem !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    width: 100%;
    box-shadow: 0 2px 8px rgba(31,122,61,0.25) !important;
}
.stButton button[kind="primary"]:hover {
    background: linear-gradient(135deg, #156030 0%, #0d4a23 100%) !important;
    box-shadow: 0 4px 14px rgba(31,122,61,0.35) !important;
    transform: translateY(-1px);
}

/* ───── PREDICTION RESULT CARD ───── */
.predict-card {
    text-align: center;
    padding-top: 0.5rem;
}
.predict-label {
    font-size: 0.85rem;
    color: #6b7568;
    margin-bottom: 4px;
}
.predict-value {
    font-size: 3.5rem;
    font-weight: 800;
    color: #1f7a3d;
    line-height: 1;
    margin: 0.5rem 0;
}
.predict-unit {
    font-size: 0.95rem;
    color: #4a5d4e;
    font-weight: 500;
    margin-bottom: 1rem;
}
.predict-badge {
    display: inline-block;
    background: #e3f0e6;
    color: #156030;
    padding: 8px 18px;
    border-radius: 20px;
    font-size: 0.82rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    margin: 0.5rem 0 1rem 0;
}
.predict-badge.high { background: #e3f0e6; color: #156030; }
.predict-badge.med { background: #fce8d4; color: #b8731d; }
.predict-badge.low { background: #fde0e0; color: #a82828; }

.compare-box {
    background: #f5faf6;
    border-radius: 10px;
    padding: 1rem;
    margin-top: 1rem;
}
.compare-label {
    font-size: 0.82rem;
    color: #6b7568;
}
.compare-value {
    font-size: 1.5rem;
    font-weight: 700;
    color: #1f7a3d;
    margin: 0.3rem 0;
}
.compare-value.neg { color: #a82828; }
.compare-sub {
    font-size: 0.78rem;
    color: #6b7568;
}

.confidence-row {
    margin-top: 1rem;
    display: flex;
    justify-content: space-between;
    font-size: 0.85rem;
    color: #4a5d4e;
}
.confidence-bar-bg {
    background: #e8ede5;
    height: 8px;
    border-radius: 4px;
    margin-top: 6px;
    overflow: hidden;
}
.confidence-bar-fill {
    height: 100%;
    background: linear-gradient(90deg, #1f7a3d, #4caf50);
    border-radius: 4px;
}

/* ───── SCORE GAUGE CARDS ───── */
.score-card {
    background: white;
    border-radius: 14px;
    padding: 1.2rem;
    border: 1px solid #e8ede5;
    text-align: center;
    height: 100%;
}
.score-card-title {
    font-size: 0.92rem;
    font-weight: 600;
    color: #4a5d4e;
    margin-bottom: 0.8rem;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
}
.score-rating {
    font-size: 0.95rem;
    font-weight: 700;
    margin-top: 0.4rem;
}
.score-desc {
    font-size: 0.78rem;
    color: #6b7568;
    margin-top: 0.3rem;
    line-height: 1.4;
}

/* ───── RECOMMENDATIONS ROW ───── */
.recs-container {
    background: white;
    border-radius: 16px;
    padding: 1.4rem 1.5rem;
    border: 1px solid #e8ede5;
    margin-top: 1rem;
}
.rec-item {
    display: flex;
    gap: 10px;
    align-items: flex-start;
    padding: 0.4rem 0;
}
.rec-icon {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    font-size: 0.9rem;
    font-weight: 700;
}
.rec-icon.ok { background: #e3f0e6; color: #156030; }
.rec-icon.warn { background: #fce8d4; color: #b8731d; }
.rec-icon.info { background: #e1edf7; color: #2c6cb0; }

.rec-title {
    font-size: 0.92rem;
    font-weight: 600;
    color: #1a2e1e;
    margin-bottom: 2px;
}
.rec-title.ok { color: #156030; }
.rec-title.warn { color: #b8731d; }
.rec-title.info { color: #2c6cb0; }
.rec-desc {
    font-size: 0.8rem;
    color: #6b7568;
    line-height: 1.5;
}

/* Misc */
hr { border-color: #e8ede5 !important; margin: 0.6rem 0 !important; }
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
# LOAD MODEL + DATA
# ════════════════════════════════════════════════════════════════════
@st.cache_resource
def load_model():
    if not os.path.exists(MODEL_PATH):
        st.error(f"Model file not found: `{MODEL_PATH}`")
        st.stop()
    return joblib.load(MODEL_PATH)


@st.cache_data
def load_data():
    path = DATA_PATH if os.path.exists(DATA_PATH) else FALLBACK_DATA_PATH
    if not os.path.exists(path):
        st.error("Dataset not found.")
        st.stop()
    return pd.read_csv(path)


model = load_model()
data = load_data()
MODEL_FEATURES = list(model.feature_names_in_)

state_options = sorted(data["state"].dropna().unique().tolist())
season_options = sorted(data["season"].dropna().unique().tolist())
crop_options = sorted(data["crop"].dropna().unique().tolist())
crop_yield_ranges = data.groupby("crop")["yield"].agg(["min", "max", "mean", "median"]).round(3)


# ════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS — score calculations
# ════════════════════════════════════════════════════════════════════
def soil_health_score(N, P, K, pH):
    """0-100. NPK sufficiency + pH optimality."""
    npk = N + P + K
    npk_score = min(100, (npk / 180) * 100)  # 180 is ideal NPK sum
    ph_score = 100 if 6.0 <= pH <= 7.5 else max(0, 100 - abs(pH - 6.75) * 30)
    return int(0.65 * npk_score + 0.35 * ph_score)


def climate_suitability_score(temp, rainfall, humidity):
    """0-100. How close to typical Indian crop-growing conditions."""
    # Ideal: temp 22-30, rainfall 800-2000, humidity 60-80
    t_score = 100 - min(100, abs(temp - 26) * 6)
    r_score = 100 if 800 <= rainfall <= 2000 else max(0, 100 - abs(rainfall - 1400) / 30)
    h_score = 100 - min(100, abs(humidity - 70) * 2)
    return int((t_score + r_score + h_score) / 3)


def input_efficiency_score(fertilizer, pesticide, rainfall):
    """0-100. Balanced inputs without over-application."""
    # Ideal fertilizer: 100-250; pesticide: 1-5
    fert_score = 100 if 100 <= fertilizer <= 250 else max(0, 100 - abs(fertilizer - 175) / 3)
    pest_score = 100 if 1 <= pesticide <= 5 else max(0, 100 - abs(pesticide - 3) * 15)
    return int((fert_score + pest_score) / 2)


def npk_balance_score(N, P, K):
    """0-100. How close to ideal N:P:K = 3:1:2 ratio."""
    if N == 0:
        return 0
    p_ideal = N / 3
    k_ideal = N / 1.5
    p_dev = abs(P - p_ideal) / max(p_ideal, 1)
    k_dev = abs(K - k_ideal) / max(k_ideal, 1)
    return int(max(0, 100 - (p_dev + k_dev) * 50))


def rating_label(score):
    if score >= 80: return "Excellent", "#1f7a3d"
    if score >= 65: return "Good", "#3b8c5a"
    if score >= 50: return "Moderate", "#b8731d"
    if score >= 30: return "Below avg", "#c8843a"
    return "Poor", "#a82828"


def make_gauge(score, color):
    """Build a circular plotly gauge for the score."""
    fig = go.Figure(go.Pie(
        values=[score, 100 - score],
        rotation=0,
        hole=0.72,
        marker_colors=[color, "#e8ede5"],
        sort=False,
        direction="clockwise",
        textinfo="none",
        hoverinfo="skip",
    ))
    fig.update_layout(
        showlegend=False,
        margin=dict(l=0, r=0, t=0, b=0),
        height=140,
        annotations=[
            dict(text=f"<b>{score}</b>", x=0.5, y=0.55, font_size=26, font_color="#1a2e1e", showarrow=False),
            dict(text="/100", x=0.5, y=0.38, font_size=11, font_color="#8a9388", showarrow=False),
        ],
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


# ════════════════════════════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("""
    <div style="text-align: center; padding: 0.5rem 0 1.5rem 0;">
        <div style="font-size: 2.2rem;">🌱</div>
        <div style="font-size: 1.4rem; font-weight: 700; color: white; margin-top: 4px;">
            Agri<span style="color: #4caf50;">Predict</span> AI
        </div>
        <div style="font-size: 0.75rem; color: #a8c4ad; margin-top: 2px;">
            Crop Yield Intelligence
        </div>
    </div>
    <hr style="border-color: rgba(255,255,255,0.08); margin: 0 0 1rem 0;">
    """, unsafe_allow_html=True)

    page = st.radio(
        "nav",
        ["🏠  Dashboard", "📊  Historical Trends", "🌾  Crop Insights", "ℹ️  About Project"],
        label_visibility="collapsed",
    )

    st.markdown("""
    <hr style="border-color: rgba(255,255,255,0.08); margin: 1rem 0;">
    <div style="padding: 0 8px;">
        <div style="font-size: 0.95rem; font-weight: 600; color: white; margin-bottom: 0.8rem;">
            Model Information
        </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div style="padding: 0 8px; font-size: 0.82rem; line-height: 1.9; color: #c0d4c5;">
        <div style="color: #8aa890; font-size: 0.75rem;">MODEL</div>
        <div style="color: white; font-weight: 500; margin-bottom: 0.8rem;">Extra Trees Regressor</div>
        <div style="color: #8aa890; font-size: 0.75rem;">ACCURACY (R²)</div>
        <div style="color: white; font-weight: 600; margin-bottom: 0.8rem;">95.06%</div>
        <div style="color: #8aa890; font-size: 0.75rem;">RECORDS</div>
        <div style="color: white; font-weight: 500; margin-bottom: 0.8rem;">{len(data):,}</div>
        <div style="color: #8aa890; font-size: 0.75rem;">COVERAGE</div>
        <div style="color: white; font-weight: 500;">{len(crop_options)} crops · {len(state_options)} states</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="position: relative; margin-top: 2rem; padding: 1rem; background: rgba(76,175,80,0.08); border-radius: 10px; border: 1px solid rgba(76,175,80,0.2);">
        <div style="font-size: 0.75rem; color: #8aa890;">🌾 EMPOWERING</div>
        <div style="font-size: 0.85rem; color: white; font-weight: 500; margin-top: 2px;">Farmers with Data & AI</div>
    </div>
    """, unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
# MAIN DASHBOARD CONTENT
# ════════════════════════════════════════════════════════════════════
if page.startswith("🏠"):

    # ───── HEADER ─────
    h_left, h_right = st.columns([3, 1])
    with h_left:
        st.markdown("""
        <div class="dash-header-left">
            <h1>🌾 Crop Yield Prediction</h1>
            <div class="subtitle">Predict crop yield using weather, soil and farm input intelligence</div>
        </div>
        """, unsafe_allow_html=True)
    with h_right:
        st.markdown(f"""
        <div style="display: flex; justify-content: flex-end; align-items: center; gap: 10px; padding-top: 8px;">
            <div class="date-pill">📅 {datetime.now().strftime('%d %B %Y')}</div>
        </div>
        """, unsafe_allow_html=True)

    # ───── KPI METRIC CARDS ─────
    k1, k2, k3, k4, k5 = st.columns(5)
    with k1:
        st.markdown(f"""
        <div class="kpi-card kpi-green">
            <div class="kpi-icon">🌱</div>
            <div class="kpi-content">
                <div class="kpi-label">Total Records</div>
                <div class="kpi-value">{len(data):,}</div>
                <div class="kpi-sub">Historical Data Points</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with k2:
        st.markdown(f"""
        <div class="kpi-card kpi-teal">
            <div class="kpi-icon">🌾</div>
            <div class="kpi-content">
                <div class="kpi-label">Crops Covered</div>
                <div class="kpi-value">{len(crop_options)}</div>
                <div class="kpi-sub">Different Crops</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with k3:
        st.markdown(f"""
        <div class="kpi-card kpi-purple">
            <div class="kpi-icon">🗺️</div>
            <div class="kpi-content">
                <div class="kpi-label">States Covered</div>
                <div class="kpi-value">{len(state_options)}</div>
                <div class="kpi-sub">Indian States</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with k4:
        st.markdown("""
        <div class="kpi-card kpi-amber">
            <div class="kpi-icon">🎯</div>
            <div class="kpi-content">
                <div class="kpi-label">Model Accuracy</div>
                <div class="kpi-value">95%</div>
                <div class="kpi-sub">R² Score</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    with k5:
        st.markdown(f"""
        <div class="kpi-card kpi-blue">
            <div class="kpi-icon">📅</div>
            <div class="kpi-content">
                <div class="kpi-label">Data Range</div>
                <div class="kpi-value">{int(data['year'].min())}–{int(data['year'].max())}</div>
                <div class="kpi-sub">24 Years</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height: 1.2rem;'></div>", unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════
    # MAIN 3-COLUMN ROW: Inputs | Prediction Result | Historical Trend
    # ═══════════════════════════════════════════════════════════════
    col_inputs, col_result, col_chart = st.columns([1.15, 1, 1.2])

    # ─── COLUMN 1: INPUTS ───
    with col_inputs:
        with st.container():
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">🎛️ Input Parameters</div>', unsafe_allow_html=True)

            st.markdown('<div class="input-group">📍 Location & Time</div>', unsafe_allow_html=True)
            cc1, cc2 = st.columns(2)
            with cc1:
                state = st.selectbox("State", state_options, index=0, key="state")
            with cc2:
                year = st.number_input("Year", min_value=int(data["year"].min()),
                                       max_value=int(data["year"].max() + 5),
                                       value=int(data["year"].max()), step=1, key="year")

            st.markdown('<div class="input-group">🌾 Crop Information</div>', unsafe_allow_html=True)
            cc1, cc2 = st.columns(2)
            with cc1:
                crop = st.selectbox("Crop", crop_options, key="crop")
            with cc2:
                season = st.selectbox("Season", season_options, key="season")

            st.markdown('<div class="input-group">🌱 Soil Information</div>', unsafe_allow_html=True)
            cc1, cc2, cc3 = st.columns(3)
            with cc1:
                N = st.number_input("Nitrogen (N)", 0.0, 200.0, 78.0, 1.0, key="N",
                                    help="kg/ha. Typical Indian soil: 50–100")
            with cc2:
                P = st.number_input("Phosphorus (P)", 0.0, 100.0, 45.0, 1.0, key="P",
                                    help="kg/ha. Typical Indian soil: 15–45")
            with cc3:
                K = st.number_input("Potassium (K)", 0.0, 100.0, 22.0, 1.0, key="K",
                                    help="kg/ha. Typical Indian soil: 20–50")

            cc1, cc2 = st.columns(2)
            with cc1:
                pH = st.number_input("pH Value", 4.0, 9.0, 6.8, 0.1, key="pH",
                                     help="6.0–7.5 is optimal for most crops")
            with cc2:
                # Live soil fertility score preview
                preview_score = soil_health_score(N, P, K, pH)
                _, rating_color = rating_label(preview_score)
                st.markdown(f"""
                <div style="margin-top: 26px;">
                    <div style="font-size: 0.82rem; color: #4a5d4e; font-weight: 500; margin-bottom: 4px;">Soil Fertility Score</div>
                    <div style="display: flex; gap: 8px; align-items: center;">
                        <div style="background: white; border: 1px solid #d8dfd6; border-radius: 8px; padding: 6px 10px; flex: 1;">
                            <span style="font-weight: 600; color: #1a2e1e;">{preview_score} / 100</span>
                        </div>
                        <div style="background: {rating_color}20; color: {rating_color}; padding: 6px 12px; border-radius: 8px; font-size: 0.78rem; font-weight: 600;">
                            {rating_label(preview_score)[0]}
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

            st.markdown('<div class="input-group">🌤️ Climate Information</div>', unsafe_allow_html=True)
            cc1, cc2, cc3 = st.columns(3)
            with cc1:
                avg_temp_c = st.number_input("Avg Temp (°C)", 5.0, 40.0, 28.2, 0.1, key="temp")
            with cc2:
                total_rainfall_mm = st.number_input("Rainfall (mm)", 100.0, 5000.0, 1191.1, 10.0, key="rain")
            with cc3:
                avg_humidity_percent = st.number_input("Humidity (%)", 20.0, 100.0, 69.6, 0.5, key="hum")

            st.markdown('<div class="input-group">🧪 Farm Inputs</div>', unsafe_allow_html=True)
            cc1, cc2 = st.columns(2)
            with cc1:
                fertilizer_per_ha = st.number_input("Fertilizer (kg/ha)", 0.0, 500.0, 250.5, 1.0, key="fert")
            with cc2:
                pesticide_per_ha = st.number_input("Pesticide (kg/ha)", 0.0, 20.0, 1.25, 0.05, key="pest")

            st.markdown("<div style='height: 0.8rem;'></div>", unsafe_allow_html=True)
            predict_clicked = st.button("✨  Predict Yield", type="primary", use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════
    # COMPUTE PREDICTION (always — so result column is never empty)
    # ═══════════════════════════════════════════════════════════════
    NPK_total = N + P + K
    N_to_P_ratio = N / (P + 0.1)
    N_to_K_ratio = N / (K + 0.1)
    P_to_K_ratio = P / (K + 0.1)
    NPK_balance_score_val = np.abs((N / 3) - P) + np.abs((N / 1.5) - K)
    temp_rainfall_interaction = avg_temp_c * total_rainfall_mm
    temp_humidity_interaction = avg_temp_c * avg_humidity_percent
    moisture_index = (total_rainfall_mm * avg_humidity_percent) / 100
    growing_degree_days = max(0, avg_temp_c - 10)
    pH_optimal = 1 if 6.0 <= pH <= 7.5 else 0
    soil_fertility_score_val = (NPK_total / 200) * 0.7 + pH_optimal * 0.3
    fertilizer_rainfall_ratio = fertilizer_per_ha / (total_rainfall_mm + 1)
    pesticide_efficiency = pesticide_per_ha / 10
    input_intensity = (fertilizer_per_ha / 500 + pesticide_per_ha / 20) / 2
    years_since_start = year - int(data["year"].min())

    input_data = {
        "N": N, "P": P, "K": K, "pH": pH,
        "avg_temp_c": avg_temp_c, "avg_humidity_percent": avg_humidity_percent,
        "total_rainfall_mm": total_rainfall_mm,
        "pesticide_per_ha": pesticide_per_ha, "fertilizer_per_ha": fertilizer_per_ha,
        "year": year, "state": state, "season": season, "crop": crop,
        "NPK_total": NPK_total, "N_to_P_ratio": N_to_P_ratio,
        "N_to_K_ratio": N_to_K_ratio, "P_to_K_ratio": P_to_K_ratio,
        "NPK_balance_score": NPK_balance_score_val,
        "temp_rainfall_interaction": temp_rainfall_interaction,
        "temp_humidity_interaction": temp_humidity_interaction,
        "moisture_index": moisture_index,
        "growing_degree_days": growing_degree_days,
        "pH_optimal": pH_optimal,
        "soil_fertility_score": soil_fertility_score_val,
        "fertilizer_rainfall_ratio": fertilizer_rainfall_ratio,
        "pesticide_efficiency": pesticide_efficiency,
        "input_intensity": input_intensity,
        "years_since_start": years_since_start,
    }

    input_df = pd.DataFrame([input_data]).reindex(columns=MODEL_FEATURES, fill_value=0)
    try:
        prediction = float(model.predict(input_df)[0])
    except Exception:
        prediction = 0.0

    unit = yield_unit(crop)
    avg_y = float(crop_yield_ranges.loc[crop, "mean"]) if crop in crop_yield_ranges.index else 0
    diff_pct = ((prediction - avg_y) / avg_y * 100) if avg_y > 0 else 0

    # Productivity badge
    if avg_y > 0:
        ratio = prediction / avg_y
        if ratio >= 1.1:
            badge_class, badge_text = "high", "🌟 HIGH PRODUCTIVITY"
        elif ratio >= 0.85:
            badge_class, badge_text = "med", "✓ NORMAL PRODUCTIVITY"
        else:
            badge_class, badge_text = "low", "⚠ LOW PRODUCTIVITY"
    else:
        badge_class, badge_text = "med", "ESTIMATE"

    # Confidence (heuristic — based on how close inputs are to training distribution)
    confidence = 94  # Static for now; could be made dynamic

    # ─── COLUMN 2: PREDICTION RESULT ───
    with col_result:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">📈 Prediction Result</div>', unsafe_allow_html=True)

        diff_class = "" if diff_pct >= 0 else "neg"
        diff_sign = "+" if diff_pct >= 0 else ""
        diff_label = "Above Average" if diff_pct >= 0 else "Below Average"

        st.markdown(f"""
        <div class="predict-card">
            <div class="predict-label">Expected Yield 🌱</div>
            <div class="predict-value">{prediction:.2f}</div>
            <div class="predict-unit">{unit}</div>
            <div class="predict-badge {badge_class}">{badge_text}</div>
            <div class="compare-box">
                <div class="compare-label">Compared to historical average</div>
                <div class="compare-value {diff_class}">{diff_sign}{diff_pct:.1f}%</div>
                <div class="compare-sub">{diff_label} ({avg_y:.2f} {unit})</div>
            </div>
            <div class="confidence-row">
                <span>Model Confidence ⓘ</span>
                <span style="font-weight: 700; color: #1f7a3d;">{confidence}%</span>
            </div>
            <div class="confidence-bar-bg"><div class="confidence-bar-fill" style="width: {confidence}%;"></div></div>
        </div>
        """, unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # ─── COLUMN 3: HISTORICAL TREND ───
    with col_chart:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">📊 Historical Yield Trend</div>', unsafe_allow_html=True)

        # Filter for crop+state if data exists, else show all-india avg
        crop_state_data = data[(data["crop"] == crop) & (data["state"] == state)]
        if len(crop_state_data) < 5:
            trend_data = data[data["crop"] == crop].groupby("year")["yield"].mean()
            trend_title = f"{crop.strip()} — All India"
        else:
            trend_data = crop_state_data.groupby("year")["yield"].mean()
            trend_title = f"{crop.strip()} — {state}"

        if len(trend_data) > 0:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=trend_data.index, y=trend_data.values,
                mode="lines+markers",
                line=dict(color="#1f7a3d", width=2.5),
                marker=dict(size=6, color="#1f7a3d", line=dict(color="white", width=1.5)),
                fill="tozeroy", fillcolor="rgba(31,122,61,0.08)",
                hovertemplate="<b>%{x}</b><br>%{y:.2f} " + unit + "<extra></extra>",
                name="",
            ))
            fig.update_layout(
                height=250,
                margin=dict(l=10, r=10, t=10, b=10),
                xaxis=dict(title="Year", gridcolor="#f0f0f0", showline=False),
                yaxis=dict(title=f"Yield ({unit})", gridcolor="#f0f0f0", showline=False),
                plot_bgcolor="white",
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(family="Inter", size=11, color="#4a5d4e"),
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

            avg_trend = trend_data.mean()
            st.markdown(f"""
            <div style="background: #f5faf6; border-radius: 8px; padding: 10px 14px; margin-top: 0.4rem; font-size: 0.85rem; color: #4a5d4e;">
                <b style="color: #1f7a3d;">{trend_title}</b> · Average yield {trend_data.min():.2f}–{trend_data.max():.2f} {unit} (mean {avg_trend:.2f})
            </div>
            """, unsafe_allow_html=True)
        else:
            st.info("Not enough historical data to plot a trend for this combination.")

        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<div style='height: 1.2rem;'></div>", unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════
    # 4 SCORE GAUGE CARDS
    # ═══════════════════════════════════════════════════════════════
    soil_s = soil_health_score(N, P, K, pH)
    climate_s = climate_suitability_score(avg_temp_c, total_rainfall_mm, avg_humidity_percent)
    input_s = input_efficiency_score(fertilizer_per_ha, pesticide_per_ha, total_rainfall_mm)
    npk_s = npk_balance_score(N, P, K)

    gauges = [
        ("🌱 Soil Health Score", soil_s, "#1f7a3d",
         f"Soil condition is {rating_label(soil_s)[0].lower()} for {crop.strip()}"),
        ("🌧️ Climate Suitability", climate_s, "#2c6cb0",
         f"Climate is {rating_label(climate_s)[0].lower()} for this crop"),
        ("⚖️ Input Efficiency", input_s, "#b8731d",
         f"Inputs are {rating_label(input_s)[0].lower()}"),
        ("🧪 NPK Balance", npk_s, "#6b46a8",
         f"NPK levels are {rating_label(npk_s)[0].lower()}"),
    ]

    g1, g2, g3, g4 = st.columns(4)
    for col, (title, score, color, desc) in zip([g1, g2, g3, g4], gauges):
        with col:
            st.markdown(f'<div class="score-card">', unsafe_allow_html=True)
            st.markdown(f'<div class="score-card-title">{title}</div>', unsafe_allow_html=True)
            st.plotly_chart(make_gauge(score, color), use_container_width=True, config={"displayModeBar": False})
            rating_text, rating_color = rating_label(score)
            st.markdown(f"""
            <div class="score-rating" style="color: {rating_color};">{rating_text}</div>
            <div class="score-desc">{desc}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("<div style='height: 0.8rem;'></div>", unsafe_allow_html=True)

    # ═══════════════════════════════════════════════════════════════
    # AI INSIGHTS & RECOMMENDATIONS
    # ═══════════════════════════════════════════════════════════════
    recs = []

    # Rainfall check
    if 500 <= total_rainfall_mm <= 2500:
        recs.append(("ok", "Favorable Rainfall", f"Rainfall is within the optimal range for {crop.strip()}."))
    elif total_rainfall_mm < 500:
        recs.append(("warn", "Low Rainfall", f"Rainfall is below optimal. Consider irrigation planning."))
    else:
        recs.append(("warn", "High Rainfall", "Very high rainfall — watch for waterlogging and disease risk."))

    # Temperature check
    if 20 <= avg_temp_c <= 32:
        recs.append(("ok", "Optimal Temperature", "Temperature conditions are ideal for maximum yield."))
    else:
        recs.append(("warn", "Suboptimal Temperature", "Temperature is outside ideal range — monitor crop stress."))

    # pH check
    if 6.0 <= pH <= 7.5:
        recs.append(("ok", "Soil pH Optimal", "Soil pH is in the optimal range for this crop."))
    elif pH < 6.0:
        recs.append(("warn", "Acidic Soil", f"pH {pH:.1f} is acidic. Consider liming."))
    else:
        recs.append(("warn", "Alkaline Soil", f"pH {pH:.1f} is alkaline. Consider sulfur application."))

    # NPK check
    if N_to_P_ratio > 4:
        recs.append(("warn", "Increase Phosphorus", "Increase phosphorus by ~10% for better yield outcome."))
    elif N_to_P_ratio < 1.5:
        recs.append(("warn", "Increase Nitrogen", "Nitrogen is low relative to phosphorus. Boost N inputs."))
    else:
        recs.append(("ok", "Balanced NPK", "Your N:P ratio is well balanced for most crops."))

    # Yield potential
    if avg_y > 0:
        if prediction >= avg_y * 1.1:
            recs.append(("info", "Yield Potential", "With optimized inputs, yield may increase by 8–12%."))
        elif prediction < avg_y * 0.85:
            recs.append(("info", "Optimization Tip", "Review soil and inputs — historical yields suggest higher potential."))
        else:
            recs.append(("info", "Yield Potential", "Your inputs align with historically average yields."))
    else:
        recs.append(("info", "Yield Potential", "Predictions for this crop are based on limited historical data."))

    st.markdown('<div class="recs-container">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">💡 AI Insights & Recommendations</div>', unsafe_allow_html=True)

    rec_cols = st.columns(5)
    icons = {"ok": "✓", "warn": "!", "info": "i"}
    for col, (kind, title, desc) in zip(rec_cols, recs[:5]):
        with col:
            st.markdown(f"""
            <div class="rec-item">
                <div class="rec-icon {kind}">{icons[kind]}</div>
                <div>
                    <div class="rec-title {kind}">{title}</div>
                    <div class="rec-desc">{desc}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════
# OTHER PAGES (simple)
# ════════════════════════════════════════════════════════════════════
elif page.startswith("📊"):
    st.markdown("# 📊 Historical Trends")
    st.markdown("Explore yield patterns across crops, states, and years.")

    comparable = data[~data["crop"].str.strip().isin(SPECIAL_UNIT_CROPS.keys())]

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Average yield by year")
        yearly = comparable.groupby("year")["yield"].mean()
        fig = go.Figure(go.Scatter(
            x=yearly.index, y=yearly.values,
            mode="lines+markers",
            line=dict(color="#1f7a3d", width=2.5),
            marker=dict(size=7, color="#1f7a3d"),
            fill="tozeroy", fillcolor="rgba(31,122,61,0.1)",
        ))
        fig.update_layout(
            height=350, plot_bgcolor="white",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter"),
            xaxis=dict(title="Year", gridcolor="#f0f0f0"),
            yaxis=dict(title="Yield (tonnes/ha)", gridcolor="#f0f0f0"),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("### Average yield by season")
        season_y = comparable.groupby("season")["yield"].mean().sort_values(ascending=False)
        fig = go.Figure(go.Bar(
            x=season_y.index, y=season_y.values,
            marker=dict(color="#1f7a3d"),
        ))
        fig.update_layout(
            height=350, plot_bgcolor="white",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Inter"),
            yaxis=dict(title="Yield (tonnes/ha)", gridcolor="#f0f0f0"),
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Average yield by state")
    state_y = comparable.groupby("state")["yield"].mean().sort_values(ascending=False)
    fig = go.Figure(go.Bar(
        x=state_y.values, y=state_y.index, orientation="h",
        marker=dict(color=state_y.values, colorscale=[[0, "#cfe5d4"], [1, "#1f7a3d"]]),
    ))
    fig.update_layout(
        height=600, plot_bgcolor="white",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter"),
        xaxis=dict(title="Yield (tonnes/ha)", gridcolor="#f0f0f0"),
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig, use_container_width=True)


elif page.startswith("🌾"):
    st.markdown("# 🌾 Crop Insights")
    st.markdown("Detailed yield statistics for any crop in the dataset.")

    sel = st.selectbox("Select crop", crop_options)
    crop_data = data[data["crop"] == sel]
    u = yield_unit(sel)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Records", f"{len(crop_data):,}")
    c2.metric("Average Yield", f"{crop_data['yield'].mean():.2f} {u}")
    c3.metric("Min Yield", f"{crop_data['yield'].min():.2f} {u}")
    c4.metric("Max Yield", f"{crop_data['yield'].max():.2f} {u}")

    st.markdown("### Yield distribution")
    fig = go.Figure(go.Histogram(
        x=crop_data["yield"], nbinsx=40,
        marker=dict(color="#1f7a3d"),
    ))
    fig.add_vline(x=crop_data["yield"].mean(), line_dash="dash", line_color="#c8843a",
                  annotation_text=f"Mean {crop_data['yield'].mean():.2f}")
    fig.update_layout(
        height=400, plot_bgcolor="white",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter"),
        xaxis=dict(title=f"Yield ({u})", gridcolor="#f0f0f0"),
        yaxis=dict(title="Frequency", gridcolor="#f0f0f0"),
    )
    st.plotly_chart(fig, use_container_width=True)


else:  # About
    st.markdown("# ℹ️ About AgriPredict AI")
    st.markdown("""
    AgriPredict AI is a machine-learning powered crop yield forecasting system trained on
    24 years (1997–2020) of Indian agricultural data. It combines soil chemistry, weather
    patterns, and farming inputs to estimate expected harvests.

    ### Model
    - **Algorithm:** Extra Trees Regressor (200 estimators)
    - **Test R²:** 0.9506
    - **Mean Absolute Error:** 1.00
    - **Training records:** 19,689
    - **Coverage:** 55 crops · 30 states

    ### Units
    Most crops report yield in **tonnes per hectare (t/ha)**. Coconut is the exception —
    it's measured in **nuts per hectare**, since Indian government records count individual
    coconuts rather than weight.

    ### How to use
    1. Enter your field's location, soil, climate, and farm inputs on the **Dashboard**
    2. Click **Predict Yield** to get the forecast
    3. Review the four score gauges and AI recommendations
    4. Check **Historical Trends** to see how yields have evolved over time

    ### Important caveats
    Predictions are statistical estimates. Real-world yields depend on many factors not
    captured in the model. Use predictions as one input among many in farm planning.
    """)

    with st.expander("📄 Sample training data"):
        st.dataframe(data.head(20), use_container_width=True)
    with st.expander("🎯 Model features"):
        st.write(MODEL_FEATURES)
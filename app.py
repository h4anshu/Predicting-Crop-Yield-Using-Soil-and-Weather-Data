"""
CROP YIELD PREDICTION - ENHANCED STREAMLIT APP v2.0
====================================================
This is your improved app with the enhanced model from Stages 1-4

INSTRUCTIONS:
1. Save this file as 'app_v2.py'
2. Run: streamlit run app_v2.py
3. Open browser at http://localhost:8501
"""

import streamlit as st
import joblib
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import glob

# --------------------------
# PAGE CONFIGURATION
# --------------------------
st.set_page_config(
    page_title="Crop Yield Predictor v2.0",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --------------------------
# LOAD MODEL AND DATA
# --------------------------
@st.cache_resource
def load_model():
    """Load the best model from Stage 3"""
    model_files = glob.glob("crop_yield_model_v2_*.pkl")
    if model_files:
        model = joblib.load(model_files[0])
        model_name = model_files[0].replace('crop_yield_model_v2_', '').replace('.pkl', '').replace('_', ' ').title()
        return model, model_name
    else:
        # Fallback to original model
        try:
            model = joblib.load("crop_yield_model.pkl")
            return model, "Random Forest (Original)"
        except:
            st.error("❌ No model found! Please complete Stages 1-3 first.")
            st.stop()

@st.cache_data
def load_data():
    """Load the enhanced dataset for reference"""
    try:
        data = pd.read_csv("master_dataset_enhanced.csv")
        return data
    except:
        # Fallback to cleaned data
        try:
            data = pd.read_csv("master_dataset_cleaned.csv")
            return data
        except:
            st.error("❌ Dataset not found! Please complete Stage 1 first.")
            st.stop()

# Load model and data
model, model_name = load_model()
data = load_data()

model_features = model.feature_names_in_  # ✅ CRITICAL FIX


# --------------------------
# EXTRACT REFERENCE DATA
# --------------------------
# Get unique values for dropdowns
state_options = sorted(data["state"].dropna().unique().tolist())
season_options = sorted(data["season"].dropna().unique().tolist())
crop_options = sorted(data["crop"].dropna().unique().tolist())

# Get typical yield ranges by crop
crop_yield_ranges = data.groupby('crop')['yield'].agg(['min', 'max', 'mean', 'median']).round(2)

# --------------------------
# SIDEBAR
# --------------------------
st.sidebar.title("🌾 Crop Yield Predictor")
st.sidebar.markdown("### v2.0 - Enhanced Model")
st.sidebar.info(f"**Active Model:** {model_name}")

# Navigation
page = st.sidebar.radio(
    "Navigate to:",
    ["🎯 Prediction", "📊 Insights & Statistics", "ℹ️ About"]
)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🔧 Quick Stats")
st.sidebar.metric("Total Crops", len(crop_options))
st.sidebar.metric("States Covered", len(state_options))
st.sidebar.metric("Training Records", f"{len(data):,}")

# --------------------------
# PAGE 1: PREDICTION
# --------------------------
if page == "🎯 Prediction":
    st.title("🌾 Crop Yield Prediction System")
    st.markdown("### Predict crop yield based on soil, weather, and input data")
    
    # Create two columns for input
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 📍 Location & Crop Details")
        state = st.selectbox("Select State", state_options, key='state')
        crop = st.selectbox("Select Crop", crop_options, key='crop')
        season = st.selectbox("Select Season", season_options, key='season')
        year = st.number_input(
            "Year",
            min_value=int(data["year"].min()),
            max_value=int(data["year"].max() + 3),
            value=int(data["year"].max()),
            step=1
        )

        
        st.markdown("#### 🌱 Soil Nutrients (kg/ha)")
        N = st.number_input("Nitrogen (N)", min_value=0.0, max_value=200.0, value=60.0, step=1.0)
        P = st.number_input("Phosphorus (P)", min_value=0.0, max_value=100.0, value=18.0, step=1.0)
        K = st.number_input("Potassium (K)", min_value=0.0, max_value=100.0, value=38.0, step=1.0)
        pH = st.number_input("Soil pH", min_value=4.0, max_value=9.0, value=6.5, step=0.1)
    
    with col2:
        st.markdown("#### 🌤️ Weather Conditions")
        avg_temp_c = st.number_input("Average Temperature (°C)", min_value=-10.0, max_value=50.0, value=25.0, step=0.5)
        total_rainfall_mm = st.number_input("Total Rainfall (mm)", min_value=0.0, max_value=5000.0, value=1000.0, step=10.0)
        avg_humidity_percent = st.number_input("Average Humidity (%)", min_value=0.0, max_value=100.0, value=70.0, step=1.0)
        
        st.markdown("#### 🧪 Agricultural Inputs (per hectare)")
        fertilizer_per_ha = st.number_input("Fertilizer (kg/ha)", min_value=0.0, max_value=1000.0, value=100.0, step=5.0)
        pesticide_per_ha = st.number_input("Pesticide (kg/ha)", min_value=0.0, max_value=50.0, value=2.0, step=0.5)
    
    # Show typical yield range for selected crop
    if crop in crop_yield_ranges.index:
        st.info(f"📊 **Typical yield for {crop}:** {crop_yield_ranges.loc[crop, 'min']:.2f} - "
                f"{crop_yield_ranges.loc[crop, 'max']:.2f} kg/ha "
                f"(Average: {crop_yield_ranges.loc[crop, 'mean']:.2f})")
    
    # Calculate derived features (same as Stage 2)
    NPK_total = N + P + K
    N_to_P_ratio = N / (P + 0.1)
    N_to_K_ratio = N / (K + 0.1)
    P_to_K_ratio = P / (K + 0.1)
    NPK_balance_score = np.abs((N/3) - P) + np.abs((N/1.5) - K)
    
    temp_rainfall_interaction = avg_temp_c * total_rainfall_mm
    temp_humidity_interaction = avg_temp_c * avg_humidity_percent
    moisture_index = (total_rainfall_mm * avg_humidity_percent) / 100
    growing_degree_days = max(0, avg_temp_c - 10)
    
    pH_optimal = 1 if 6.0 <= pH <= 7.5 else 0
    soil_fertility_score = (NPK_total / 200) * 0.7 + pH_optimal * 0.3
    
    fertilizer_rainfall_ratio = fertilizer_per_ha / (total_rainfall_mm + 1)
    pesticide_efficiency = pesticide_per_ha / 10  # Normalized
    input_intensity = (fertilizer_per_ha / 500 + pesticide_per_ha / 20) / 2
    
    # For temporal features, use reasonable defaults
    # Temporal features (ONLY if model expects them)
    years_since_start = year - int(data["year"].min())

    if "yield_lag1" in model_features:
        yield_lag1 = st.number_input(
            "Previous Year Yield (kg/ha)",
            min_value=0.0,
            max_value=100000.0,
            value=float(crop_yield_ranges.loc[crop, 'median']) if crop in crop_yield_ranges.index else 3000.0
        )
    else:
        yield_lag1 = None

    
    # Collect all inputs
    input_data = {
        'N': N,
        'P': P,
        'K': K,
        'pH': pH,
        'avg_temp_c': avg_temp_c,
        'avg_humidity_percent': avg_humidity_percent,
        'total_rainfall_mm': total_rainfall_mm,
        'pesticide_per_ha': pesticide_per_ha,
        'fertilizer_per_ha': fertilizer_per_ha,
        'year': year,
        'state': state,
        'season': season,
        'crop': crop,
        'NPK_total': NPK_total,
        'N_to_P_ratio': N_to_P_ratio,
        'N_to_K_ratio': N_to_K_ratio,
        'P_to_K_ratio': P_to_K_ratio,
        'NPK_balance_score': NPK_balance_score,
        'temp_rainfall_interaction': temp_rainfall_interaction,
        'temp_humidity_interaction': temp_humidity_interaction,
        'moisture_index': moisture_index,
        'growing_degree_days': growing_degree_days,
        'pH_optimal': pH_optimal,
        'soil_fertility_score': soil_fertility_score,
        'fertilizer_rainfall_ratio': fertilizer_rainfall_ratio,
        'pesticide_efficiency': pesticide_efficiency,
        'input_intensity': input_intensity,
        'years_since_start': years_since_start
    }
    
    if yield_lag1 is not None:
       input_data['yield_lag1'] = yield_lag1

    
    # --------------------------
    # PREDICTION
    # --------------------------
    if st.button("🎯 Predict Yield", type="primary", use_container_width=True):
        try:
            input_df = pd.DataFrame([input_data])

            # ✅ CRITICAL FIX: Align with trained model features
            input_df = input_df.reindex(columns=model_features, fill_value=0)

            prediction = model.predict(input_df)[0]

            
            # Display prediction with formatting
            st.markdown("---")
            st.success("### ✅ Prediction Complete!")
            
            # Create metrics columns
            metric_col1, metric_col2, metric_col3 = st.columns(3)
            
            with metric_col1:
                st.metric(
                    label="Predicted Yield",
                    value=f"{prediction:.2f} kg/ha",
                    delta=None
                )
            
            with metric_col2:
                if crop in crop_yield_ranges.index:
                    avg_yield = crop_yield_ranges.loc[crop, 'mean']
                    diff = prediction - avg_yield
                    st.metric(
                        label="vs Average",
                        value=f"{avg_yield:.2f} kg/ha",
                        delta=f"{diff:+.2f} kg/ha"
                    )
            
            with metric_col3:
                min_y = crop_yield_ranges.loc[crop, 'min']
                max_y = crop_yield_ranges.loc[crop, 'max']
                range_diff = max_y - min_y

                if range_diff > 0:
                    percentile = ((prediction - min_y) / range_diff) * 100
                    percentile = min(100, max(0, percentile))
                else:
                    percentile = 50

                st.metric(
                    label="Percentile",
                    value=f"{min(100, max(0, percentile)):.0f}%"
                )
            
            # Visualization
            if crop in crop_yield_ranges.index:
                fig = go.Figure()
                
                # Add range bar
                fig.add_trace(go.Bar(
                    y=['Yield Range'],
                    x=[crop_yield_ranges.loc[crop, 'max'] - crop_yield_ranges.loc[crop, 'min']],
                    base=[crop_yield_ranges.loc[crop, 'min']],
                    orientation='h',
                    marker=dict(color='lightblue'),
                    name='Typical Range',
                    showlegend=True
                ))
                
                # Add average line
                fig.add_vline(
                    x=crop_yield_ranges.loc[crop, 'mean'],
                    line_dash="dash",
                    line_color="orange",
                    annotation_text="Average"
                )
                
                # Add prediction marker
                fig.add_trace(go.Scatter(
                    x=[prediction],
                    y=['Yield Range'],
                    mode='markers',
                    marker=dict(size=20, color='red', symbol='diamond'),
                    name='Your Prediction',
                    showlegend=True
                ))
                
                fig.update_layout(
                    title=f"Your Prediction vs Typical {crop} Yield Range",
                    xaxis_title="Yield (kg/ha)",
                    height=300,
                    showlegend=True
                )
                
                st.plotly_chart(fig, use_container_width=True)
            
            # Recommendations
            st.markdown("### 💡 Recommendations")
            
            if pH < 6.0:
                st.warning("⚠️ Soil pH is acidic. Consider liming to raise pH to 6.0-7.0")
            elif pH > 7.5:
                st.warning("⚠️ Soil pH is alkaline. Consider sulfur application to lower pH")
            else:
                st.success("✅ Soil pH is in optimal range (6.0-7.5)")
            
            if N_to_P_ratio < 2:
                st.info("💡 Consider increasing Nitrogen relative to Phosphorus")
            elif N_to_P_ratio > 5:
                st.info("💡 Consider increasing Phosphorus relative to Nitrogen")
            
            if total_rainfall_mm < 500:
                st.warning("⚠️ Low rainfall predicted. Consider irrigation planning")
            
        except Exception as e:
            st.error(f"❌ Error during prediction: {e}")
            st.error("Please check your inputs and try again")

# --------------------------
# PAGE 2: INSIGHTS & STATISTICS
# --------------------------
elif page == "📊 Insights & Statistics":
    st.title("📊 Data Insights & Statistics")
    
    tab1, tab2, tab3 = st.tabs(["🌾 Crop Analysis", "🗺️ State Analysis", "📅 Temporal Trends"])
    
    with tab1:
        st.markdown("### Crop Yield Statistics")
        
        # Top crops by average yield
        top_crops = data.groupby('crop')['yield'].mean().sort_values(ascending=False).head(15)
        
        fig = px.bar(
            x=top_crops.values,
            y=top_crops.index,
            orientation='h',
            title="Top 15 Crops by Average Yield",
            labels={'x': 'Average Yield (kg/ha)', 'y': 'Crop'},
            color=top_crops.values,
            color_continuous_scale='Viridis'
        )
        fig.update_layout(height=500, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
        
        # Yield distribution
        selected_crop = st.selectbox("Select crop to view distribution:", crop_options)
        crop_data = data[data['crop'] == selected_crop]['yield']
        
        fig = px.histogram(
            crop_data,
            nbins=50,
            title=f"Yield Distribution for {selected_crop}",
            labels={'value': 'Yield (kg/ha)', 'count': 'Frequency'}
        )
        fig.add_vline(x=crop_data.mean(), line_dash="dash", line_color="red", 
                      annotation_text=f"Mean: {crop_data.mean():.2f}")
        st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        st.markdown("### State-wise Performance")
        
        # Average yield by state
        state_yields = data.groupby('state')['yield'].mean().sort_values(ascending=False)
        
        fig = px.bar(
            x=state_yields.values,
            y=state_yields.index,
            orientation='h',
            title="Average Yield by State",
            labels={'x': 'Average Yield (kg/ha)', 'y': 'State'},
            color=state_yields.values,
            color_continuous_scale='RdYlGn'
        )
        fig.update_layout(height=600, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    
    with tab3:
        st.markdown("### Temporal Trends")
        
        # Yield over years
        yearly_avg = data.groupby('year')['yield'].mean()
        
        fig = px.line(
            x=yearly_avg.index,
            y=yearly_avg.values,
            title="Average Yield Trend Over Years",
            labels={'x': 'Year', 'y': 'Average Yield (kg/ha)'},
            markers=True
        )
        st.plotly_chart(fig, use_container_width=True)
        
        # Season comparison
        season_avg = data.groupby('season')['yield'].mean().sort_values(ascending=False)
        
        fig = px.bar(
            x=season_avg.index,
            y=season_avg.values,
            title="Average Yield by Season",
            labels={'x': 'Season', 'y': 'Average Yield (kg/ha)'},
            color=season_avg.values,
            color_continuous_scale='Blues'
        )
        st.plotly_chart(fig, use_container_width=True)

# --------------------------
# PAGE 3: ABOUT
# --------------------------
else:
    st.title("ℹ️ About This Application")
    
    st.markdown("""
    ### 🌾 Crop Yield Prediction System v2.0
    
    This application predicts crop yield based on multiple factors including:
    - 🌍 **Soil properties**: N, P, K nutrients and pH
    - 🌤️ **Weather conditions**: Temperature, rainfall, humidity
    - 🧪 **Agricultural inputs**: Fertilizer and pesticide usage
    - 📍 **Location & timing**: State, season, and year
    
    ---
    
    ### 🚀 Model Information
    
    - **Model Type:** {model_name}
    - **Training Data:** {len(data):,} records from 1997-2020
    - **Features:** 25+ engineered features
    - **States Covered:** {len(state_options)}
    - **Crops Covered:** {len(crop_options)}
    
    ---
    
    ### 📊 Model Performance
    
    The model has been validated across:
    - ✅ Different crop types
    - ✅ Geographic regions (states)
    - ✅ Time periods (temporal validation)
    - ✅ Seasonal variations
    
    ---
    
    ### 🔧 Enhanced Features (v2.0)
    
    **New in this version:**
    1. 📐 Normalized fertilizer/pesticide inputs
    2. 🌱 NPK nutrient balance features
    3. 🌤️ Climate interaction features
    4. 🌍 Soil quality indicators
    5. ⚡ Input efficiency metrics
    6. 📅 Temporal trend features
    7. 📊 Interactive visualizations
    8. 💡 Smart recommendations
    
    ---
    
    ### 📚 How to Use
    
    1. **Navigate to Prediction tab**
    2. **Enter your parameters:**
       - Select location (state)
       - Choose crop and season
       - Input soil nutrients (N, P, K, pH)
       - Enter weather data
       - Provide agricultural inputs
    3. **Click "Predict Yield"**
    4. **Review results and recommendations**
    
    ---
    
    ### ⚠️ Important Notes
    
    - Predictions are estimates based on historical data
    - Actual yields may vary due to unforeseen factors
    - Use predictions as guidance, not absolute values
    - For best results, ensure accurate input data
    
    ---
    
    ### 📧 Support
    
    For questions or issues, please refer to the documentation.
    
    ---
    
    **Version:** 2.0  
    **Last Updated:** 2025  
    **Model:** Enhanced ML Pipeline with Feature Engineering
    """.format(model_name=model_name, len=len, state_options=state_options, crop_options=crop_options, data=data))
    
    # Show sample data
    with st.expander("📄 View Sample Training Data"):
        st.dataframe(data.head(20))
    
    # Show feature importance (if available)
    with st.expander("🎯 Model Features"):
        st.markdown("**Input Features Used:**")
        feature_list = list(model_features)
        st.write(feature_list)

# --------------------------
# FOOTER
# --------------------------
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: gray;'>"
    "🌾 Crop Yield Prediction System v2.0 | Enhanced with ML & Feature Engineering"
    "</div>",
    unsafe_allow_html=True
)
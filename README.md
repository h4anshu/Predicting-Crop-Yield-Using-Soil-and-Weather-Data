# Crop Yield Prediction Project 🌾

This project is a comprehensive end-to-end machine learning solution for predicting crop yield. It utilizes a combination of agricultural, climatic, and soil data to train a robust model and provides a simple web interface for users to get instant predictions.

## 🚀 Overview

The goal of this project is to build a predictive model that can accurately forecast crop yield based on various environmental and agricultural factors. This can be an invaluable tool for farmers, agricultural scientists, and policymakers to make informed decisions.

The project encompasses:

- **Data Preprocessing and Merging**: Combining multiple datasets to create a unified view.
- **Machine Learning Model**: Training a Random Forest Regressor to predict crop yield.
- **Web Application**: A user-friendly interface built with Streamlit to serve the model.

## ✨ Features

- **Accurate Predictions**: Utilizes a highly accurate Random Forest model, fine-tuned for performance.
- **Comprehensive Data**: Incorporates data on crop type, weather, soil nutrients, and farming practices.
- **Interactive UI**: An easy-to-use Streamlit web application is developed to allow users to input specific parameters and obtain crop yield predictions along with recommendations for improving agricultural outcomes.

## 📊 Datasets Used

The model is trained on three key datasets:

1. **`crop_yield.csv`**: Contains historical data on crop production, including area, fertilizer usage, and pesticide usage.
2. **`state_weather_data_1997_2020.csv`**: Provides annual weather data, including average temperature, rainfall, and humidity.
3. **`State_soil_data.csv`**: Contains state-wise soil nutrient data, including Nitrogen (N), Phosphorus (P), Potassium (K), and pH levels.

## 🛠️ Technologies Used

- **Python**: The core programming language for the project.
- **Pandas**: For data manipulation and analysis.
- **Scikit-learn**: For building and evaluating the machine learning model.

⚙️ Installation
To run this project on your local machine, follow these steps:

Clone the repository:

Bash

git clone https://github.com/h4anshu/crop-yield-prediction.git
cd crop-yield-prediction


▶️ How to Run the Project
Train the Model:
Open and run the main.ipynb Jupyter Notebook. This will perform the data preprocessing, model training, and will save the trained model as crop_yield_model.pkl.

Launch the Web Application:
Run the following command in your terminal:
       "streamlit run app.py"
This will open the web application in your default browser.

📁 Project Structure
.
├── 📄 app.py                  # The Streamlit web application script
├── 📓 main.ipynb               # Jupyter Notebook for data processing and model training
├── 💾 crop_yield_model.pkl      # Saved trained model (generated after running main.ipynb)
├── 📊 data/
│   ├── crop_yield.csv
│   ├── india_state_weather_nasa_power_1997_2020.csv
│   └── State_soil_data.csv 
└── 📄 README.md                # Project documentation
- **Jupyter Notebook**: For model development and experimentation.
- **Streamlit**: For creating the web application.
- **Joblib**: For saving and loading the trained model.

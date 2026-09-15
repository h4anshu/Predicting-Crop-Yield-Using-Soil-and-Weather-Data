// Static seed data so the dropdowns and stat cards render on first paint instead of
// waiting on the Cloud Run backend (which cold-starts slowly).
// App.jsx still fetches the live values in the background and overwrites these, so a
// retrain that changes the crop list stays correct without touching this file.
// Regenerate with:  node check-constants.mjs   (it fails when these drift)
//
// Labels are stripped here. The source CSV pads them ('Rabi       ') but the v3 model
// is trained on the stripped forms, and an unstripped label one-hot encodes to all
// zeros -- silently dropping the category rather than raising.
// Coconut is absent on purpose: it is recorded in nuts/ha inside a tonnes/ha column,
// so v3 excludes it. See model_metrics.json -> data_quality.

export const API_BASE = 'https://agripredict-api-531174775648.europe-west1.run.app'

export const DEFAULT_OPTIONS = {
  states: [
    'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar',
    'Chhattisgarh', 'Delhi', 'Goa', 'Gujarat',
    'Haryana', 'Himachal Pradesh', 'Jammu and Kashmir', 'Jharkhand',
    'Karnataka', 'Kerala', 'Madhya Pradesh', 'Maharashtra',
    'Manipur', 'Meghalaya', 'Mizoram', 'Nagaland',
    'Odisha', 'Puducherry', 'Punjab', 'Sikkim',
    'Tamil Nadu', 'Telangana', 'Tripura', 'Uttar Pradesh',
    'Uttarakhand', 'West Bengal',
  ],
  seasons: [
    'Autumn', 'Kharif', 'Rabi', 'Summer',
    'Whole Year', 'Winter',
  ],
  crops: [
    'Arecanut', 'Arhar/Tur', 'Bajra', 'Banana',
    'Barley', 'Black pepper', 'Cardamom', 'Cashewnut',
    'Castor seed', 'Coriander', 'Cotton(lint)', 'Cowpea(Lobia)',
    'Dry chillies', 'Garlic', 'Ginger', 'Gram',
    'Groundnut', 'Guar seed', 'Horse-gram', 'Jowar',
    'Jute', 'Khesari', 'Linseed', 'Maize',
    'Masoor', 'Mesta', 'Moong(Green Gram)', 'Moth',
    'Niger seed', 'Oilseeds total', 'Onion', 'Other  Rabi pulses',
    'Other Cereals', 'Other Kharif pulses', 'Other Summer Pulses', 'Peas & beans (Pulses)',
    'Potato', 'Ragi', 'Rapeseed &Mustard', 'Rice',
    'Safflower', 'Sannhamp', 'Sesamum', 'Small millets',
    'Soyabean', 'Sugarcane', 'Sunflower', 'Sweet potato',
    'Tapioca', 'Tobacco', 'Turmeric', 'Urad',
    'Wheat', 'other oilseeds',
  ],
  year_min: 1997,
  year_max: 2020,
}

export const DEFAULT_STATS = {
  total_records: 19689,
  crops_covered: 54,
  states_covered: 30,
  model_accuracy: '92%',
  model_accuracy_core: '81%',
  model_mae: 1.0014,
  year_min: 1997,
  year_max: 2020,
  years_covered: '1997 - 2020',
}

// Per-state soil and climate. v3 does not take `state` as a feature, so selecting a
// state has to load its real agronomic values or the control does nothing at all.
// The API ships the authoritative copy in /api/options.state_defaults; this is the
// first-paint fallback.
export const STATE_DEFAULTS = {
  "Andhra Pradesh": {
    "N": 78,
    "P": 45,
    "K": 22,
    "pH": 6.8,
    "avg_temp_c": 28.2,
    "total_rainfall_mm": 1027.8,
    "avg_humidity_percent": 71.25,
    "fertilizer_per_ha": 171.73,
    "pesticide_per_ha": 0.37
  },
  "Arunachal Pradesh": {
    "N": 55,
    "P": 15,
    "K": 35,
    "pH": 5.5,
    "avg_temp_c": 22.52,
    "total_rainfall_mm": 2411.52,
    "avg_humidity_percent": 78.3,
    "fertilizer_per_ha": 171.52,
    "pesticide_per_ha": 0.37
  },
  "Assam": {
    "N": 60,
    "P": 18,
    "K": 38,
    "pH": 5.8,
    "avg_temp_c": 23.09,
    "total_rainfall_mm": 2368.95,
    "avg_humidity_percent": 78.3,
    "fertilizer_per_ha": 171.73,
    "pesticide_per_ha": 0.37
  },
  "Bihar": {
    "N": 85,
    "P": 30,
    "K": 25,
    "pH": 7.2,
    "avg_temp_c": 26.61,
    "total_rainfall_mm": 921.63,
    "avg_humidity_percent": 57.02,
    "fertilizer_per_ha": 171.75,
    "pesticide_per_ha": 0.37
  },
  "Chhattisgarh": {
    "N": 70,
    "P": 35,
    "K": 20,
    "pH": 6.5,
    "avg_temp_c": 26.33,
    "total_rainfall_mm": 1567.15,
    "avg_humidity_percent": 60.28,
    "fertilizer_per_ha": 171.76,
    "pesticide_per_ha": 0.37
  },
  "Delhi": {
    "N": 90,
    "P": 40,
    "K": 30,
    "pH": 7.5,
    "avg_temp_c": 25.47,
    "total_rainfall_mm": 618.71,
    "avg_humidity_percent": 49.1,
    "fertilizer_per_ha": 171.75,
    "pesticide_per_ha": 0.37
  },
  "Goa": {
    "N": 65,
    "P": 25,
    "K": 45,
    "pH": 6.2,
    "avg_temp_c": 27.55,
    "total_rainfall_mm": 3627.84,
    "avg_humidity_percent": 74.47,
    "fertilizer_per_ha": 171.51,
    "pesticide_per_ha": 0.37
  },
  "Gujarat": {
    "N": 75,
    "P": 38,
    "K": 28,
    "pH": 7.8,
    "avg_temp_c": 27.13,
    "total_rainfall_mm": 977.56,
    "avg_humidity_percent": 55.15,
    "fertilizer_per_ha": 171.76,
    "pesticide_per_ha": 0.37
  },
  "Haryana": {
    "N": 130,
    "P": 48,
    "K": 35,
    "pH": 7.9,
    "avg_temp_c": 23.3,
    "total_rainfall_mm": 1138.97,
    "avg_humidity_percent": 55.64,
    "fertilizer_per_ha": 171.75,
    "pesticide_per_ha": 0.37
  },
  "Himachal Pradesh": {
    "N": 60,
    "P": 20,
    "K": 40,
    "pH": 6.0,
    "avg_temp_c": 20.23,
    "total_rainfall_mm": 1189.51,
    "avg_humidity_percent": 58.7,
    "fertilizer_per_ha": 170.17,
    "pesticide_per_ha": 0.37
  },
  "Jammu and Kashmir": {
    "N": 70,
    "P": 25,
    "K": 42,
    "pH": 6.7,
    "avg_temp_c": 7.64,
    "total_rainfall_mm": 1323.46,
    "avg_humidity_percent": 67.07,
    "fertilizer_per_ha": 171.76,
    "pesticide_per_ha": 0.37
  },
  "Jharkhand": {
    "N": 68,
    "P": 22,
    "K": 30,
    "pH": 6.1,
    "avg_temp_c": 23.55,
    "total_rainfall_mm": 1350.34,
    "avg_humidity_percent": 63.78,
    "fertilizer_per_ha": 171.76,
    "pesticide_per_ha": 0.37
  },
  "Karnataka": {
    "N": 72,
    "P": 42,
    "K": 25,
    "pH": 6.9,
    "avg_temp_c": 24.57,
    "total_rainfall_mm": 818.07,
    "avg_humidity_percent": 65.92,
    "fertilizer_per_ha": 171.76,
    "pesticide_per_ha": 0.37
  },
  "Kerala": {
    "N": 65,
    "P": 28,
    "K": 50,
    "pH": 5.7,
    "avg_temp_c": 27.57,
    "total_rainfall_mm": 1778.18,
    "avg_humidity_percent": 78.55,
    "fertilizer_per_ha": 171.76,
    "pesticide_per_ha": 0.37
  },
  "Madhya Pradesh": {
    "N": 70,
    "P": 40,
    "K": 20,
    "pH": 7.4,
    "avg_temp_c": 25.11,
    "total_rainfall_mm": 1870.12,
    "avg_humidity_percent": 56.0,
    "fertilizer_per_ha": 171.75,
    "pesticide_per_ha": 0.37
  },
  "Maharashtra": {
    "N": 75,
    "P": 43,
    "K": 26,
    "pH": 7.1,
    "avg_temp_c": 26.96,
    "total_rainfall_mm": 3387.29,
    "avg_humidity_percent": 68.18,
    "fertilizer_per_ha": 171.76,
    "pesticide_per_ha": 0.37
  },
  "Manipur": {
    "N": 58,
    "P": 17,
    "K": 37,
    "pH": 5.9,
    "avg_temp_c": 19.92,
    "total_rainfall_mm": 1486.52,
    "avg_humidity_percent": 80.21,
    "fertilizer_per_ha": 162.13,
    "pesticide_per_ha": 0.35
  },
  "Meghalaya": {
    "N": 52,
    "P": 16,
    "K": 33,
    "pH": 5.6,
    "avg_temp_c": 18.07,
    "total_rainfall_mm": 4360.57,
    "avg_humidity_percent": 82.43,
    "fertilizer_per_ha": 171.7,
    "pesticide_per_ha": 0.37
  },
  "Mizoram": {
    "N": 54,
    "P": 15,
    "K": 34,
    "pH": 5.7,
    "avg_temp_c": 22.84,
    "total_rainfall_mm": 3082.44,
    "avg_humidity_percent": 80.4,
    "fertilizer_per_ha": 164.6,
    "pesticide_per_ha": 0.35
  },
  "Nagaland": {
    "N": 56,
    "P": 16,
    "K": 36,
    "pH": 5.8,
    "avg_temp_c": 18.3,
    "total_rainfall_mm": 1569.19,
    "avg_humidity_percent": 76.56,
    "fertilizer_per_ha": 171.71,
    "pesticide_per_ha": 0.37
  },
  "Odisha": {
    "N": 67,
    "P": 26,
    "K": 32,
    "pH": 6.3,
    "avg_temp_c": 26.42,
    "total_rainfall_mm": 1686.78,
    "avg_humidity_percent": 74.06,
    "fertilizer_per_ha": 170.32,
    "pesticide_per_ha": 0.37
  },
  "Puducherry": {
    "N": 88,
    "P": 55,
    "K": 40,
    "pH": 7.0,
    "avg_temp_c": 28.41,
    "total_rainfall_mm": 1060.94,
    "avg_humidity_percent": 75.48,
    "fertilizer_per_ha": 168.52,
    "pesticide_per_ha": 0.36
  },
  "Punjab": {
    "N": 150,
    "P": 50,
    "K": 40,
    "pH": 8.0,
    "avg_temp_c": 23.3,
    "total_rainfall_mm": 1138.97,
    "avg_humidity_percent": 55.64,
    "fertilizer_per_ha": 171.42,
    "pesticide_per_ha": 0.37
  },
  "Sikkim": {
    "N": 50,
    "P": 20,
    "K": 30,
    "pH": 5.5,
    "avg_temp_c": 7.21,
    "total_rainfall_mm": 1606.09,
    "avg_humidity_percent": 78.68,
    "fertilizer_per_ha": 171.7,
    "pesticide_per_ha": 0.37
  },
  "Tamil Nadu": {
    "N": 80,
    "P": 38,
    "K": 30,
    "pH": 6.6,
    "avg_temp_c": 28.36,
    "total_rainfall_mm": 1207.03,
    "avg_humidity_percent": 72.52,
    "fertilizer_per_ha": 171.76,
    "pesticide_per_ha": 0.37
  },
  "Telangana": {
    "N": 77,
    "P": 48,
    "K": 24,
    "pH": 7.0,
    "avg_temp_c": 26.62,
    "total_rainfall_mm": 753.33,
    "avg_humidity_percent": 60.74,
    "fertilizer_per_ha": 171.73,
    "pesticide_per_ha": 0.37
  },
  "Tripura": {
    "N": 62,
    "P": 20,
    "K": 35,
    "pH": 5.9,
    "avg_temp_c": 25.35,
    "total_rainfall_mm": 3054.79,
    "avg_humidity_percent": 77.35,
    "fertilizer_per_ha": 171.53,
    "pesticide_per_ha": 0.37
  },
  "Uttar Pradesh": {
    "N": 120,
    "P": 45,
    "K": 35,
    "pH": 7.6,
    "avg_temp_c": 25.4,
    "total_rainfall_mm": 1300.6,
    "avg_humidity_percent": 58.93,
    "fertilizer_per_ha": 171.76,
    "pesticide_per_ha": 0.37
  },
  "Uttarakhand": {
    "N": 80,
    "P": 24,
    "K": 38,
    "pH": 6.4,
    "avg_temp_c": 17.09,
    "total_rainfall_mm": 1333.54,
    "avg_humidity_percent": 61.69,
    "fertilizer_per_ha": 193.6,
    "pesticide_per_ha": 0.37
  },
  "West Bengal": {
    "N": 85,
    "P": 40,
    "K": 45,
    "pH": 6.2,
    "avg_temp_c": 26.15,
    "total_rainfall_mm": 1624.7,
    "avg_humidity_percent": 73.63,
    "fertilizer_per_ha": 171.72,
    "pesticide_per_ha": 0.37
  }
}

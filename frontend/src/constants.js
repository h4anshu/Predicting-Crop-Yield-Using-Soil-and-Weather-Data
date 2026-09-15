// Static seed data so the dropdowns and stat cards render on first paint instead of
// waiting on the Cloud Run backend (which cold-starts slowly: it loads a 35MB model).
// App.jsx still fetches the live values in the background and overwrites these,
// so re-training with new data stays correct without touching this file.
// NOTE: season and crop strings keep their trailing spaces on purpose — the model
// was trained on those exact labels and /api/predict matches them verbatim.

export const API_BASE = 'https://agripredict-api-531174775648.europe-west1.run.app'

export const DEFAULT_OPTIONS = {
  states: [
    'Andhra Pradesh', 'Arunachal Pradesh', 'Assam', 'Bihar', 'Chhattisgarh',
    'Delhi', 'Goa', 'Gujarat', 'Haryana', 'Himachal Pradesh',
    'Jammu and Kashmir', 'Jharkhand', 'Karnataka', 'Kerala', 'Madhya Pradesh',
    'Maharashtra', 'Manipur', 'Meghalaya', 'Mizoram', 'Nagaland',
    'Odisha', 'Puducherry', 'Punjab', 'Sikkim', 'Tamil Nadu',
    'Telangana', 'Tripura', 'Uttar Pradesh', 'Uttarakhand', 'West Bengal',
  ],
  seasons: [
    'Autumn     ', 'Kharif     ', 'Rabi       ',
    'Summer     ', 'Whole Year ', 'Winter     ',
  ],
  crops: [
    'Arecanut', 'Arhar/Tur', 'Bajra', 'Banana', 'Barley',
    'Black pepper', 'Cardamom', 'Cashewnut', 'Castor seed', 'Coconut ',
    'Coriander', 'Cotton(lint)', 'Cowpea(Lobia)', 'Dry chillies', 'Garlic',
    'Ginger', 'Gram', 'Groundnut', 'Guar seed', 'Horse-gram',
    'Jowar', 'Jute', 'Khesari', 'Linseed', 'Maize',
    'Masoor', 'Mesta', 'Moong(Green Gram)', 'Moth', 'Niger seed',
    'Oilseeds total', 'Onion', 'Other  Rabi pulses', 'Other Cereals',
    'Other Kharif pulses', 'Other Summer Pulses', 'Peas & beans (Pulses)',
    'Potato', 'Ragi', 'Rapeseed &Mustard', 'Rice', 'Safflower',
    'Sannhamp', 'Sesamum', 'Small millets', 'Soyabean', 'Sugarcane',
    'Sunflower', 'Sweet potato', 'Tapioca', 'Tobacco', 'Turmeric',
    'Urad', 'Wheat', 'other oilseeds',
  ],
  year_min: 1997,
  year_max: 2020,
}

export const DEFAULT_STATS = {
  total_records: 19689,
  crops_covered: 55,
  states_covered: 30,
  model_accuracy: '95%',
  year_min: 1997,
  year_max: 2020,
  years_covered: '1997 - 2020',
}

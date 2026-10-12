// Seed data so the dropdowns and the dashboard render on first paint instead of waiting on the Cloud Run backend (which
// cold-starts slowly). App.jsx still fetches the live values in the background and overwrites these.
// Regenerate by copying the live /api/options and /api/stats `dataset`; `node check-constants.mjs` fails when they drift.
// The outlook summary is deliberately not seeded: it changes with every rebuild and the pages handle its absence.

// Point the app at a local API with VITE_API_BASE=http://localhost:8000 (frontend/.env.local).
// `import.meta.env` is undefined under plain node, which check-constants.mjs also uses.
export const API_BASE = import.meta.env?.VITE_API_BASE
  ?? 'https://agripredict-api-531174775648.europe-west1.run.app'

export const DEFAULT_OPTIONS = {
  "states": [
    "Andaman And Nicobar Islands",
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chandigarh",
    "Chhattisgarh",
    "Delhi",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jammu And Kashmir",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Ladakh",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Puducherry",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "The Dadra And Nagar Haveli And Daman And Diu",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal"
  ],
  "seasons": [
    "Kharif",
    "Rabi",
    "Summer",
    "Whole Year"
  ],
  "crops": [
    "Arcanut (Processed)",
    "Arecanut",
    "Arhar/Tur",
    "Atcanut (Raw)",
    "Bajra",
    "Banana",
    "Barley",
    "Bhindi",
    "Bitter Gourd",
    "Black Pepper",
    "Bottle Gourd",
    "Brinjal",
    "Cabbage",
    "Cardamom",
    "Carrot",
    "Cashewnut",
    "Cashewnut Processed",
    "Cashewnut Raw",
    "Castor Seed",
    "Cauliflower",
    "Citrus Fruit",
    "Coconut",
    "Coffee",
    "Colocosia",
    "Cond-Spcs Other",
    "Coriander",
    "Cotton",
    "Cotton(Lint)",
    "Cowpea(Lobia)",
    "Drum Stick",
    "Dry Chillies",
    "Dry Ginger",
    "Garlic",
    "Ginger",
    "Gram",
    "Grapes",
    "Groundnut",
    "Guar Seed",
    "Horse-Gram",
    "Jack Fruit",
    "Jobster",
    "Jowar",
    "Jute",
    "Jute & Mesta",
    "Kapas",
    "Khesari",
    "Korra",
    "Lemon",
    "Linseed",
    "Maize",
    "Mango",
    "Masoor",
    "Mesta",
    "Moong(Green Gram)",
    "Moth",
    "Niger Seed",
    "Onion",
    "Orange",
    "Other Cereals",
    "Other Fresh Fruits",
    "Other Kharif Pulses",
    "Other Misc. Pulses",
    "Other Oilseeds",
    "Other Pulses",
    "Other Rabi Pulses",
    "Other Summer Pulses",
    "Other Vegetables",
    "Papaya",
    "Peas & Beans (Pulses)",
    "Perilla",
    "Pineapple",
    "Pome Fruit",
    "Pome Granet",
    "Potato",
    "Ragi",
    "Rajmash Kholar",
    "Rapeseed &Mustard",
    "Redish",
    "Rice",
    "Ricebean (Nagadal)",
    "Rubber",
    "Safflower",
    "Samai",
    "Sannhamp",
    "Sapota",
    "Sesamum",
    "Small Millets",
    "Soyabean",
    "Sugarcane",
    "Sunflower",
    "Sweet Potato",
    "Tapioca",
    "Tea",
    "Tobacco",
    "Tomato",
    "Turmeric",
    "Turnip",
    "Urad",
    "Varagu",
    "Wheat"
  ]
}

export const DEFAULT_STATS = {
  dataset: {
    "rows": 441437,
    "district_rows": 441075,
    "state_only_rows": 362,
    "columns": 102,
    "districts": 752,
    "states_uts": 35,
    "crops": 100,
    "crops_listed": 118,
    "year_min": 1997,
    "year_max": 2024,
    "sources": "DES district area-production-yield (APY, to 2022-23) and UPAG (2013-14 to 2024-25), the original state-level dataset, IMD gridded rain and temperature, NASA POWER, MODIS NDVI/EVI (Google Earth Engine), Soil Health Card, ICRISAT",
    "groups": [
      {
        "group": "identifier",
        "columns": 14,
        "filled_pct": 100.0
      },
      {
        "group": "yield (value at this row's level)",
        "columns": 5,
        "filled_pct": 100.0
      },
      {
        "group": "state-level (original dataset)",
        "columns": 12,
        "filled_pct": 73.7
      },
      {
        "group": "weather, fixed season window",
        "columns": 10,
        "filled_pct": 97.8
      },
      {
        "group": "weather, planting-to-harvest window",
        "columns": 12,
        "filled_pct": 10.2
      },
      {
        "group": "satellite NDVI/EVI",
        "columns": 20,
        "filled_pct": 55.6
      },
      {
        "group": "soil (Soil Health Card)",
        "columns": 22,
        "filled_pct": 98.8
      },
      {
        "group": "ICRISAT attributes",
        "columns": 7,
        "filled_pct": 82.1
      }
    ],
    "state_vs_district": {
      "yield_within_2pct": 93.4,
      "yield_within_10pct": 97.0,
      "district_rows_with_state_values_pct": 70.3
    }
  },
  outlook: null,
}

import { useState, useEffect, useRef, useCallback } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from 'recharts'
import GaugeChart from './GaugeChart'
import farmerImg from '../assets/farmer.png'

const API_BASE = 'https://predicting-crop-yield-using-soil-and-weather-dat-production.up.railway.app'

const INPUT_TABS = [
  { id: 'location', icon: '📍', label: 'Location & Crop' },
  { id: 'soil', icon: '🌱', label: 'Soil' },
  { id: 'climate', icon: '🌤️', label: 'Climate' },
  { id: 'farm', icon: '🧪', label: 'Farm Inputs' },
]

const SCORE_COLORS = {
  soil_health: '#1f7a3d',
  climate_suitability: '#2c6cb0',
  input_efficiency: '#b8731d',
  npk_balance: '#6b46a8',
}

const SCORE_ICONS = {
  soil_health: '🌱',
  climate_suitability: '🌧️',
  input_efficiency: '⚖️',
  npk_balance: '🧪',
}

const SCORE_LABELS = {
  soil_health: 'Soil Health Score',
  climate_suitability: 'Climate Suitability',
  input_efficiency: 'Input Efficiency',
  npk_balance: 'NPK Balance',
}

const REC_ICONS = { ok: '✓', warn: '!', info: 'i' }

function getRatingColor(rating) {
  if (!rating) return '#8a9388'
  const r = rating.toLowerCase()
  if (r === 'excellent') return '#1f7a3d'
  if (r === 'good') return '#3b8c5a'
  if (r === 'moderate') return '#b8731d'
  if (r === 'below avg') return '#c8843a'
  return '#a82828'
}

export default function Dashboard({ options, stats }) {
  const [activeTab, setActiveTab] = useState('location')
  const [state, setState] = useState('')
  const [year, setYear] = useState(2020)
  const [crop, setCrop] = useState('')
  const [season, setSeason] = useState('')
  const [area, setArea] = useState(2.50)
  const [N, setN] = useState(78)
  const [P, setP] = useState(45)
  const [K, setK] = useState(22)
  const [pH, setPH] = useState(6.8)
  const [temp, setTemp] = useState(28.2)
  const [rainfall, setRainfall] = useState(1191.1)
  const [humidity, setHumidity] = useState(69.6)
  const [fertilizer, setFertilizer] = useState(250.5)
  const [pesticide, setPesticide] = useState(1.25)

  const [result, setResult] = useState(null)
  const [historical, setHistorical] = useState(null)
  const [loading, setLoading] = useState(false)
  const [needsUpdate, setNeedsUpdate] = useState(false)

  // Debounce timer ref
  const debounceRef = useRef(null)

  // Initialize defaults
  useEffect(() => {
    if (options) {
      if (options.states?.length) setState(options.states[0])
      if (options.crops?.length) setCrop(options.crops[0])
      if (options.seasons?.length) setSeason(options.seasons[0])
      if (options.year_max) setYear(options.year_max)
    }
  }, [options])

  // Soil health preview (live)
  const soilPreview = (() => {
    const npk = N + P + K
    const npkScore = Math.min(100, (npk / 180) * 100)
    const phScore = (pH >= 6.0 && pH <= 7.5) ? 100 : Math.max(0, 100 - Math.abs(pH - 6.75) * 30)
    const score = Math.round(0.65 * npkScore + 0.35 * phScore)
    let label = 'Poor'
    if (score >= 80) label = 'Excellent'
    else if (score >= 65) label = 'Good'
    else if (score >= 50) label = 'Moderate'
    else if (score >= 30) label = 'Below avg'
    return { score, label }
  })()

  // Predict function
  const doPredict = useCallback(async () => {
    if (!crop || !state || !season) return
    setLoading(true)
    setNeedsUpdate(false)
    try {
      const res = await fetch(`${API_BASE}/api/predict`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          state, year, crop, season, N, P, K, pH,
          avg_temp_c: temp,
          total_rainfall_mm: rainfall,
          avg_humidity_percent: humidity,
          fertilizer_per_ha: fertilizer,
          pesticide_per_ha: pesticide,
          area,
        }),
      })
      const data = await res.json()
      setResult(data)
    } catch (e) {
      console.error('Prediction failed:', e)
    }
    setLoading(false)
  }, [state, year, crop, season, N, P, K, pH, temp, rainfall, humidity, fertilizer, pesticide, area])

  // Auto-predict with debounce when ANY input changes
  useEffect(() => {
    if (!crop || !state || !season) return

    // Show "needs update" hint immediately
    if (result) setNeedsUpdate(true)

    // Debounce the actual API call
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      doPredict()
    }, 600)

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [state, year, crop, season, N, P, K, pH, temp, rainfall, humidity, fertilizer, pesticide, area])

  // Fetch historical data when crop/state changes
  useEffect(() => {
    if (crop && state) {
      fetch(`${API_BASE}/api/historical?crop=${encodeURIComponent(crop)}&state=${encodeURIComponent(state)}`)
        .then(r => r.json())
        .then(d => setHistorical(d))
        .catch(() => {})
    }
  }, [crop, state])

  const today = new Date()
  const formattedDate = today.toLocaleDateString('en-IN', {
    day: '2-digit', month: 'long', year: 'numeric',
  })

  const chartData = historical
    ? historical.years.map((y, i) => ({ year: y, yield: historical.values[i] }))
    : []

  const badgeClass = result?.badge?.includes('HIGH') ? 'high'
    : result?.badge?.includes('LOW') ? 'low' : 'normal'

  return (
    <div className="main-content">
      <div className="main-content-inner">
        {/* ── HEADER ── */}
        <div className="page-header fade-in">
          <div className="page-header-left">
            <span className="page-header-icon">🌾</span>
            <div>
              <h1 className="page-header-title">Crop Yield Prediction</h1>
              <div className="page-header-subtitle">
                Predict crop yield using weather, soil and farm input intelligence
              </div>
            </div>
          </div>
          <div className="page-header-right">
            <div className="date-pill">📅 {formattedDate}</div>
            <button className="btn-refresh" onClick={doPredict}>
              🔄 Refresh Data
            </button>
          </div>
        </div>

        {/* ── KPI CARDS ── */}
        <div className="kpi-row">
          <div className="kpi-card fade-in fade-in-delay-1">
            <div className="kpi-icon green">🌱</div>
            <div className="kpi-content">
              <div className="kpi-label">Total Records</div>
              <div className="kpi-value">{stats?.total_records?.toLocaleString() || '19,689'}</div>
              <div className="kpi-sub">Historical Data Points</div>
            </div>
          </div>
          <div className="kpi-card fade-in fade-in-delay-2">
            <div className="kpi-icon teal">🌾</div>
            <div className="kpi-content">
              <div className="kpi-label">Crops Covered</div>
              <div className="kpi-value">{stats?.crops_covered || 55}</div>
              <div className="kpi-sub">Different Crops</div>
            </div>
          </div>
          <div className="kpi-card fade-in fade-in-delay-3">
            <div className="kpi-icon purple">🗺️</div>
            <div className="kpi-content">
              <div className="kpi-label">States Covered</div>
              <div className="kpi-value">{stats?.states_covered || 30}</div>
              <div className="kpi-sub">Indian States</div>
            </div>
          </div>
          <div className="kpi-card fade-in fade-in-delay-4">
            <div className="kpi-icon amber">🎯</div>
            <div className="kpi-content">
              <div className="kpi-label">Model Accuracy</div>
              <div className="kpi-value">95%</div>
              <div className="kpi-sub">R² Score</div>
            </div>
          </div>
          <div className="kpi-card fade-in fade-in-delay-5">
            <div className="kpi-icon blue">📅</div>
            <div className="kpi-content">
              <div className="kpi-label">Data Range</div>
              <div className="kpi-value">{stats?.years_covered || '1997 - 2020'}</div>
              <div className="kpi-sub">24 Years</div>
            </div>
          </div>
        </div>

        {/* ── MAIN 2-COLUMN GRID ── */}
        <div className="main-grid">
          {/* LEFT: Tabbed Input Form */}
          <div className="section-card fade-in fade-in-delay-1">
            <div className="section-title">🎛️ Input Parameters</div>

            <div className="input-tabs">
              {INPUT_TABS.map(tab => (
                <button
                  key={tab.id}
                  className={`input-tab ${activeTab === tab.id ? 'active' : ''}`}
                  onClick={() => setActiveTab(tab.id)}
                >
                  {tab.icon} {tab.label}
                </button>
              ))}
            </div>

            {/* Tab: Location & Crop */}
            {activeTab === 'location' && (
              <div className="tab-content" key="location">
                <div className="tab-helper">Select your geographic region, growing season, and target crop.</div>
                <div className="input-row cols-2">
                  <div className="form-field">
                    <label>State</label>
                    <select value={state} onChange={e => setState(e.target.value)}>
                      {options?.states?.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </div>
                  <div className="form-field">
                    <label>Year</label>
                    <select value={year} onChange={e => setYear(Number(e.target.value))}>
                      {options && Array.from(
                        { length: (options.year_max + 5) - options.year_min + 1 },
                        (_, i) => options.year_min + i
                      ).map(y => <option key={y} value={y}>{y}</option>)}
                    </select>
                  </div>
                </div>
                <div className="input-row cols-3">
                  <div className="form-field">
                    <label>Crop</label>
                    <select value={crop} onChange={e => setCrop(e.target.value)}>
                      {options?.crops?.map(c => <option key={c} value={c}>{c}</option>)}
                    </select>
                  </div>
                  <div className="form-field">
                    <label>Season</label>
                    <select value={season} onChange={e => setSeason(e.target.value)}>
                      {options?.seasons?.map(s => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </div>
                  <div className="form-field">
                    <label>Area (Hectares)</label>
                    <input type="number" value={area} onChange={e => setArea(Number(e.target.value))} step="0.1" min="0" />
                  </div>
                </div>
              </div>
            )}

            {/* Tab: Soil */}
            {activeTab === 'soil' && (
              <div className="tab-content" key="soil">
                <div className="tab-helper">Enter your soil test results. Typical Indian soil: N 50–100, P 15–45, K 20–50 kg/ha.</div>
                <div className="input-row cols-3">
                  <div className="form-field">
                    <label>Nitrogen (N) kg/ha</label>
                    <input type="number" value={N} onChange={e => setN(Number(e.target.value))} step="1" min="0" max="200" />
                  </div>
                  <div className="form-field">
                    <label>Phosphorus (P) kg/ha</label>
                    <input type="number" value={P} onChange={e => setP(Number(e.target.value))} step="1" min="0" max="100" />
                  </div>
                  <div className="form-field">
                    <label>Potassium (K) kg/ha</label>
                    <input type="number" value={K} onChange={e => setK(Number(e.target.value))} step="1" min="0" max="100" />
                  </div>
                </div>
                <div className="input-row cols-2">
                  <div className="form-field">
                    <label>pH Value</label>
                    <input type="number" value={pH} onChange={e => setPH(Number(e.target.value))} step="0.1" min="4" max="9" />
                  </div>
                  <div className="form-field">
                    <div className="fertility-preview-label">Soil Fertility Score</div>
                    <div className="fertility-preview">
                      <div className="fertility-value">{soilPreview.score} / 100</div>
                      <div
                        className="fertility-badge"
                        style={{
                          background: getRatingColor(soilPreview.label) + '18',
                          color: getRatingColor(soilPreview.label),
                        }}
                      >
                        {soilPreview.label}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Tab: Climate */}
            {activeTab === 'climate' && (
              <div className="tab-content" key="climate">
                <div className="tab-helper">Enter average climate conditions for the growing season. Ideal: Temp 22–30°C, Rainfall 800–2000mm.</div>
                <div className="input-row cols-3">
                  <div className="form-field">
                    <label>Avg Temperature (°C)</label>
                    <input type="number" value={temp} onChange={e => setTemp(Number(e.target.value))} step="0.1" min="5" max="45" />
                  </div>
                  <div className="form-field">
                    <label>Rainfall (mm)</label>
                    <input type="number" value={rainfall} onChange={e => setRainfall(Number(e.target.value))} step="10" min="0" max="5000" />
                  </div>
                  <div className="form-field">
                    <label>Humidity (%)</label>
                    <input type="number" value={humidity} onChange={e => setHumidity(Number(e.target.value))} step="0.5" min="0" max="100" />
                  </div>
                </div>
              </div>
            )}

            {/* Tab: Farm Inputs */}
            {activeTab === 'farm' && (
              <div className="tab-content" key="farm">
                <div className="tab-helper">Enter fertilizer and pesticide usage. Ideal: Fertilizer 100–250 kg/ha, Pesticide 1–5 kg/ha.</div>
                <div className="input-row cols-2">
                  <div className="form-field">
                    <label>Fertilizer (kg/ha)</label>
                    <input type="number" value={fertilizer} onChange={e => setFertilizer(Number(e.target.value))} step="1" min="0" max="500" />
                  </div>
                  <div className="form-field">
                    <label>Pesticide (kg/ha)</label>
                    <input type="number" value={pesticide} onChange={e => setPesticide(Number(e.target.value))} step="0.05" min="0" max="20" />
                  </div>
                </div>
              </div>
            )}

            <button className="btn-predict" onClick={doPredict} disabled={loading}>
              {loading ? '⏳ Predicting...' : '✨ Predict Yield'}
            </button>
            {needsUpdate && !loading && (
              <div className="update-hint">⚡ Auto-updating prediction...</div>
            )}
          </div>

          {/* RIGHT: Prediction Result */}
          <div className="result-section">
            <div className="section-card fade-in fade-in-delay-2">
              <div className="section-title">📈 Prediction Result</div>
              {result ? (
                <div className="predict-card">
                  <div className="predict-label">Expected Yield 🌱</div>
                  <div className="predict-value-row">
                    <span className="predict-value">{result.prediction.toFixed(2)}</span>
                    <span className="predict-plant-icon">🌿</span>
                  </div>
                  <div className="predict-unit">{result.unit}</div>
                  <div className={`predict-badge ${badgeClass}`}>
                    {result.badge?.includes('HIGH') ? '🌟' : result.badge?.includes('LOW') ? '⚠' : '✓'} {result.badge}
                  </div>
                  <div className="compare-box">
                    <div className="compare-label">Compared to historical average</div>
                    <div className={`compare-value ${result.diff_pct < 0 ? 'negative' : ''}`}>
                      {result.diff_pct >= 0 ? '+' : ''}{result.diff_pct}%
                    </div>
                    <div className="compare-sub">
                      {result.diff_pct >= 0 ? 'Above' : 'Below'} Average ({result.avg_yield} {result.unit})
                    </div>
                  </div>
                  <div className="confidence-row">
                    <span>Model Confidence ⓘ</span>
                    <span className="confidence-value">{result.confidence}%</span>
                  </div>
                  <div className="confidence-bar">
                    <div className="confidence-bar-fill" style={{ width: `${result.confidence}%` }} />
                  </div>
                </div>
              ) : (
                <div className="empty-state">
                  <div className="empty-state-icon">📊</div>
                  <div className="empty-state-text">Prediction will appear here automatically</div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ── HISTORICAL CHART (Full Width) ── */}
        <div className="chart-card fade-in fade-in-delay-3" style={{ marginBottom: '1.6rem' }}>
          <div className="section-title">📊 Historical Yield Trend</div>
          <div className="chart-controls">
            <div className="chart-control-group">
              <span className="chart-control-label">Metric</span>
              <select className="chart-control-select">
                <option>Yield ({historical?.unit || 't/ha'})</option>
              </select>
            </div>
            <div style={{ flex: 1 }} />
            <div className="chart-control-group">
              <span className="chart-control-label">View</span>
              <select className="chart-control-select">
                <option>Line Chart</option>
              </select>
            </div>
          </div>
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={280}>
              <AreaChart data={chartData} margin={{ top: 5, right: 15, left: 5, bottom: 5 }}>
                <defs>
                  <linearGradient id="yieldGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#1f7a3d" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="#1f7a3d" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis
                  dataKey="year"
                  tick={{ fontSize: 13, fill: '#8a9388' }}
                  axisLine={{ stroke: '#e8ede5' }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 13, fill: '#8a9388' }}
                  axisLine={{ stroke: '#e8ede5' }}
                  tickLine={false}
                  label={{ value: `Yield (${historical?.unit || 't/ha'})`, angle: -90, position: 'insideLeft', fontSize: 13, fill: '#8a9388' }}
                />
                <Tooltip
                  contentStyle={{
                    background: '#fff',
                    border: '1px solid #e8ede5',
                    borderRadius: 10,
                    fontSize: 14,
                    fontFamily: 'Inter',
                    boxShadow: '0 6px 16px rgba(0,0,0,0.1)',
                  }}
                  formatter={(v) => [`${v.toFixed(2)} ${historical?.unit || 't/ha'}`, 'Yield']}
                />
                <Area
                  type="monotone"
                  dataKey="yield"
                  stroke="#1f7a3d"
                  strokeWidth={2.5}
                  fill="url(#yieldGrad)"
                  dot={{ r: 5, fill: '#1f7a3d', stroke: '#fff', strokeWidth: 2 }}
                  activeDot={{ r: 7, fill: '#1f7a3d', stroke: '#fff', strokeWidth: 2 }}
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="empty-state">
              <div className="empty-state-icon">📈</div>
              <div className="empty-state-text">Loading chart data...</div>
            </div>
          )}
          {historical && (
            <div className="chart-summary">
              <b>{historical.label}</b> · Average Yield ({historical.years?.[0]}–{historical.years?.[historical.years.length - 1]}): {historical.avg} {historical.unit}
            </div>
          )}
        </div>

        {/* ── SCORE GAUGES ── */}
        <div className="gauges-row">
          {result?.scores ? (
            Object.entries(result.scores).map(([key, s]) => (
              <div className="gauge-card fade-in" key={key}>
                <div className="gauge-card-title">
                  {SCORE_ICONS[key]} {SCORE_LABELS[key]}
                </div>
                <GaugeChart score={s.value} color={SCORE_COLORS[key]} size={120} />
                <div className="gauge-rating" style={{ color: getRatingColor(s.rating) }}>
                  {s.rating}
                </div>
                <div className="gauge-desc">{s.desc}</div>
              </div>
            ))
          ) : (
            ['Soil Health Score', 'Climate Suitability', 'Input Efficiency', 'NPK Balance'].map((label, i) => (
              <div className="gauge-card" key={i}>
                <div className="gauge-card-title">{Object.values(SCORE_ICONS)[i]} {label}</div>
                <GaugeChart score={0} color={Object.values(SCORE_COLORS)[i]} size={120} />
                <div className="gauge-rating" style={{ color: '#8a9388' }}>—</div>
                <div className="gauge-desc">Run prediction to see score</div>
              </div>
            ))
          )}
        </div>

        {/* ── RECOMMENDATIONS ── */}
        <div className="recs-card fade-in">
          <div className="section-title">💡 AI Insights & Recommendations</div>
          <div className="recs-grid">
            {result?.recommendations?.map((rec, i) => (
              <div className="rec-item" key={i}>
                <div className={`rec-icon ${rec.type}`}>{REC_ICONS[rec.type]}</div>
                <div>
                  <div className={`rec-title ${rec.type}`}>{rec.title}</div>
                  <div className="rec-desc">{rec.desc}</div>
                </div>
              </div>
            )) || (
              <div className="empty-state" style={{ gridColumn: '1 / -1' }}>
                <div className="empty-state-icon">💡</div>
                <div className="empty-state-text">Predictions and recommendations will appear automatically</div>
              </div>
            )}
          </div>
          <img src={farmerImg} alt="Farmer illustration" className="recs-farmer" />
        </div>
      </div>
    </div>
  )
}

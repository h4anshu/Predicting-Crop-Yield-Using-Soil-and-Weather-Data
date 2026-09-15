import { useState, useEffect } from 'react'
import './index.css'
import Sidebar from './components/Sidebar'
import Dashboard from './components/Dashboard'
import Prediction from './pages/Prediction'
import HistoricalTrends from './pages/HistoricalTrends'
import CropInsights from './pages/CropInsights'
import SoilClimate from './pages/SoilClimate'
import ModelPerformance from './pages/ModelPerformance'
import { API_BASE, DEFAULT_OPTIONS, DEFAULT_STATS } from './constants'

function App() {
  const [activePage, setActivePage] = useState('dashboard')
  const [options, setOptions] = useState(DEFAULT_OPTIONS)
  const [stats, setStats] = useState(DEFAULT_STATS)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  useEffect(() => {
    fetch(`${API_BASE}/api/options`)
      .then(r => r.json())
      .then(d => { if (d?.states?.length) setOptions(d) })
      .catch(e => console.error('Failed to load options:', e))

    fetch(`${API_BASE}/api/stats`)
      .then(r => r.json())
      .then(d => { if (d?.total_records) setStats(d) })
      .catch(e => console.error('Failed to load stats:', e))
  }, [])

  function handlePageChange(page) {
    setActivePage(page)
    setSidebarOpen(false)
  }

  return (
    <div className="app-layout">
      {/* Mobile overlay */}
      <div
        className={`sidebar-overlay ${sidebarOpen ? 'visible' : ''}`}
        onClick={() => setSidebarOpen(false)}
      />

      {/* Sidebar */}
      <div className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <Sidebar
          activePage={activePage}
          onPageChange={handlePageChange}
          stats={stats}
        />
      </div>

      {/* Main Area */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Mobile Header */}
        <div className="mobile-header">
          <button className="hamburger-btn" onClick={() => setSidebarOpen(!sidebarOpen)}>
            {sidebarOpen ? '✕' : '☰'}
          </button>
          <div className="mobile-brand">
            Agri<span>Predict</span> AI
          </div>
        </div>

        {/* Pages */}
        {activePage === 'dashboard' && (
          <Dashboard options={options} stats={stats} />
        )}
        {activePage === 'prediction' && <Prediction options={options} />}
        {activePage === 'trends' && <HistoricalTrends options={options} />}
        {activePage === 'insights' && <CropInsights options={options} />}
        {activePage === 'soil' && <SoilClimate options={options} />}
        {activePage === 'model' && <ModelPerformance />}
        {activePage === 'about' && (
          <div className="main-content">
            <div className="main-content-inner">
              <div className="page-header fade-in">
                <div className="page-header-left">
                  <span className="page-header-icon">ℹ️</span>
                  <div>
                    <h1 className="page-header-title">About AgriPredict AI</h1>
                    <div className="page-header-subtitle">
                      Machine learning powered crop yield forecasting
                    </div>
                  </div>
                </div>
              </div>
              <div className="section-card fade-in" style={{ maxWidth: 800 }}>
                <div className="section-title">🌾 About the Project</div>
                <div style={{ color: '#4a5d4e', lineHeight: 1.8, fontSize: '0.92rem' }}>
                  <p>
                    AgriPredict AI is a machine-learning powered crop yield forecasting system trained on
                    24 years (1997–2020) of Indian agricultural data. It combines soil chemistry, weather
                    patterns, and farming inputs to estimate expected harvests.
                  </p>
                  <h3 style={{ margin: '1.2rem 0 0.5rem', color: '#1a2e1e' }}>Model Details</h3>
                  <ul style={{ paddingLeft: '1.2rem' }}>
                    <li><strong>Algorithm:</strong> Extra Trees Regressor (200 estimators, max depth 20)</li>
                    <li><strong>Test R²:</strong> {stats?.model_accuracy || '—'} across all crops,{' '}
                      {stats?.model_accuracy_core || '—'} on core staples</li>
                    <li><strong>Mean Absolute Error:</strong> {stats?.model_mae ?? '—'} t/ha</li>
                    <li><strong>Training records:</strong> {stats?.total_records?.toLocaleString('en-IN') || '—'}</li>
                    <li><strong>Coverage:</strong> {stats?.crops_covered || '—'} crops · {stats?.states_covered || '—'} states</li>
                    <li><strong>Validation:</strong> temporal holdout — trained on 1997–2017, tested on 2018–2020</li>
                  </ul>
                  <p style={{ marginTop: '0.8rem' }}>
                    Two accuracy figures are quoted because crop yields in this dataset differ by
                    more than an order of magnitude. A model that merely separates high-magnitude
                    crops from low-magnitude ones scores well without doing much agronomy, so the
                    lower core-staples figure is the honest description of everyday performance.
                    The <strong>Model Performance</strong> page sets out the full breakdown.
                  </p>
                  <h3 style={{ margin: '1.2rem 0 0.5rem', color: '#1a2e1e' }}>Units and exclusions</h3>
                  <p>
                    Yields are reported in tonnes per hectare. Coconut is excluded from the model:
                    Indian government records count individual nuts rather than weight, so its
                    figures are not comparable with every other crop in the same column.
                  </p>
                  <h3 style={{ margin: '1.2rem 0 0.5rem', color: '#1a2e1e' }}>Scope of a forecast</h3>
                  <p>
                    Soil is recorded once per state and weather once per state-year, so a forecast
                    describes conditions typical of a region rather than one specific field. Use it
                    to compare options — crops, seasons, input levels — rather than as a substitute
                    for a soil test. Predictions are statistical estimates and should be one input
                    among several in farm planning.
                  </p>
                  <h3 style={{ margin: '1.2rem 0 0.5rem', color: '#1a2e1e' }}>How to Use</h3>
                  <ol style={{ paddingLeft: '1.2rem' }}>
                    <li>Enter your field's location, soil, climate, and farm inputs on the <strong>Dashboard</strong></li>
                    <li>Click <strong>Predict Yield</strong> to get the forecast</li>
                    <li>Review the four score gauges and AI recommendations</li>
                    <li>Use <strong>Prediction</strong> to compare several input scenarios side by side</li>
                    <li>Check <strong>Historical Trends</strong> to see how yields have evolved</li>
                    <li>Read <strong>Model Performance</strong> for accuracy, limits and validation</li>
                  </ol>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default App

import { useState, useEffect } from 'react'
import './index.css'
import Sidebar from './components/Sidebar'
import Dashboard from './components/Dashboard'
import DistrictForecast from './pages/DistrictForecast'
import DistrictMap from './pages/DistrictMap'
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
  const [districtPick, setDistrictPick] = useState(null)   // set by the map, read by the District Forecast page

  useEffect(() => {
    fetch(`${API_BASE}/api/options`)
      .then(r => r.json())
      .then(d => { if (d?.states?.length) setOptions(d) })
      .catch(e => console.error('Failed to load options:', e))

    fetch(`${API_BASE}/api/stats`)
      .then(r => r.json())
      .then(d => { if (d?.dataset) setStats(d) })
      .catch(e => console.error('Failed to load stats:', e))
  }, [])

  function handlePageChange(page) {
    setActivePage(page)
    setSidebarOpen(false)
  }

  const d = stats?.dataset
  const o = stats?.outlook

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
        {activePage === 'dashboard' && <Dashboard stats={stats} onNavigate={handlePageChange} onOpen={pick => { setDistrictPick(pick); setActivePage('district') }} />}
        {activePage === 'district' && <DistrictForecast key={districtPick ? JSON.stringify(districtPick) : 'free'} initial={districtPick} />}
        {activePage === 'map' && (
          <DistrictMap onOpen={pick => { setDistrictPick(pick); setActivePage('district') }} />
        )}
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
                      Crop yield forecasting from official records
                    </div>
                  </div>
                </div>
              </div>
              <div className="section-card fade-in" style={{ maxWidth: 800 }}>
                <div className="section-title">🌾 About the Project</div>
                <div style={{ color: '#4a5d4e', lineHeight: 1.8, fontSize: '0.92rem' }}>
                  <p>
                    AgriPredict AI tells you what to expect from a crop in an Indian district next season, from that district's
                    own published history, and how far to trust it. It is built on one dataset: {d ? `${d.rows.toLocaleString('en-IN')} records for ${d.districts} districts in ${d.states_uts} states and UTs, ${d.year_min}–${d.year_max}` : 'official district records'},
                    with the state-level figures, weather, satellite vegetation, soil and irrigation data joined onto the same rows.
                  </p>
                  <h3 style={{ margin: '1.2rem 0 0.5rem', color: '#1a2e1e' }}>What is forecast, and how</h3>
                  <ul style={{ paddingLeft: '1.2rem' }}>
                    <li><strong>Expected yield:</strong> the mean of the last three published seasons of the series. It has been a better guide than repeating
                      the last published season for {o ? `${o.mean_beats_last_published_crops} of ${o.crops_offered}` : 'most'} crops.</li>
                    <li><strong>Range:</strong> 80%, calibrated per crop on how far that mean was from the recorded yield in past seasons, wider for volatile
                      series. It held {o ? `${Math.round(100 * o.range_coverage.dev_2018_2023)}% of the time on 2018–23 and ${Math.round(100 * o.range_coverage.confirm_2024)}% in 2024` : '—'}.</li>
                    <li><strong>A model was tested and is not used:</strong> a machine-learning model trained on the whole dataset was tested the way a
                      forecaster would meet the data, knowing only what had been published by then. {o ? `It beat the mean by the bar set in advance for ${o.model_crops_beating_mean} of the ${o.model_crops_tested} crops` : 'It did not clear the bar'}.
                      Weather, satellite and soil data did not clear their bars either.</li>
                    <li><strong>Validation:</strong> every pass/fail bar was written before the results were seen; the <strong>Model &amp; Evidence</strong> page
                      lists them with the outcome, including the ones that failed and one test that was corrected because it was too generous.</li>
                  </ul>
                  <h3 style={{ margin: '1.2rem 0 0.5rem', color: '#1a2e1e' }}>Publication lag</h3>
                  <p>
                    District yields are published more than a year late, so a forecast for 2025 uses seasons up to 2023 and never assumes it knows
                    last season's result. Each forecast is shown with an 80% range, the last published value, the 3-season mean and a reliability flag.
                  </p>
                  <h3 style={{ margin: '1.2rem 0 0.5rem', color: '#1a2e1e' }}>Units and exclusions</h3>
                  <p>
                    Yields are in tonnes per hectare. Coconut is recorded in nuts, so it is never averaged with the others. Madhya Pradesh district
                    figures in the source are about twice the Centre's official state total for wheat; treat their level with caution.
                  </p>
                  <h3 style={{ margin: '1.2rem 0 0.5rem', color: '#1a2e1e' }}>Scope of a forecast</h3>
                  <p>
                    An outlook describes a district, not a field, and is a statistical estimate. Use it to compare districts, crops and seasons, as one
                    input among several in planning.
                  </p>
                  <h3 style={{ margin: '1.2rem 0 0.5rem', color: '#1a2e1e' }}>How to use</h3>
                  <ol style={{ paddingLeft: '1.2rem' }}>
                    <li>Start on the <strong>Dashboard</strong> for what the data holds and what it supports forecasting</li>
                    <li>Open <strong>District Outlook</strong> or the <strong>District Map</strong> for the expected yield, with its range, baselines and track record</li>
                    <li>Use <strong>Historical Trends</strong>, <strong>Crop Insights</strong> and <strong>Soil &amp; Climate</strong> to see the records behind it</li>
                    <li>Read <strong>Model &amp; Evidence</strong> for accuracy by crop, limits and validation</li>
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

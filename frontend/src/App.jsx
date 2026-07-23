import { useState, useEffect } from 'react'
import './index.css'
import Sidebar from './components/Sidebar'
import Dashboard from './components/Dashboard'

const API_BASE = 'https://agripredict-api-531174775648.europe-west1.run.app'

function App() {
  const [activePage, setActivePage] = useState('dashboard')
  const [options, setOptions] = useState(null)
  const [stats, setStats] = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  useEffect(() => {
    fetch(`${API_BASE}/api/options`)
      .then(r => r.json())
      .then(d => setOptions(d))
      .catch(e => console.error('Failed to load options:', e))

    fetch(`${API_BASE}/api/stats`)
      .then(r => r.json())
      .then(d => setStats(d))
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
                    <li><strong>Algorithm:</strong> Extra Trees Regressor (200 estimators)</li>
                    <li><strong>Test R²:</strong> 0.9506</li>
                    <li><strong>Mean Absolute Error:</strong> 1.00</li>
                    <li><strong>Training records:</strong> 19,689</li>
                    <li><strong>Coverage:</strong> 55 crops · 30 states</li>
                  </ul>
                  <h3 style={{ margin: '1.2rem 0 0.5rem', color: '#1a2e1e' }}>How to Use</h3>
                  <ol style={{ paddingLeft: '1.2rem' }}>
                    <li>Enter your field's location, soil, climate, and farm inputs on the <strong>Dashboard</strong></li>
                    <li>Click <strong>Predict Yield</strong> to get the forecast</li>
                    <li>Review the four score gauges and AI recommendations</li>
                    <li>Check <strong>Historical Trends</strong> to see how yields have evolved</li>
                  </ol>
                </div>
              </div>
            </div>
          </div>
        )}
        {activePage !== 'dashboard' && activePage !== 'about' && (
          <div className="main-content">
            <div className="main-content-inner">
              <div className="page-header fade-in">
                <div className="page-header-left">
                  <span className="page-header-icon">🚧</span>
                  <div>
                    <h1 className="page-header-title">Coming Soon</h1>
                    <div className="page-header-subtitle">
                      This section is under development.
                    </div>
                  </div>
                </div>
              </div>
              <div className="section-card fade-in" style={{ maxWidth: 600, textAlign: 'center', padding: '3rem' }}>
                <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>🔨</div>
                <div style={{ color: '#4a5d4e', fontSize: '1rem' }}>
                  Navigate to <strong>Dashboard</strong> to use the crop yield prediction tool.
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

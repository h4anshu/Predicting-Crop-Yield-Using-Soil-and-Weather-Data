const NAV_ITEMS = [
  { id: 'dashboard', icon: '🏠', label: 'Dashboard' },
  { id: 'prediction', icon: '🔮', label: 'Prediction' },
  { id: 'trends', icon: '📊', label: 'Historical Trends' },
  { id: 'insights', icon: '🌾', label: 'Crop Insights' },
  { id: 'soil', icon: '🧪', label: 'Soil & Climate' },
  { id: 'model', icon: '📈', label: 'Model Performance' },
  { id: 'about', icon: 'ℹ️', label: 'About Project' },
]

export default function Sidebar({ activePage, onPageChange, stats }) {
  return (
    <>
      {/* Brand */}
      <div className="sidebar-brand">
        <div className="sidebar-brand-icon">🌱</div>
        <div className="sidebar-brand-name">
          Agri<span>Predict</span> AI
        </div>
        <div className="sidebar-brand-sub">Crop Yield Intelligence</div>
      </div>

      <hr className="sidebar-divider" />

      {/* Nav */}
      <nav className="sidebar-nav">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            className={`sidebar-nav-item ${activePage === item.id ? 'active' : ''}`}
            onClick={() => onPageChange(item.id)}
          >
            <span className="nav-icon">{item.icon}</span>
            {item.label}
          </button>
        ))}
      </nav>

      <hr className="sidebar-divider" />

      {/* Model info */}
      <div className="sidebar-info">
        <div className="sidebar-info-title">Model Information</div>

        <div className="sidebar-info-item">
          <div className="sidebar-info-label">Model</div>
          <div className="sidebar-info-value">Extra Trees Regressor</div>
        </div>
        <div className="sidebar-info-item">
          <div className="sidebar-info-label">Accuracy (R²)</div>
          <div className="sidebar-info-value accent">95%</div>
        </div>
        <div className="sidebar-info-item">
          <div className="sidebar-info-label">Data Records</div>
          <div className="sidebar-info-value">{stats?.total_records?.toLocaleString() || '19,689'}</div>
        </div>
        <div className="sidebar-info-item">
          <div className="sidebar-info-label">Years Covered</div>
          <div className="sidebar-info-value">{stats?.years_covered || '1997 - 2020'}</div>
        </div>
        <div className="sidebar-info-item">
          <div className="sidebar-info-label">Crops</div>
          <div className="sidebar-info-value">{stats?.crops_covered || 55}</div>
        </div>
        <div className="sidebar-info-item">
          <div className="sidebar-info-label">States</div>
          <div className="sidebar-info-value">{stats?.states_covered || 30}</div>
        </div>
      </div>

      {/* Footer */}
      <div className="sidebar-footer">
        <div className="sidebar-footer-label">🌾 Empowering</div>
        <div className="sidebar-footer-text">Farmers with Data & AI 🚀</div>
      </div>
    </>
  )
}

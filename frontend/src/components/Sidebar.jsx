const NAV_ITEMS = [
  { id: 'dashboard', icon: '🏠', label: 'Dashboard' },
  { id: 'district', icon: '🗺️', label: 'District Outlook' },
  { id: 'map', icon: '🧭', label: 'District Map' },
  { id: 'trends', icon: '📊', label: 'Historical Trends' },
  { id: 'insights', icon: '🌾', label: 'Crop Insights' },
  { id: 'soil', icon: '🧪', label: 'Soil & Climate' },
  { id: 'model', icon: '📈', label: 'Model & Evidence' },
  { id: 'about', icon: 'ℹ️', label: 'About Project' },
]

const n = v => (v == null ? '—' : Number(v).toLocaleString('en-IN'))

export default function Sidebar({ activePage, onPageChange, stats }) {
  const d = stats?.dataset
  const o = stats?.outlook
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

      {/* Dataset and model info */}
      <div className="sidebar-info">
        <div className="sidebar-info-title">Data &amp; Model</div>

        <div className="sidebar-info-item">
          <div className="sidebar-info-label">Records</div>
          <div className="sidebar-info-value">{n(d?.rows)}</div>
        </div>
        <div className="sidebar-info-item">
          <div className="sidebar-info-label">Years covered</div>
          <div className="sidebar-info-value">{d ? `${d.year_min} – ${d.year_max}` : '—'}</div>
        </div>
        <div className="sidebar-info-item">
          <div className="sidebar-info-label">Districts · states</div>
          <div className="sidebar-info-value">{d ? `${n(d.districts)} · ${d.states_uts}` : '—'}</div>
        </div>
        <div className="sidebar-info-item">
          <div className="sidebar-info-label">Crops with an outlook</div>
          <div className="sidebar-info-value">{o ? `${o.crops_offered} of ${d?.crops ?? o.crops_offered}` : '—'}</div>
        </div>
        <div className="sidebar-info-item">
          <div className="sidebar-info-label">80% range held</div>
          <div className="sidebar-info-value accent">{o ? `${Math.round(100 * o.range_coverage.dev_2018_2023)}%` : '—'}</div>
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

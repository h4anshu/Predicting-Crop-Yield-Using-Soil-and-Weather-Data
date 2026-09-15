/**
 * Presentational pieces shared by the five pages.
 * Non-component exports (useApi, chart styling, fmt) live in ./api.js so that this
 * module exports components only and Fast Refresh keeps working.
 */

export function PageHeader({ icon, title, subtitle, right }) {
  return (
    <div className="page-header fade-in">
      <div className="page-header-left">
        <span className="page-header-icon">{icon}</span>
        <div>
          <h1 className="page-header-title">{title}</h1>
          <div className="page-header-subtitle">{subtitle}</div>
        </div>
      </div>
      {right && <div className="page-header-right">{right}</div>}
    </div>
  )
}

export function KpiCard({ icon, iconBg, label, value, sub, title }) {
  return (
    <div className="kpi-card" title={title}>
      <div className="kpi-icon" style={{ background: iconBg || 'var(--green-100)' }}>{icon}</div>
      <div className="kpi-content">
        <div className="kpi-label">{label}</div>
        <div className="kpi-value">{value}</div>
        {sub && <div className="kpi-sub">{sub}</div>}
      </div>
    </div>
  )
}

export function Loading({ label = 'Loading…' }) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">⏳</div>
      <div className="empty-state-text">
        {label}
        <div style={{ fontSize: '0.82rem', marginTop: '0.5rem', color: 'var(--text-light)' }}>
          The first request after an idle period wakes the server and can take a few seconds.
        </div>
      </div>
    </div>
  )
}

export function ErrorState({ error }) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon">⚠️</div>
      <div className="empty-state-text">
        Could not reach the prediction service.
        <div style={{ fontSize: '0.82rem', marginTop: '0.5rem', color: 'var(--text-light)' }}>{error}</div>
      </div>
    </div>
  )
}

/**
 * A short explanatory note. Used throughout to state a limitation next to the number
 * it applies to, rather than burying every caveat on the About page.
 */
export function Note({ tone = 'info', title, children }) {
  return (
    <div className={`note note-${tone}`}>
      {title && <div className="note-title">{title}</div>}
      <div className="note-body">{children}</div>
    </div>
  )
}

export function Bar({ value, max, color = 'var(--green-600)', height = 8 }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  return (
    <div className="mini-bar" style={{ height }}>
      <div className="mini-bar-fill" style={{ width: `${pct}%`, background: color }} />
    </div>
  )
}

export function Spec({ label, value, wide }) {
  return (
    <div className={`spec-item${wide ? ' spec-wide' : ''}`}>
      <div className="spec-label">{label}</div>
      <div className="spec-value">{value}</div>
    </div>
  )
}

/** Every page renders inside the same scroll container. */
export function Page({ children }) {
  return (
    <div className="main-content">
      <div className="main-content-inner">{children}</div>
    </div>
  )
}

/**
 * Presentational pieces shared by the five pages.
 * Non-component exports (useApi, chart styling, fmt) live in ./api.js so that this
 * module exports components only and Fast Refresh keeps working.
 */

import { fmt } from './api'

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

/** The four selectors of `useSeriesPicker`: state, district, crop and season, year. */
export function SeriesPicker({ p }) {
  const { sel, setSel, states, state, districts, district, seriesList, series, seriesKey, year } = p
  return (
    <>
      <div className="input-row cols-3">
        <div className="form-field">
          <label>State</label>
          <select value={state} onChange={e => setSel({ state: e.target.value })}>
            {states.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div className="form-field">
          <label>District</label>
          <select value={district} onChange={e => setSel({ ...sel, state, district: e.target.value, series: undefined })}>
            {districts.map(([c, d]) => <option key={c} value={c}>{d.name}</option>)}
          </select>
        </div>
        <div className="form-field">
          <label>Crop · season</label>
          <select value={series ? seriesKey(series) : ''} onChange={e => setSel({ ...sel, state, district, series: e.target.value })}>
            {seriesList.map(s => <option key={seriesKey(s)} value={seriesKey(s)}>{s.crop} · {s.season}</option>)}
          </select>
        </div>
      </div>
      <div className="input-row cols-3" style={{ marginTop: '0.6rem' }}>
        <div className="form-field">
          <label>Agricultural year starting</label>
          <select value={year} onChange={e => setSel({ ...sel, state, district, series: series && seriesKey(series), year: Number(e.target.value) })}>
            <option value={2025}>2025 (first unpublished season)</option>
            <option value={2026}>2026 (two seasons past the data)</option>
          </select>
        </div>
      </div>
    </>
  )
}

/** Expected yield with its range, the last published season, the range width and the reliability flag. */
export function OutlookKpis({ f }) {
  return (
    <div className="kpi-row fade-in">
      <KpiCard icon="🎯" iconBg="var(--green-100)" label={`EXPECTED YIELD ${f.forecast_year}`} value={fmt(f.forecast)}
               sub={`${f.unit} · 80% range ${fmt(f.interval.low)}–${fmt(f.interval.high)}`}
               title="The mean of the last three published seasons. The range comes from how far that mean has been from the recorded yield in past seasons, separately for volatile and stable series." />
      <KpiCard icon="📅" iconBg="var(--blue-bg)" label={`LAST PUBLISHED (${f.baselines.last_published.year})`}
               value={fmt(f.baselines.last_published.value)}
               sub={`expected is ${f.forecast >= f.baselines.last_published.value ? '+' : ''}${fmt(100 * (f.forecast / f.baselines.last_published.value - 1), 0)}% against it`} />
      <KpiCard icon="↔️" iconBg="var(--amber-bg)" label="RANGE WIDTH" value={`±${fmt(100 * f.interval.relative_half_width, 0)}%`}
               sub="of the expected yield, 80% of the time" />
      <KpiCard icon={f.trust.low_trust ? '⚠️' : '✅'} iconBg={f.trust.low_trust ? 'var(--amber-bg)' : 'var(--green-100)'}
               label="RELIABILITY" value={f.trust.low_trust ? 'Volatile' : 'Stable'}
               sub={`${f.trust.seasons_of_history_used} of 3 recent seasons on record`} />
    </div>
  )
}

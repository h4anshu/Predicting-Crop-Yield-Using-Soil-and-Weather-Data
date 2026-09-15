import { useState } from 'react'
import {
  AreaChart, Area, BarChart, Bar as RBar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell, LineChart, Line,
} from 'recharts'
import { ErrorState, KpiCard, Loading, Note, PageHeader, Page } from './shared'
import { useApi, CHART_COLORS, axisProps, gridProps, tooltipStyle, fmt } from './api'

/**
 * Yield patterns across years, seasons and states.
 *
 * Every figure here excludes the special-unit crops, because averaging nuts/ha with
 * tonnes/ha produces a number that means nothing. That filter happens server-side in
 * /api/trends; it is surfaced in the UI so the reader knows what they are looking at.
 */
export default function HistoricalTrends({ options }) {
  const { data: trends, error, loading } = useApi('/api/trends')
  const [crop, setCrop] = useState('Rice')
  const [state, setState] = useState('')
  const q = `/api/historical?crop=${encodeURIComponent(crop)}${state ? `&state=${encodeURIComponent(state)}` : ''}`
  const { data: series } = useApi(q)

  if (loading) return <Page><Loading label="Loading historical trends…" /></Page>
  if (error) return <Page><ErrorState error={error} /></Page>
  if (!trends) return null

  const yearly = trends.yearly.years.map((y, i) => ({ year: y, yield: trends.yearly.values[i] }))
  const seasons = trends.by_season.seasons.map((s, i) => ({ season: s.trim(), yield: trends.by_season.values[i] }))
  const states = trends.by_state.states.map((s, i) => ({ state: s, yield: trends.by_state.values[i] }))

  const first = yearly[0], last = yearly[yearly.length - 1]
  const growth = first && last ? ((last.yield - first.yield) / first.yield) * 100 : 0
  const best = states[0], worst = states[states.length - 1]

  const seriesData = series?.years?.map((y, i) => ({ year: y, yield: series.values[i] })) || []

  return (
    <Page>
      <PageHeader
        icon="📊"
        title="Historical Trends"
        subtitle="Yield patterns across 24 years, six seasons and 30 states"
      />

      <div className="kpi-row fade-in">
        <KpiCard icon="📈" iconBg="var(--green-100)" label="24-YEAR CHANGE"
          value={`${growth >= 0 ? '+' : ''}${fmt(growth, 1)}%`}
          sub={`${fmt(first?.yield)} → ${fmt(last?.yield)} t/ha`} />
        <KpiCard icon="🏆" iconBg="var(--amber-bg)" label="HIGHEST YIELDING STATE"
          value={best?.state || '—'} sub={`${fmt(best?.yield)} t/ha average`} />
        <KpiCard icon="🌱" iconBg="var(--blue-bg)" label="BEST SEASON"
          value={seasons[0]?.season || '—'} sub={`${fmt(seasons[0]?.yield)} t/ha average`} />
        <KpiCard icon="📉" iconBg="var(--red-bg)" label="LOWEST YIELDING STATE"
          value={worst?.state || '—'} sub={`${fmt(worst?.yield)} t/ha average`} />
      </div>

      <div className="section-card fade-in">
        <div className="section-title">📅 Average yield by year</div>
        <p className="section-lede">
          Mean yield across all comparable crops. Movement here reflects shifting crop mix and
          reporting coverage as much as agronomic productivity, so read it as a trend, not a
          productivity index.
        </p>
        <div style={{ width: '100%', height: 300 }}>
          <ResponsiveContainer>
            <AreaChart data={yearly} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
              <defs>
                <linearGradient id="yearGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={CHART_COLORS.green} stopOpacity={0.35} />
                  <stop offset="100%" stopColor={CHART_COLORS.green} stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="year" {...axisProps} />
              <YAxis {...axisProps} />
              <Tooltip {...tooltipStyle} formatter={v => [`${fmt(v)} t/ha`, 'Avg yield']} />
              <Area type="monotone" dataKey="yield" stroke={CHART_COLORS.green} strokeWidth={2.5}
                    fill="url(#yearGrad)" dot={{ r: 2.5, fill: CHART_COLORS.green }} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="split-grid">
        <div className="section-card fade-in">
          <div className="section-title">🌤️ By season</div>
          <div style={{ width: '100%', height: 280 }}>
            <ResponsiveContainer>
              <BarChart data={seasons} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="season" {...axisProps} interval={0} angle={-15} textAnchor="end" height={56} />
                <YAxis {...axisProps} />
                <Tooltip {...tooltipStyle} formatter={v => [`${fmt(v)} t/ha`, 'Avg yield']} />
                <RBar dataKey="yield" radius={[6, 6, 0, 0]}>
                  {seasons.map((_, i) => (
                    <Cell key={i} fill={i === 0 ? CHART_COLORS.green : '#a8c9b4'} />
                  ))}
                </RBar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="section-card fade-in">
          <div className="section-title">🔬 Track one crop</div>
          <div className="input-row" style={{ marginBottom: '1rem' }}>
            <div className="form-field">
              <label>Crop</label>
              <select value={crop} onChange={e => setCrop(e.target.value)}>
                {options?.crops?.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="form-field">
              <label>State (optional)</label>
              <select value={state} onChange={e => setState(e.target.value)}>
                <option value="">All India</option>
                {options?.states?.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
          </div>
          {seriesData.length > 0 ? (
            <>
              <div style={{ width: '100%', height: 210 }}>
                <ResponsiveContainer>
                  <LineChart data={seriesData} margin={{ top: 8, right: 12, left: 0, bottom: 4 }}>
                    <CartesianGrid {...gridProps} />
                    <XAxis dataKey="year" {...axisProps} />
                    <YAxis {...axisProps} />
                    <Tooltip {...tooltipStyle} formatter={v => [`${fmt(v)} ${series.unit}`, 'Yield']} />
                    <Line type="monotone" dataKey="yield" stroke={CHART_COLORS.blue}
                          strokeWidth={2.5} dot={{ r: 2.5 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div className="chart-summary" style={{ marginTop: '0.6rem' }}>
                <strong>{series.label}</strong> — avg {fmt(series.avg)}, range {fmt(series.min)}–{fmt(series.max)} {series.unit}
              </div>
            </>
          ) : <Loading label="Loading series…" />}
        </div>
      </div>

      <div className="section-card fade-in">
        <div className="section-title">🗺️ Average yield by state</div>
        <div style={{ width: '100%', height: Math.max(340, states.length * 20) }}>
          <ResponsiveContainer>
            <BarChart data={states} layout="vertical" margin={{ top: 4, right: 30, left: 8, bottom: 4 }}>
              <CartesianGrid {...gridProps} horizontal={false} />
              <XAxis type="number" {...axisProps} />
              <YAxis type="category" dataKey="state" width={135} {...axisProps} interval={0} />
              <Tooltip {...tooltipStyle} formatter={v => [`${fmt(v)} t/ha`, 'Avg yield']} />
              <RBar dataKey="yield" radius={[0, 5, 5, 0]}>
                {states.map((s, i) => (
                  <Cell key={i} fill={`rgba(31,122,61,${0.35 + 0.65 * (s.yield / (states[0]?.yield || 1))})`} />
                ))}
              </RBar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <Note tone="info" title="What is excluded, and why">
          Coconut is reported in nuts per hectare rather than tonnes, so it is left out of every
          average on this page — mixing the two units would produce a figure with no meaning.
          State averages also reflect which crops each state reports, not land quality alone: a
          state growing more high-yield crops ranks higher without being more productive per crop.
        </Note>
      </div>
    </Page>
  )
}


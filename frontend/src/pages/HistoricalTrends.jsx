import { useState } from 'react'
import {
  AreaChart, Area, BarChart, Bar as RBar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell, LineChart, Line, ReferenceLine,
} from 'recharts'
import { ErrorState, KpiCard, Loading, Note, PageHeader, Page } from './shared'
import { useApi, CHART_COLORS, axisProps, gridProps, tooltipStyle, fmt } from './api'

/**
 * Yield patterns across years, seasons and states.
 *
 * Every figure here excludes the special-unit crops, because averaging nuts/ha with
 * tonnes/ha produces a number that means nothing. That filter happens server-side in
 * /api/trends; it is surfaced in the UI so the reader knows what they are looking at.
 * The by-year line is an index (each series against its own average), so the mix of crops
 * reported in a year cannot move it.
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
  const states = trends.by_state.states.map((s, i) => ({ state: s, yield: trends.by_state.values[i], records: trends.by_state.records[i] }))

  const avg = rows => rows.reduce((a, r) => a + r.yield, 0) / (rows.length || 1)
  const first = avg(yearly.slice(0, 3)), last = avg(yearly.slice(-3))
  const growth = first ? ((last - first) / first) * 100 : 0
  const best = states[0], worst = states[states.length - 1]

  const seriesData = series?.years?.map((y, i) => ({ year: y, yield: series.values[i] })) || []

  return (
    <Page>
      <PageHeader
        icon="📊"
        title="Historical Trends"
        subtitle={`Yield patterns across ${yearly.length} years and ${states.length} states and UTs`}
      />

      <div className="kpi-row fade-in">
        <KpiCard icon="📈" iconBg="var(--green-100)" label={`CHANGE, ${yearly[0]?.year}–${yearly[2]?.year} TO ${yearly[yearly.length - 3]?.year}–${yearly[yearly.length - 1]?.year}`}
          value={`${growth >= 0 ? '+' : ''}${fmt(growth, 1)}%`}
          sub={`yield index ${fmt(first, 1)} → ${fmt(last, 1)}`} />
        <KpiCard icon="🏆" iconBg="var(--amber-bg)" label="HIGHEST VS NATIONAL"
          value={best?.state || '—'} sub={`${fmt(best?.yield, 0)} (100 = national, crop for crop)`} />
        <KpiCard icon="📉" iconBg="var(--red-bg)" label="LOWEST VS NATIONAL"
          value={worst?.state || '—'} sub={`${fmt(worst?.yield, 0)} (100 = national, crop for crop)`} />
      </div>

      <div className="section-card fade-in">
        <div className="section-title">📅 Yield index by year</div>
        <p className="section-lede">
          Each state, crop and season is measured against its own average (100), then averaged, so a
          change in which crops a year reports cannot move the line. Some years report fewer series
          (2020 is thin, 2024 is partly published), which adds noise but not a trend.
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
              <YAxis {...axisProps} domain={['dataMin - 5', 'dataMax + 5']} tickFormatter={v => Math.round(v)} />
              <Tooltip {...tooltipStyle} formatter={v => [fmt(v, 1), 'Yield index']} />
              <Area type="monotone" dataKey="yield" stroke={CHART_COLORS.green} strokeWidth={2.5}
                    fill="url(#yearGrad)" dot={{ r: 2.5, fill: CHART_COLORS.green }} />
            </AreaChart>
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

      <div className="section-card fade-in">
        <div className="section-title">🗺️ Yield by state, against the national figure</div>
        <p className="section-lede">
          Each state's yield divided by the national yield of the same crop, season and year (100 = national), averaged over the series the
          state reports. Comparing crop for crop keeps a state that grows sugarcane or banana from ranking first for its crop mix.
        </p>
        <div style={{ width: '100%', height: Math.max(340, states.length * 20) }}>
          <ResponsiveContainer>
            <BarChart data={states} layout="vertical" margin={{ top: 4, right: 30, left: 8, bottom: 4 }}>
              <CartesianGrid {...gridProps} horizontal={false} />
              <XAxis type="number" {...axisProps} />
              <YAxis type="category" dataKey="state" width={135} {...axisProps} interval={0} />
              <Tooltip {...tooltipStyle} formatter={(v, _n, p) => [`${fmt(v, 0)} (${p.payload.records} records)`, 'vs national']} />
              <ReferenceLine x={100} stroke={CHART_COLORS.amber} strokeDasharray="5 4" />
              <RBar dataKey="yield" radius={[0, 5, 5, 0]}>
                {states.map((s, i) => (
                  <Cell key={i} fill={`rgba(31,122,61,${0.35 + 0.65 * Math.min(1, s.yield / (states[0]?.yield || 1))})`} />
                ))}
              </RBar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <Note tone="info" title="What is excluded, and why">
          Coconut is reported in nuts per hectare rather than tonnes, so it is left out of the index and the state comparison.
          A state's figure averages only the crops it reports, so a state with a few series (Delhi, Goa) is noisier than one with many;
          the record count is in the tooltip.
        </Note>
      </div>
    </Page>
  )
}


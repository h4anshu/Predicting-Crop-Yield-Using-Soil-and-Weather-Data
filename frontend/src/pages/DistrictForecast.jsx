import { useState } from 'react'
import { ComposedChart, Line, ErrorBar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { ErrorState, KpiCard, Loading, Note, Page, PageHeader } from './shared'
import { CHART_COLORS, axisProps, gridProps, tooltipStyle, fmt, useGet, skillVerdict } from './api'

/**
 * District forecast: next-season yield for one district, crop and season.
 *
 * Built to be read critically. Every forecast comes with what repeating history would have said, the range the
 * model's own past errors imply, a reliability flag, and how the model did on seasons it had not seen. The
 * skill sentence is generated from the numbers, so a model that is no better than a 3-season average says so.
 */
export default function DistrictForecast({ initial }) {
  const opts = useGet('/api/district/options')
  const [sel, setSel] = useState(initial || {})   // `initial` comes from a click on the District Map

  const options = opts.data
  const states = options ? Object.keys(options).sort() : []
  const state = states.includes(sel.state) ? sel.state : states[0]
  const districts = state ? Object.entries(options[state]).sort((a, b) => a[1].name.localeCompare(b[1].name)) : []
  const district = districts.find(([c]) => c === sel.district)?.[0] ?? districts[0]?.[0]
  const seriesList = district ? options[state][district].series : []
  const seriesKey = s => `${s.crop}|${s.season}`
  const series = seriesList.find(s => seriesKey(s) === sel.series) ?? seriesList[0]
  const year = sel.year ?? 2025

  const q = district && series
    ? `district_code=${district}&crop=${encodeURIComponent(series.crop)}&season=${encodeURIComponent(series.season)}` : null
  const fc = useGet(q ? `/api/district/forecast?${q}&year=${year}` : null)
  const tr = useGet(q ? `/api/district/track-record?${q}` : null)

  if (opts.loading) return <Page><Loading label="Loading districts…" /></Page>
  if (opts.error) return <Page><ErrorState error={opts.error} /></Page>

  const f = fc.data
  const skill = f?.model?.skill
  const dev = skill?.dev_2018_2023
  const c24 = skill?.confirm_2024

  return (
    <Page>
      <PageHeader
        icon="🗺️"
        title="District Forecast"
        subtitle="Next-season yield by district, shown against what repeating history would say"
      />

      <div className="section-card fade-in">
        <div className="section-title">🎛️ Choose a series</div>
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
            <label>Forecast year (agricultural year starting)</label>
            <select value={year} onChange={e => setSel({ ...sel, state, district, series: series && seriesKey(series), year: Number(e.target.value) })}>
              <option value={2025}>2025 (first unpublished season)</option>
              <option value={2026}>2026 (two seasons past the data)</option>
            </select>
          </div>
        </div>
      </div>

      {fc.loading && <Loading label="Forecasting…" />}
      {fc.error && (
        <div className="section-card fade-in">
          <Note tone="warn" title="No forecast for this selection">{fc.error}</Note>
        </div>
      )}

      {f && (
        <>
          <div className="kpi-row fade-in">
            <KpiCard icon="🔮" iconBg="var(--green-100)" label={`FORECAST ${f.forecast_year}`} value={fmt(f.forecast)}
                     sub={`${f.unit} · 80% range ${fmt(f.interval.low)}–${fmt(f.interval.high)}`}
                     title="The range is calibrated from this model's past errors, separately for volatile and stable series." />
            <KpiCard icon="📅" iconBg="var(--blue-bg)" label={`LAST PUBLISHED (${f.baselines.last_published.year})`}
                     value={fmt(f.baselines.last_published.value)}
                     sub={`forecast is ${f.forecast >= f.baselines.last_published.value ? '+' : ''}${fmt(100 * (f.forecast / f.baselines.last_published.value - 1), 0)}% against it`} />
            <KpiCard icon="📈" iconBg="var(--amber-bg)" label="MEAN OF LAST 3 PUBLISHED" value={fmt(f.baselines.mean_last_three_published)}
                     sub={f.unit} />
            <KpiCard icon={f.trust.low_trust ? '⚠️' : '✅'} iconBg={f.trust.low_trust ? 'var(--amber-bg)' : 'var(--green-100)'}
                     label="RELIABILITY" value={f.trust.low_trust ? 'Volatile' : 'Stable'}
                     sub={`${f.trust.seasons_of_history_used} of 3 recent seasons on record`} />
          </div>

          <div className="section-card fade-in">
            <div className="section-title">⚖️ How much to trust this</div>
            <Note tone={skillVerdict(f.model.group, dev.skill_vs_mean3_pct).tone}
                  title={skillVerdict(f.model.group, dev.skill_vs_mean3_pct).title}>
              On seasons it had not seen (2018–2023, {dev.n.toLocaleString('en-IN')} forecasts) its error was{' '}
              <strong>{fmt(dev.skill_vs_last_published_pct, 1)}% lower</strong> than repeating the last published season and{' '}
              <strong>{fmt(dev.skill_vs_mean3_pct, 1)}% lower</strong> than the 3-season mean. On 2024, a year it was never
              tuned on, {fmt(c24.skill_vs_last_published_pct, 1)}% and {fmt(c24.skill_vs_mean3_pct, 1)}% (2024 is partly
              published, so treat that as an optimistic reading). Typical error is about {fmt(dev.mae, 2)} t/ha.
            </Note>
            <Note tone="info" title="What goes into it">
              {f.model.inputs}. District yields are published more than a year late, so the latest season used here is{' '}
              {f.baselines.last_published.year}: the model never assumes it knows last season's result.
            </Note>
            {f.notes.map(n => <Note key={n} tone="warn">{n}</Note>)}
          </div>

          <div className="section-card fade-in">
            <div className="section-title">📊 Recorded yield, past forecasts and this forecast</div>
            <p className="section-lede">
              Past forecasts are out-of-sample: each was made by a model trained only on earlier seasons.
            </p>
            <Trajectory f={f} tr={tr.data} />
            {tr.data?.summary && (
              <p className="section-lede" style={{ marginTop: '0.6rem' }}>
                Over this series' {tr.data.summary.n} backtested seasons the model's average error was{' '}
                <strong>{fmt(tr.data.summary.model_mae, 2)} t/ha</strong> against{' '}
                <strong>{fmt(tr.data.summary.last_published_mae, 2)} t/ha</strong> for repeating the last published season.
                One series is a small sample; the figures above are the reliable summary.
              </p>
            )}
          </div>
        </>
      )}
    </Page>
  )
}

function Trajectory({ f, tr }) {
  const rows = new Map()
  const put = (year, patch) => rows.set(year, { year, ...(rows.get(year) || {}), ...patch })
  f.history.forEach(h => put(h.year, { recorded: h.yield }))
  ;(tr?.seasons || []).forEach(s => put(s.year, { past: s.forecast, recorded: s.actual }))
  // ErrorBar takes [distance below, distance above], not absolute bounds
  put(f.forecast_year, { forecast: f.forecast, err: [f.forecast - f.interval.low, f.interval.high - f.forecast] })
  const data = [...rows.values()].sort((a, b) => a.year - b.year)
  return (
    <div style={{ width: '100%', height: 300 }}>
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
          <CartesianGrid {...gridProps} />
          <XAxis dataKey="year" {...axisProps} type="number" domain={['dataMin', 'dataMax']} allowDecimals={false} />
          <YAxis {...axisProps} domain={['auto', 'auto']}
                 label={{ value: f.unit, angle: -90, position: 'insideLeft', style: { fontSize: 11, fill: '#485c4e' } }} />
          <Tooltip {...tooltipStyle} formatter={(v, n) => [fmt(v), n]} />
          <Line dataKey="recorded" name="Recorded" stroke={CHART_COLORS.green} strokeWidth={2.2} dot={{ r: 3 }} connectNulls />
          <Line dataKey="past" name="Past forecast" stroke={CHART_COLORS.amber} strokeWidth={0} dot={{ r: 5, fill: CHART_COLORS.amber }} />
          <Line dataKey="forecast" name="Forecast (bar = 80% range)" stroke={CHART_COLORS.blue} strokeWidth={0} dot={{ r: 7, fill: CHART_COLORS.blue }}>
            <ErrorBar dataKey="err" width={8} strokeWidth={2.5} stroke={CHART_COLORS.blue} />
          </Line>
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

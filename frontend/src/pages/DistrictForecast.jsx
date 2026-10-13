import { ComposedChart, Line, ErrorBar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { ErrorState, Loading, Note, OutlookKpis, Page, PageHeader, SeriesPicker } from './shared'
import { CHART_COLORS, axisProps, gridProps, tooltipStyle, fmt, useGet, useSeriesPicker } from './api'

const signed = v => (v == null ? '—' : `${v > 0 ? '+' : ''}${fmt(v, 1)}%`)
const lowerHigher = v => `${fmt(Math.abs(v), 1)}% ${v >= 0 ? 'lower' : 'higher'}`

/**
 * District outlook: the expected yield of one crop in one district, with a tested range.
 *
 * The expected yield is the mean of the last three PUBLISHED seasons. A machine-learning model was tested against that mean and
 * did not beat it by the bar set in advance, so the page says what the mean is, what it was tested against, and how often its
 * range held, instead of presenting a number as more than it is.
 */
export default function DistrictForecast({ initial }) {
  const picker = useSeriesPicker(initial)   // `initial` comes from a click on the District Map
  const { opts, query: q, year } = picker
  const fc = useGet(q ? `/api/district/forecast?${q}&year=${year}` : null)
  const tr = useGet(q ? `/api/district/track-record?${q}` : null)

  if (opts.loading) return <Page><Loading label="Loading districts…" /></Page>
  if (opts.error) return <Page><ErrorState error={opts.error} /></Page>

  const f = fc.data
  const ev = f?.evidence
  const mean = ev?.mean3
  const model = ev?.model
  const cov = ev?.range_coverage

  return (
    <Page>
      <PageHeader
        icon="🗺️"
        title="District Outlook"
        subtitle="What to expect next season in a district, with the range it has held to and the evidence behind it"
      />

      <div className="section-card fade-in">
        <div className="section-title">🎛️ Choose a series</div>
        <SeriesPicker p={picker} />
      </div>

      {fc.loading && <Loading label="Working out the outlook…" />}
      {fc.error && (
        <div className="section-card fade-in">
          <Note tone="warn" title="No outlook for this selection">{fc.error}</Note>
        </div>
      )}

      {f && (
        <>
          <OutlookKpis f={f} />

          <div className="section-card fade-in">
            <div className="section-title">⚖️ How much to trust this</div>
            <Note tone={mean.mean3_vs_last_published_pct >= 0 ? 'info' : 'warn'}
                  title={mean.mean3_vs_last_published_pct >= 0 ? `For ${f.crop}, the 3-season mean has been a better guide than last season's figure`
                                                               : `For ${f.crop}, last season's figure has been a better guide than the 3-season mean`}>
              On seasons not yet seen (2018–2023, {mean.n.toLocaleString('en-IN')} forecasts of {f.crop}) the mean of the last three published seasons had
              an error {lowerHigher(mean.mean3_vs_last_published_pct)} than repeating the last published season ({fmt(mean.mean3_mae, 2)} against{' '}
              {fmt(mean.last_published_mae, 2)} t/ha). It is the expected yield here because it has been the better of the two simple choices for most
              crops, not because it is clever.
            </Note>
            <Note tone="info" title="A model was tested against it">
              A machine-learning model trained on the whole dataset was tested the way a forecaster would meet the data, knowing only what had been
              published by then. For {f.crop} its error was {lowerHigher(model.dev.skill_vs_mean3_pct)} than this mean on 2018–23 ({model.years_better_than_mean3} of 6
              years better, {signed(model.confirm_2024.skill_vs_mean3_pct)} in 2024). The bar set in advance was +2.0%, in at least 4 of 6 years, and not worse
              in 2024; no crop cleared it, so the model is not used.
            </Note>
            <Note tone="info" title="How often the range held">
              Ranges built this way held the recorded yield {fmt(100 * cov.dev, 0)}% of the time on 2018–23 and {fmt(100 * cov.confirm_2024, 0)}% in 2024
              (80% intended), across all crops. District yields are published more than a year late, so the latest season used here is{' '}
              {f.baselines.last_published.year}: nothing assumes last season's result is known.
            </Note>
            {f.notes.map(n => <Note key={n} tone="warn">{n}</Note>)}
          </div>

          <div className="section-card fade-in">
            <div className="section-title">📊 Recorded yield, past expectations and this one</div>
            <p className="section-lede">
              Past expectations are out-of-sample: each is the mean of the seasons that had been published by then.
            </p>
            <Trajectory f={f} tr={tr.data} />
            {tr.data?.summary && (
              <p className="section-lede" style={{ marginTop: '0.6rem' }}>
                Over this series' {tr.data.summary.n} past seasons the 3-season mean's average error was{' '}
                <strong>{fmt(tr.data.summary.mean_mae, 2)} t/ha</strong> against{' '}
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
          <Line dataKey="past" name="Past expectation (3-season mean)" stroke={CHART_COLORS.amber} strokeWidth={0} dot={{ r: 5, fill: CHART_COLORS.amber }} />
          <Line dataKey="forecast" name="Expected (bar = 80% range)" stroke={CHART_COLORS.blue} strokeWidth={0} dot={{ r: 7, fill: CHART_COLORS.blue }}>
            <ErrorBar dataKey="err" width={8} strokeWidth={2.5} stroke={CHART_COLORS.blue} />
          </Line>
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

import { useState, useMemo } from 'react'
import {
  BarChart, Bar as RBar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Cell,
} from 'recharts'
import { ErrorState, KpiCard, Loading, Note, PageHeader, Page, Spec } from './shared'
import { useApi, CHART_COLORS, axisProps, gridProps, tooltipStyle, fmt } from './api'

const signed = v => (v == null ? '—' : `${v > 0 ? '+' : ''}${fmt(v, 1)}%`)

/**
 * Per-crop distribution of district yields, plus how well the expected yield (the mean of the last three published seasons) and
 * the model tested against it did on seasons they had not seen: the two questions a user has about a crop, on one page.
 */
export default function CropInsights({ options }) {
  const [crop, setCrop] = useState('Rice')
  const { data, error, loading } = useApi(`/api/crop-insights/${encodeURIComponent(crop)}`)
  const { data: model } = useApi('/api/model')

  const histogram = useMemo(() => {
    const h = data?.histogram
    if (!h) return []
    return h.counts.map((c, i) => ({ bin: (h.edges[i] + h.edges[i + 1]) / 2, label: fmt(h.edges[i], 1), count: c }))
  }, [data])

  const tested = model?.crops?.[crop]
  const mean = tested?.mean3
  const mod = tested?.model

  return (
    <Page>
      <PageHeader
        icon="🌾"
        title="Crop Insights"
        subtitle="Yield distribution across districts, and how well its next-season outlook has held up"
        right={
          <div className="form-field" style={{ minWidth: 210 }}>
            <label>Select crop</label>
            <select value={crop} onChange={e => setCrop(e.target.value)}>
              {options?.crops?.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
        }
      />

      {loading && <Loading label={`Loading ${crop}…`} />}
      {error && <ErrorState error={error} />}
      {data?.error && (
        <Note tone="warn" title="Not available">{crop} has no usable yield records in the dataset.</Note>
      )}

      {data && !data.error && (
        <>
          <div className="kpi-row fade-in">
            <KpiCard icon="📋" iconBg="var(--green-100)" label="RECORDS"
              value={data.records.toLocaleString('en-IN')}
              sub={`${data.districts} districts · ${data.states} states · ${data.year_min}–${data.year_max}`} />
            <KpiCard icon="📊" iconBg="var(--blue-bg)" label="AVERAGE YIELD"
              value={fmt(data.avg)} sub={`${data.unit} (total production ÷ total area)`} />
            <KpiCard icon="📈" iconBg="var(--amber-bg)" label="TYPICAL DISTRICT RANGE"
              value={`${fmt(data.p5, 1)}–${fmt(data.p95, 1)}`} sub={`${data.unit}, 5th to 95th percentile`} />
            <KpiCard
              icon="🎯" iconBg="var(--purple-bg)" label="3-SEASON MEAN VS LAST SEASON"
              value={tested ? signed(mean.mean3_vs_last_published_pct) : 'no outlook'}
              sub={tested ? `lower error, ${mean.n.toLocaleString('en-IN')} unseen forecasts, 2018–23` : 'too little history to test'}
              title="How much lower the error of the mean of the last three published seasons was than repeating the last published season, on seasons it had not seen."
            />
          </div>

          <div className="section-card fade-in">
            <div className="section-title">📉 Yield distribution</div>
            <p className="section-lede">
              How {crop} yields are spread across all {data.records.toLocaleString('en-IN')} district records. A wide or
              multi-peaked spread means regional conditions dominate, and a single national average hides more than it reveals.
            </p>
            <div style={{ width: '100%', height: 320 }}>
              <ResponsiveContainer>
                <BarChart data={histogram} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
                  <CartesianGrid {...gridProps} />
                  <XAxis dataKey="label" {...axisProps} interval={Math.ceil(histogram.length / 10)}
                         label={{ value: `Yield (${data.unit})`, position: 'insideBottom', offset: -2, style: { fontSize: 11, fill: '#485c4e' } }} />
                  <YAxis {...axisProps} label={{ value: 'Records', angle: -90, position: 'insideLeft', style: { fontSize: 11, fill: '#485c4e' } }} />
                  <Tooltip {...tooltipStyle}
                           labelFormatter={l => `≈ ${l} ${data.unit}`}
                           formatter={v => [v, 'records']} />
                  <ReferenceLine x={histogram.find(h => h.bin >= data.p50)?.label} stroke={CHART_COLORS.amber}
                                 strokeDasharray="5 4"
                                 label={{ value: `median ${fmt(data.p50)}`, fontSize: 10, fill: CHART_COLORS.amber, position: 'top' }} />
                  <RBar dataKey="count" radius={[4, 4, 0, 0]}>
                    {histogram.map((h, i) => (
                      <Cell key={i} fill={h.bin > data.p50 ? CHART_COLORS.green : '#a8c9b4'} />
                    ))}
                  </RBar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <p className="section-lede" style={{ marginTop: '0.4rem' }}>
              The tails beyond the 0.5th and 99.5th percentile are folded into the end bars.
            </p>
          </div>

          <div className="section-card fade-in">
            <div className="section-title">🎯 How well does the outlook hold up for {crop}?</div>
            {!tested && (
              <Note tone="info">
                {crop} has too few district series with a recent record to be tested, so no outlook is offered and only its history is shown.
              </Note>
            )}
            {tested && (
              <>
                <div className="spec-grid">
                  <Spec label="Unseen forecasts, 2018–23" value={mean.n.toLocaleString('en-IN')} />
                  <Spec label="3-season mean error (MAE)" value={`${fmt(mean.mean3_mae, 3)} ${data.unit}`} />
                  <Spec label="Last published season error" value={`${fmt(mean.last_published_mae, 3)} ${data.unit}`} />
                  <Spec label="Tested model vs the mean" value={`${signed(mod.dev.skill_vs_mean3_pct)} (${mod.years_better_than_mean3} of 6 years better)`} wide />
                  <Spec label="Tested model, 2024" value={`${signed(mod.confirm_2024.skill_vs_mean3_pct)} vs the mean`} />
                </div>
                <Note tone={mean.mean3_vs_last_published_pct >= 0 ? 'info' : 'warn'}
                      title={mean.mean3_vs_last_published_pct >= 0 ? 'The 3-season mean has been the better simple guide' : "Last season's figure has been the better simple guide"}>
                  The expected yield is the mean of the last three published seasons; its error was {fmt(Math.abs(mean.mean3_vs_last_published_pct), 1)}%{' '}
                  {mean.mean3_vs_last_published_pct >= 0 ? 'lower' : 'higher'} than repeating the last published season. A machine-learning model was
                  tested against it and {mod.dev.skill_vs_mean3_pct >= 2 ? 'came close to the bar set in advance but did not clear it (+2.0%, in at least 4 of 6 years, and not worse in 2024)' : 'did not beat it'}, so
                  the model is not used. 2024 is partly published, so read that year as a rough check.
                </Note>
              </>
            )}
          </div>
        </>
      )}
    </Page>
  )
}

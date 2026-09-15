import { useState, useMemo } from 'react'
import {
  BarChart, Bar as RBar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Cell,
} from 'recharts'
import { ErrorState, KpiCard, Loading, Note, PageHeader, Page, Spec } from './shared'
import { useApi, CHART_COLORS, axisProps, gridProps, tooltipStyle, fmt } from './api'

/**
 * Per-crop distribution, plus how well the model predicts that specific crop —
 * the two questions a user has about a crop, answered on one page.
 */
export default function CropInsights({ options }) {
  const [crop, setCrop] = useState('Rice')
  const { data, error, loading } = useApi(`/api/crop-insights/${encodeURIComponent(crop)}`)
  const { data: metrics } = useApi('/api/model-metrics')

  // Bin the raw yield values into a histogram in the browser: the API returns the
  // values themselves, so binning here keeps bin count adjustable without a round-trip.
  const histogram = useMemo(() => {
    const vals = data?.histogram_values
    if (!vals?.length) return []
    const min = Math.min(...vals), max = Math.max(...vals)
    const bins = 32
    const width = (max - min) / bins || 1
    const counts = new Array(bins).fill(0)
    vals.forEach(v => {
      const i = Math.min(bins - 1, Math.floor((v - min) / width))
      counts[i] += 1
    })
    return counts.map((c, i) => ({
      bin: min + i * width + width / 2,
      label: fmt(min + i * width, 1),
      count: c,
    }))
  }, [data])

  const cropAccuracy = metrics?.per_crop?.find(c => c.crop === crop.trim())
  const rank = useMemo(() => {
    if (!metrics?.per_crop || !cropAccuracy) return null
    const sorted = [...metrics.per_crop].sort((a, b) => {
      const ra = a.mean_actual > 0 ? a.mae / a.mean_actual : 99
      const rb = b.mean_actual > 0 ? b.mae / b.mean_actual : 99
      return ra - rb
    })
    return { pos: sorted.findIndex(c => c.crop === crop.trim()) + 1, total: sorted.length }
  }, [metrics, cropAccuracy, crop])

  const relErr = cropAccuracy && cropAccuracy.mean_actual > 0
    ? (cropAccuracy.mae / cropAccuracy.mean_actual) * 100 : null

  return (
    <Page>
      <PageHeader
        icon="🌾"
        title="Crop Insights"
        subtitle="Yield distribution and model reliability, crop by crop"
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
        <Note tone="warn" title="Not available">
          {crop} is not in the modelled dataset. Coconut is excluded because it is recorded in
          nuts per hectare inside a tonnes-per-hectare column.
        </Note>
      )}

      {data && !data.error && (
        <>
          <div className="kpi-row fade-in">
            <KpiCard icon="📋" iconBg="var(--green-100)" label="RECORDS"
              value={data.records.toLocaleString('en-IN')} sub="historical observations" />
            <KpiCard icon="📊" iconBg="var(--blue-bg)" label="AVERAGE YIELD"
              value={fmt(data.avg_yield)} sub={data.unit} />
            <KpiCard icon="📈" iconBg="var(--amber-bg)" label="RANGE"
              value={`${fmt(data.min_yield, 1)}–${fmt(data.max_yield, 1)}`} sub={data.unit} />
            <KpiCard
              icon="🎯" iconBg="var(--purple-bg)" label="MODEL ERROR (MAE)"
              value={cropAccuracy ? fmt(cropAccuracy.mae, 2) : '—'}
              sub={relErr !== null ? `${fmt(relErr, 0)}% of mean yield` : 'not in holdout'}
              title="Mean absolute error for this crop on the 2018-2020 holdout."
            />
          </div>

          <div className="section-card fade-in">
            <div className="section-title">📉 Yield distribution</div>
            <p className="section-lede">
              How {data.crop.trim()} yields are spread across all {data.records.toLocaleString('en-IN')}{' '}
              records. A wide or multi-peaked spread means regional conditions dominate, and a
              single national average hides more than it reveals.
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
                  <ReferenceLine x={fmt(data.avg_yield, 1)} stroke={CHART_COLORS.amber}
                                 strokeDasharray="5 4"
                                 label={{ value: `mean ${fmt(data.avg_yield)}`, fontSize: 10, fill: CHART_COLORS.amber, position: 'top' }} />
                  <RBar dataKey="count" radius={[4, 4, 0, 0]}>
                    {histogram.map((h, i) => (
                      <Cell key={i} fill={h.bin > data.avg_yield ? CHART_COLORS.green : '#a8c9b4'} />
                    ))}
                  </RBar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="section-card fade-in">
            <div className="section-title">🎯 How reliable is the model for {data.crop.trim()}?</div>
            {cropAccuracy ? (
              <>
                <div className="spec-grid">
                  <Spec label="Holdout records" value={cropAccuracy.n} />
                  <Spec label="Mean absolute error" value={`${fmt(cropAccuracy.mae, 3)} ${data.unit}`} />
                  <Spec label="Mean actual yield" value={`${fmt(cropAccuracy.mean_actual)} ${data.unit}`} />
                  <Spec label="Error as % of mean" value={relErr !== null ? `${fmt(relErr, 1)}%` : '—'} />
                  {rank && <Spec label="Accuracy rank" value={`${rank.pos} of ${rank.total} crops`} />}
                </div>
                <Note tone={relErr > 50 ? 'danger' : relErr > 25 ? 'warn' : 'ok'}
                      title={relErr > 50 ? 'Treat these forecasts with caution'
                           : relErr > 25 ? 'Moderate reliability'
                           : 'Reliable for this crop'}>
                  {relErr > 50 ? (
                    <>Typical error is {fmt(relErr, 0)}% of this crop's mean yield, which is large
                    enough that a forecast should inform planning only alongside local knowledge.
                    High-variance crops with few records are the hardest cases in this dataset.</>
                  ) : relErr > 25 ? (
                    <>Typical error runs about {fmt(relErr, 0)}% of mean yield. Useful for relative
                    comparisons — which inputs or seasons help — more than for absolute tonnage.</>
                  ) : (
                    <>Typical error is {fmt(relErr, 0)}% of mean yield, among the stronger results
                    in the dataset. Absolute forecasts for this crop are reasonably dependable.</>
                  )}
                </Note>
              </>
            ) : (
              <Note tone="info">
                {data.crop.trim()} has fewer than five records in the 2018–2020 holdout, so no
                per-crop error is reported. A figure from so few points would not be meaningful.
              </Note>
            )}
          </div>
        </>
      )}
    </Page>
  )
}



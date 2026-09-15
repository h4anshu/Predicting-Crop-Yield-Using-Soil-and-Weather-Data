import { useState, useMemo } from 'react'
import {
  LineChart, Line, BarChart, Bar as RBar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend, ScatterChart, Scatter, ZAxis,
} from 'recharts'
import { Bar, ErrorState, KpiCard, Loading, Note, PageHeader, Page, Spec } from './shared'
import { useApi, CHART_COLORS, axisProps, gridProps, tooltipStyle, fmt } from './api'

/**
 * The agronomic inputs behind every prediction.
 *
 * This page is also where the dataset's granularity limit is stated plainly: soil is
 * one profile per state and weather one observation per state-year, which is exactly
 * why the model resolves regional rather than field-level conditions. Burying that
 * would leave a reader to discover it themselves and distrust the rest.
 */
export default function SoilClimate({ options }) {
  const { data, error, loading } = useApi('/api/soil-climate')
  const [state, setState] = useState('Punjab')
  const [metric, setMetric] = useState('total_rainfall_mm')

  const soilByState = useMemo(() => {
    const map = {}
    ;(data?.soil || []).forEach(s => { map[s.state.trim()] = s })
    return map
  }, [data])

  if (loading) return <Page><Loading label="Loading soil and climate data…" /></Page>
  if (error) return <Page><ErrorState error={error} /></Page>
  if (!data) return null

  const soil = soilByState[state]
  const w = data.weather[state] || data.weather[Object.keys(data.weather)[0]] || {}
  const series = (w.years || []).map((y, i) => ({
    year: y,
    total_rainfall_mm: w.rainfall[i],
    avg_temp_c: w.temp[i],
    avg_humidity_percent: w.humidity[i],
  }))

  const allSoil = (data.soil || []).map(s => ({ ...s, state: s.state.trim() }))
  const npkRanked = [...allSoil].sort((a, b) => (b.N + b.P + b.K) - (a.N + a.P + a.K))
  const avgRain = series.length ? series.reduce((a, b) => a + b.total_rainfall_mm, 0) / series.length : 0
  const avgTemp = series.length ? series.reduce((a, b) => a + b.avg_temp_c, 0) / series.length : 0

  const phBand = soil ? (soil.pH < 6.0 ? 'Acidic' : soil.pH > 7.5 ? 'Alkaline' : 'Optimal') : '—'
  const phTone = phBand === 'Optimal' ? 'var(--green-600)' : 'var(--amber)'

  return (
    <Page>
      <PageHeader
        icon="🧪"
        title="Soil & Climate"
        subtitle="The agronomic conditions the model reads for each region"
        right={
          <div className="form-field" style={{ minWidth: 200 }}>
            <label>State</label>
            <select value={state} onChange={e => setState(e.target.value)}>
              {(options?.states || Object.keys(data.weather)).map(s => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
        }
      />

      <div className="kpi-row fade-in">
        <KpiCard icon="🧪" iconBg="var(--green-100)" label="SOIL NPK"
          value={soil ? `${soil.N}·${soil.P}·${soil.K}` : '—'} sub="N · P · K (kg/ha)" />
        <KpiCard icon="⚗️" iconBg="var(--amber-bg)" label="SOIL pH"
          value={soil ? fmt(soil.pH, 1) : '—'} sub={phBand} />
        <KpiCard icon="🌧️" iconBg="var(--blue-bg)" label="AVG RAINFALL"
          value={fmt(avgRain, 0)} sub="mm/year, 1997–2020" />
        <KpiCard icon="🌡️" iconBg="var(--red-bg)" label="AVG TEMPERATURE"
          value={`${fmt(avgTemp, 1)}°C`} sub="1997–2020" />
      </div>

      {/* ─── The caveat, stated up front ────────────────────────────── */}
      <div className="section-card fade-in">
        <div className="section-title">📐 How precise is this data?</div>
        <Note tone="warn" title="Regional resolution, not field resolution">
          {data.granularity.implication}
          <div className="spec-grid" style={{ marginTop: '0.8rem' }}>
            <Spec label="Soil" value={data.granularity.soil} wide />
            <Spec label="Weather" value={data.granularity.weather} wide />
          </div>
        </Note>
        <Note tone="info" title="What that means in practice">
          Forecasts respond to the conditions typical of a region, not to a soil test from one
          field. Adjusting the soil inputs on the Dashboard explores how a field differing from its
          regional baseline might perform — useful for comparison, but not a substitute for
          field-level agronomy. Closing this gap needs district-level soil and weather records,
          which is a data-collection problem rather than a modelling one.
        </Note>
      </div>

      <div className="section-card fade-in">
        <div className="section-title">
          🌦️ Climate history — {state}
          <div className="seg-control">
            <button className={metric === 'total_rainfall_mm' ? 'active' : ''}
                    onClick={() => setMetric('total_rainfall_mm')}>Rainfall</button>
            <button className={metric === 'avg_temp_c' ? 'active' : ''}
                    onClick={() => setMetric('avg_temp_c')}>Temperature</button>
            <button className={metric === 'avg_humidity_percent' ? 'active' : ''}
                    onClick={() => setMetric('avg_humidity_percent')}>Humidity</button>
          </div>
        </div>
        <div style={{ width: '100%', height: 300 }}>
          <ResponsiveContainer>
            <LineChart data={series} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="year" {...axisProps} />
              <YAxis {...axisProps} domain={['auto', 'auto']}
                     label={{ value: METRIC_UNITS[metric], angle: -90, position: 'insideLeft', style: { fontSize: 11, fill: '#485c4e' } }} />
              <Tooltip {...tooltipStyle}
                       formatter={v => [`${fmt(v, 1)} ${METRIC_UNITS[metric]}`, METRIC_LABELS[metric]]} />
              <Line type="monotone" dataKey={metric} stroke={METRIC_COLORS[metric]}
                    strokeWidth={2.5} dot={{ r: 2.5 }} name={METRIC_LABELS[metric]} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="chart-summary">
          {series.length} yearly observations for {state}, 1997–2020.
        </div>
      </div>

      <div className="split-grid">
        <div className="section-card fade-in">
          <div className="section-title">🧫 Soil profile — {state}</div>
          {soil ? (
            <>
              <div className="nutrient-list">
                <Nutrient label="Nitrogen (N)" value={soil.N} max={160} unit="kg/ha"
                          hint="Drives vegetative growth. The strongest nutrient signal in this model." />
                <Nutrient label="Phosphorus (P)" value={soil.P} max={90} unit="kg/ha"
                          hint="Root development and grain fill. The single most responsive input in v3." />
                <Nutrient label="Potassium (K)" value={soil.K} max={60} unit="kg/ha"
                          hint="Water regulation and stress tolerance." />
              </div>
              <div className="ph-strip">
                <div className="ph-strip-label">
                  Soil pH <strong style={{ color: phTone }}>{fmt(soil.pH, 1)}</strong> — {phBand}
                </div>
                <div className="ph-scale">
                  <div className="ph-optimal-band" />
                  <div className="ph-marker" style={{ left: `${((soil.pH - 4) / 6) * 100}%` }} />
                </div>
                <div className="ph-ticks"><span>4.0</span><span>6.0–7.5 optimal</span><span>10.0</span></div>
              </div>
            </>
          ) : <Note tone="info">No soil profile recorded for {state}.</Note>}
        </div>

        <div className="section-card fade-in">
          <div className="section-title">🏅 Soil fertility across states</div>
          <p className="section-lede">Ranked by total NPK. {state} is highlighted.</p>
          <div style={{ width: '100%', height: Math.max(320, npkRanked.length * 19) }}>
            <ResponsiveContainer>
              <BarChart data={npkRanked} layout="vertical" margin={{ top: 4, right: 24, left: 8, bottom: 4 }}>
                <CartesianGrid {...gridProps} horizontal={false} />
                <XAxis type="number" {...axisProps} />
                <YAxis type="category" dataKey="state" width={130} {...axisProps} interval={0} />
                <Tooltip {...tooltipStyle} formatter={(v, n) => [`${v} kg/ha`, n]} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <RBar dataKey="N" stackId="npk" fill={CHART_COLORS.green} name="N" />
                <RBar dataKey="P" stackId="npk" fill={CHART_COLORS.blue} name="P" />
                <RBar dataKey="K" stackId="npk" fill={CHART_COLORS.amber} name="K" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="section-card fade-in">
        <div className="section-title">💧 Rainfall against temperature</div>
        <p className="section-lede">
          Every state-year in the dataset. Clusters correspond to India's climate zones — the
          regional structure the model actually learns from.
        </p>
        <div style={{ width: '100%', height: 340 }}>
          <ResponsiveContainer>
            <ScatterChart margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
              <CartesianGrid {...gridProps} vertical />
              <XAxis type="number" dataKey="temp" name="Temperature" {...axisProps}
                     domain={['auto', 'auto']}
                     label={{ value: 'Avg temperature (°C)', position: 'insideBottom', offset: -4, style: { fontSize: 11, fill: '#485c4e' } }} />
              <YAxis type="number" dataKey="rain" name="Rainfall" {...axisProps}
                     label={{ value: 'Rainfall (mm)', angle: -90, position: 'insideLeft', style: { fontSize: 11, fill: '#485c4e' } }} />
              <ZAxis range={[16, 16]} />
              <Tooltip {...tooltipStyle} cursor={{ strokeDasharray: '3 3' }}
                       formatter={(v, n) => [fmt(v, 1), n]} />
              <Scatter name="Other states" data={scatterOf(data.weather, state, false)} fill="rgba(31,122,61,0.22)" />
              <Scatter name={state} data={scatterOf(data.weather, state, true)} fill={CHART_COLORS.amber} />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </div>
    </Page>
  )
}

const METRIC_LABELS = {
  total_rainfall_mm: 'Rainfall',
  avg_temp_c: 'Temperature',
  avg_humidity_percent: 'Humidity',
}
const METRIC_UNITS = {
  total_rainfall_mm: 'mm',
  avg_temp_c: '°C',
  avg_humidity_percent: '%',
}
const METRIC_COLORS = {
  total_rainfall_mm: CHART_COLORS.blue,
  avg_temp_c: CHART_COLORS.red,
  avg_humidity_percent: CHART_COLORS.teal,
}

function scatterOf(weather, state, isSelected) {
  const out = []
  Object.entries(weather || {}).forEach(([st, w]) => {
    if ((st === state) !== isSelected) return
    ;(w.years || []).forEach((y, i) => {
      out.push({ temp: w.temp[i], rain: w.rainfall[i], state: st, year: y })
    })
  })
  return out
}

function Nutrient({ label, value, max, unit, hint }) {
  return (
    <div className="nutrient-item" title={hint}>
      <div className="nutrient-head">
        <span className="nutrient-label">{label}</span>
        <span className="nutrient-value">{value} <small>{unit}</small></span>
      </div>
      <Bar value={value} max={max} height={10} />
      <div className="nutrient-hint">{hint}</div>
    </div>
  )
}



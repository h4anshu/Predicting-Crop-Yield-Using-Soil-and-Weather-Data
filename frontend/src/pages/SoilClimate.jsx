import { useState } from 'react'
import {
  LineChart, Line, BarChart, Bar as RBar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ScatterChart, Scatter, ZAxis, Cell,
} from 'recharts'
import { Bar, ErrorState, KpiCard, Loading, Note, PageHeader, Page, Spec } from './shared'
import { useApi, CHART_COLORS, axisProps, gridProps, tooltipStyle, fmt } from './api'

/**
 * The soil and weather records behind the dataset, by state.
 *
 * Soil is the Soil Health Card programme's own lab results (the share of tested samples rated low or high), not an assumed
 * constant; weather is IMD gridded rainfall and temperature over the Kharif and Rabi windows. Both are district-level data
 * summarised to a state here, and the page states plainly what they can and cannot say.
 */
const NUTRIENTS = [
  { key: 'n', label: 'Nitrogen (N)', hint: 'Share of samples rated low. Drives vegetative growth.' },
  { key: 'p', label: 'Phosphorus (P)', hint: 'Share of samples rated low. Root development and grain fill.' },
  { key: 'k', label: 'Potassium (K)', hint: 'Share of samples rated low. Water regulation and stress tolerance.' },
  { key: 'oc', label: 'Organic carbon', hint: 'Share of samples rated low. A proxy for soil health.' },
]
const MICRO = [
  { key: 'zn_deficient', label: 'Zinc' }, { key: 'fe_deficient', label: 'Iron' },
  { key: 'b_deficient', label: 'Boron' }, { key: 's_deficient', label: 'Sulphur' },
]
const METRICS = {
  kharif_rain: { label: 'Kharif rainfall', unit: 'mm', color: CHART_COLORS.blue },
  rabi_rain: { label: 'Rabi rainfall', unit: 'mm', color: CHART_COLORS.teal },
  kharif_tmax: { label: 'Kharif max temperature', unit: '°C', color: CHART_COLORS.red },
  rabi_tmin: { label: 'Rabi min temperature', unit: '°C', color: CHART_COLORS.purple },
}
const pct = v => (v == null ? '—' : `${fmt(100 * v, 0)}%`)
const mean = a => { const v = (a || []).filter(x => x != null); return v.length ? v.reduce((s, x) => s + x, 0) / v.length : null }

export default function SoilClimate({ options }) {
  const { data, error, loading } = useApi('/api/soil-climate')
  const [state, setState] = useState('Punjab')
  const [metric, setMetric] = useState('kharif_rain')
  const [nutrient, setNutrient] = useState('n')

  if (loading) return <Page><Loading label="Loading soil and climate data…" /></Page>
  if (error) return <Page><ErrorState error={error} /></Page>
  if (!data) return null

  const soil = data.soil[state]
  const w = data.weather[state]
  const series = (w?.years || []).map((y, i) => ({ year: y, value: w[metric]?.[i] ?? null }))
  const ranked = Object.entries(data.soil)
    .map(([st, s]) => ({ state: st, value: s[`${nutrient}_low`] }))
    .filter(r => r.value != null).sort((a, b) => b.value - a.value)
  const scatter = (isSelected) => Object.entries(data.weather).flatMap(([st, v]) =>
    (st === state) !== isSelected ? [] : v.years.map((y, i) => ({ rain: v.kharif_rain?.[i], temp: v.kharif_tmax?.[i], state: st, year: y }))
      .filter(r => r.rain != null && r.temp != null))
  const m = METRICS[metric]
  const states = (options?.states || Object.keys(data.weather)).filter(s => data.soil[s] || data.weather[s])

  return (
    <Page>
      <PageHeader
        icon="🧪"
        title="Soil & Climate"
        subtitle="The soil test results and weather recorded for each region"
        right={
          <div className="form-field" style={{ minWidth: 200 }}>
            <label>State</label>
            <select value={state} onChange={e => setState(e.target.value)}>
              {states.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        }
      />

      <div className="kpi-row fade-in">
        <KpiCard icon="🧫" iconBg="var(--green-100)" label="SOIL SAMPLES TESTED"
          value={soil ? soil.samples.toLocaleString('en-IN') : '—'} sub={soil ? `${soil.districts} districts, 2023–25` : 'no Soil Health Card data'} />
        <KpiCard icon="🌱" iconBg="var(--amber-bg)" label="LOW IN NITROGEN" value={pct(soil?.n_low)} sub="of tested samples" />
        <KpiCard icon="⚗️" iconBg="var(--blue-bg)" label="ACIDIC · ALKALINE" value={soil ? `${pct(soil.ph_acidic)} · ${pct(soil.ph_alkaline)}` : '—'} sub="of tested samples" />
        <KpiCard icon="🌧️" iconBg="var(--purple-bg)" label="AVG KHARIF RAINFALL"
          value={w ? `${fmt(mean(w.kharif_rain), 0)} mm` : '—'} sub={w ? `${w.years[0]}–${w.years[w.years.length - 1]}, window Jun–Oct` : 'no weather'} />
      </div>

      <div className="section-card fade-in">
        <div className="section-title">📐 How precise is this data?</div>
        <Note tone="warn" title="District records, summarised to a state">
          {data.granularity.implication}
          <div className="spec-grid" style={{ marginTop: '0.8rem' }}>
            <Spec label="Soil" value={data.granularity.soil} wide />
            <Spec label="Weather" value={data.granularity.weather} wide />
          </div>
        </Note>
        <Note tone="info" title="What they are used for">
          Weather and soil are in the dataset for every district, but the forecasting model does not use them: with the real publication lag
          they improved its error by less than 2%, below the bar set in advance (see the Model page). They describe the regions behind
          the yields; they do not drive the forecast.
        </Note>
      </div>

      <div className="section-card fade-in">
        <div className="section-title">
          🌦️ Climate history — {state}
          <div className="seg-control">
            {Object.entries(METRICS).map(([k, v]) => (
              <button key={k} className={metric === k ? 'active' : ''} onClick={() => setMetric(k)}>{v.label}</button>
            ))}
          </div>
        </div>
        {series.some(r => r.value != null) ? (
          <div style={{ width: '100%', height: 300 }}>
            <ResponsiveContainer>
              <LineChart data={series} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="year" {...axisProps} />
                <YAxis {...axisProps} domain={['auto', 'auto']}
                       label={{ value: m.unit, angle: -90, position: 'insideLeft', style: { fontSize: 11, fill: '#485c4e' } }} />
                <Tooltip {...tooltipStyle} formatter={v => [`${fmt(v, 1)} ${m.unit}`, m.label]} />
                <Line type="monotone" dataKey="value" stroke={m.color} strokeWidth={2.5} dot={{ r: 2.5 }} name={m.label} connectNulls />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : <Note tone="info">No weather is recorded for {state}.</Note>}
        <div className="chart-summary">
          {series.length} yearly values for {state}; each is the mean over its districts of the Kharif (Jun–Oct) or Rabi (Nov–mid-Apr) window.
        </div>
      </div>

      <div className="split-grid">
        <div className="section-card fade-in">
          <div className="section-title">🧫 Soil profile — {state}</div>
          {soil ? (
            <>
              <div className="nutrient-list">
                {NUTRIENTS.map(n => (
                  <div className="nutrient-item" key={n.key} title={n.hint}>
                    <div className="nutrient-head">
                      <span className="nutrient-label">{n.label}</span>
                      <span className="nutrient-value">{pct(soil[`${n.key}_low`])} <small>low</small> · {pct(soil[`${n.key}_high`])} <small>high</small></span>
                    </div>
                    <Bar value={100 * soil[`${n.key}_low`]} max={100} height={10} />
                    <div className="nutrient-hint">{n.hint}</div>
                  </div>
                ))}
              </div>
              <p className="section-lede" style={{ marginTop: '0.8rem' }}>
                Share of tested samples deficient in a micronutrient:{' '}
                {MICRO.map((x, i) => <span key={x.key}>{i ? ' · ' : ''}{x.label} <strong>{pct(soil[x.key])}</strong></span>)}.
                Saline samples: <strong>{pct(soil.ec_saline)}</strong>.
              </p>
            </>
          ) : <Note tone="info">No Soil Health Card results for {state}.</Note>}
        </div>

        <div className="section-card fade-in">
          <div className="section-title">
            🏅 Across states
            <div className="seg-control">
              {NUTRIENTS.map(n => <button key={n.key} className={nutrient === n.key ? 'active' : ''} onClick={() => setNutrient(n.key)}>{n.key.toUpperCase()}</button>)}
            </div>
          </div>
          <p className="section-lede">Share of samples rated low in {NUTRIENTS.find(n => n.key === nutrient).label.toLowerCase()}. {state} is highlighted.</p>
          <div style={{ width: '100%', height: Math.max(320, ranked.length * 19) }}>
            <ResponsiveContainer>
              <BarChart data={ranked} layout="vertical" margin={{ top: 4, right: 24, left: 8, bottom: 4 }}>
                <CartesianGrid {...gridProps} horizontal={false} />
                <XAxis type="number" domain={[0, 1]} tickFormatter={v => `${Math.round(v * 100)}%`} {...axisProps} />
                <YAxis type="category" dataKey="state" width={130} {...axisProps} interval={0} />
                <Tooltip {...tooltipStyle} formatter={v => [pct(v), 'low']} />
                <RBar dataKey="value" radius={[0, 4, 4, 0]}>
                  {ranked.map(r => <Cell key={r.state} fill={r.state === state ? CHART_COLORS.amber : CHART_COLORS.green} />)}
                </RBar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="section-card fade-in">
        <div className="section-title">💧 Kharif rainfall against maximum temperature</div>
        <p className="section-lede">
          Every state-year in the dataset. Clusters correspond to India's climate zones, the regional structure behind the yields.
        </p>
        <div style={{ width: '100%', height: 340 }}>
          <ResponsiveContainer>
            <ScatterChart margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
              <CartesianGrid {...gridProps} vertical />
              <XAxis type="number" dataKey="temp" name="Max temperature" {...axisProps} domain={['auto', 'auto']}
                     label={{ value: 'Mean max temperature, Kharif window (°C)', position: 'insideBottom', offset: -4, style: { fontSize: 11, fill: '#485c4e' } }} />
              <YAxis type="number" dataKey="rain" name="Rainfall" {...axisProps}
                     label={{ value: 'Rainfall (mm)', angle: -90, position: 'insideLeft', style: { fontSize: 11, fill: '#485c4e' } }} />
              <ZAxis range={[16, 16]} />
              <Tooltip {...tooltipStyle} cursor={{ strokeDasharray: '3 3' }} formatter={(v, n) => [fmt(v, 1), n]} />
              <Scatter name="Other states" data={scatter(false)} fill="rgba(31,122,61,0.22)" />
              <Scatter name={state} data={scatter(true)} fill={CHART_COLORS.amber} />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </div>
    </Page>
  )
}

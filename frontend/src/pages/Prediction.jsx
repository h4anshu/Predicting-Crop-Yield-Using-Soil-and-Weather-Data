import { useState, useEffect, useCallback } from 'react'
import {
  BarChart, Bar as RBar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ErrorBar,
} from 'recharts'
import { ErrorState, Loading, Note, PageHeader, Page } from './shared'
import { CHART_COLORS, axisProps, gridProps, tooltipStyle, fmt } from './api'
import { API_BASE, STATE_DEFAULTS } from '../constants'

/**
 * Scenario workspace: run several input sets side by side.
 *
 * The Dashboard answers "what will this field yield". This answers "which of these
 * options is better", which is the question that actually drives a planting decision.
 * It is also the page where v3's input responsiveness is visible -- with v2, changing
 * pH between scenarios would have produced near-identical bars.
 */

const FIELDS = [
  { key: 'N', label: 'Nitrogen (N)', min: 0, max: 200, step: 1, unit: 'kg/ha' },
  { key: 'P', label: 'Phosphorus (P)', min: 0, max: 120, step: 1, unit: 'kg/ha' },
  { key: 'K', label: 'Potassium (K)', min: 0, max: 100, step: 1, unit: 'kg/ha' },
  { key: 'pH', label: 'Soil pH', min: 3.5, max: 10, step: 0.1, unit: '' },
  { key: 'avg_temp_c', label: 'Avg temperature', min: 5, max: 45, step: 0.1, unit: '°C' },
  { key: 'total_rainfall_mm', label: 'Total rainfall', min: 0, max: 4000, step: 10, unit: 'mm' },
  { key: 'avg_humidity_percent', label: 'Avg humidity', min: 10, max: 100, step: 0.5, unit: '%' },
  { key: 'fertilizer_per_ha', label: 'Fertilizer', min: 0, max: 1000, step: 1, unit: 'kg/ha' },
  { key: 'pesticide_per_ha', label: 'Pesticide', min: 0, max: 20, step: 0.01, unit: 'kg/ha' },
]

const BASE = {
  state: 'Punjab', year: 2020, crop: 'Wheat', season: 'Rabi', area: 2.5,
  N: 150, P: 50, K: 40, pH: 8.0, avg_temp_c: 23.3, total_rainfall_mm: 1138.97,
  avg_humidity_percent: 55.64, fertilizer_per_ha: 171.42, pesticide_per_ha: 0.37,
}

const SCENARIO_NAMES = ['Scenario A', 'Scenario B', 'Scenario C']
const SCENARIO_COLORS = [CHART_COLORS.green, CHART_COLORS.blue, CHART_COLORS.amber]

export default function Prediction({ options }) {
  const [scenarios, setScenarios] = useState([{ ...BASE }, { ...BASE, N: 90, P: 30, pH: 6.5 }])
  const [results, setResults] = useState([])
  const [busy, setBusy] = useState(true)   // the page runs its scenarios on arrival
  const [error, setError] = useState(null)
  const [active, setActive] = useState(0)

  const run = useCallback(async () => {
    try {
      const out = await Promise.all(scenarios.map(s =>
        fetch(`${API_BASE}/api/predict`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(s),
        }).then(r => {
          if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
          return r.json()
        })
      ))
      setResults(out)
    } catch (e) {
      setError(e.message)
    }
    setBusy(false)
  }, [scenarios])

  // Run once on mount so the page is never empty on arrival.
  // `run` awaits before writing any state, so no render cascades from this effect --
  // the rule cannot see past the await, hence the scoped disable rather than a
  // restructure. `busy` starts true so the button is disabled until this settles.
  // eslint-disable-next-line react-hooks/exhaustive-deps, react-hooks/set-state-in-effect
  useEffect(() => { run() }, [])

  function rerun() {
    setBusy(true)
    setError(null)
    run()
  }

  function update(i, key, value) {
    setScenarios(s => s.map((sc, j) => (j === i ? { ...sc, [key]: value } : sc)))
  }

  /** Selecting a state loads its real soil and climate: v3 has no `state` feature, so
   *  without this the control would change nothing at all. */
  function setState_(i, stateName) {
    const d = STATE_DEFAULTS[stateName]
    setScenarios(s => s.map((sc, j) =>
      j === i ? { ...sc, state: stateName, ...(d || {}) } : sc))
  }

  function addScenario() {
    if (scenarios.length >= 3) return
    setScenarios(s => [...s, { ...s[s.length - 1] }])
  }

  function removeScenario(i) {
    if (scenarios.length <= 1) return
    setScenarios(s => s.filter((_, j) => j !== i))
    setResults([])
    setActive(0)
  }

  const chartData = results.map((r, i) => ({
    name: SCENARIO_NAMES[i],
    yield: r.prediction,
    // ErrorBar takes [distance below, distance above], not absolute bounds
    err: [r.prediction - r.interval.low, r.interval.high - r.prediction],
    crop: scenarios[i]?.crop,
  }))

  const best = results.length > 1
    ? results.reduce((b, r, i) => (r.prediction > results[b].prediction ? i : b), 0)
    : null

  return (
    <Page>
      <PageHeader
        icon="🔮"
        title="Prediction Workspace"
        subtitle="Compare input scenarios side by side before committing to a plan"
        right={
          <button className="btn-predict" style={{ minWidth: 150 }} onClick={rerun} disabled={busy}>
            {busy ? 'Running…' : '✨ Run scenarios'}
          </button>
        }
      />

      {error && <ErrorState error={error} />}

      {/* ─── Results ────────────────────────────────────────────────── */}
      {results.length > 0 && (
        <>
          <div className="scenario-results fade-in">
            {results.map((r, i) => (
              <div key={i} className={`scenario-result${best === i && results.length > 1 ? ' is-best' : ''}`}
                   style={{ borderTopColor: SCENARIO_COLORS[i] }}>
                <div className="scenario-result-head">
                  <span className="scenario-dot" style={{ background: SCENARIO_COLORS[i] }} />
                  {SCENARIO_NAMES[i]}
                  {best === i && results.length > 1 && <span className="best-tag">Highest</span>}
                </div>
                <div className="scenario-value">{fmt(r.prediction)}</div>
                <div className="scenario-unit">{r.unit}</div>
                <div className="scenario-interval">
                  {fmt(r.interval.low)} – {fmt(r.interval.high)}
                  <div className="scenario-interval-label">{r.interval.level}</div>
                </div>
                <div className="scenario-meta">
                  {scenarios[i].crop} · {scenarios[i].state} · {scenarios[i].season}
                </div>
                <div className={`scenario-badge badge-${r.badge?.split(' ')[0]?.toLowerCase()}`}>
                  {r.badge}
                </div>
              </div>
            ))}
          </div>

          <div className="section-card fade-in">
            <div className="section-title">📊 Forecast comparison</div>
            <p className="section-lede">
              Bars show the point forecast; whiskers show the range the 200 trees spanned. Wide
              whiskers mean the ensemble disagreed — treat that forecast as less settled.
            </p>
            <div style={{ width: '100%', height: 280 }}>
              <ResponsiveContainer>
                <BarChart data={chartData} margin={{ top: 20, right: 20, left: 0, bottom: 4 }}>
                  <CartesianGrid {...gridProps} />
                  <XAxis dataKey="name" {...axisProps} />
                  <YAxis {...axisProps}
                         label={{ value: 'Yield (t/ha)', angle: -90, position: 'insideLeft', style: { fontSize: 11, fill: '#485c4e' } }} />
                  <Tooltip {...tooltipStyle} formatter={v => [`${fmt(v)} t/ha`, 'Forecast']} />
                  <RBar dataKey="yield" radius={[8, 8, 0, 0]} maxBarSize={90}>
                    {chartData.map((_, i) => <Cell key={i} fill={SCENARIO_COLORS[i]} />)}
                    <ErrorBar dataKey="err" width={6} strokeWidth={2} stroke="#2a3d30" />
                  </RBar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            {results.length > 1 && (
              <Note tone="info" title="Reading the difference">
                {(() => {
                  const lo = results.reduce((b, r, i) => (r.prediction < results[b].prediction ? i : b), 0)
                  const diff = results[best].prediction - results[lo].prediction
                  const pct = results[lo].prediction > 0 ? (diff / results[lo].prediction) * 100 : 0
                  const overlap = results[best].interval.low < results[lo].interval.high
                  return overlap ? (
                    <>{SCENARIO_NAMES[best]} forecasts {fmt(diff)} t/ha more than {SCENARIO_NAMES[lo]}{' '}
                    ({fmt(pct, 0)}%), but their intervals overlap — the model does not clearly
                    separate these two scenarios, so the gap should not drive the decision on its own.</>
                  ) : (
                    <>{SCENARIO_NAMES[best]} forecasts {fmt(diff)} t/ha more than {SCENARIO_NAMES[lo]}{' '}
                    ({fmt(pct, 0)}%), and their intervals do not overlap — the model separates these
                    scenarios cleanly.</>
                  )
                })()}
              </Note>
            )}
          </div>

          {results[active]?.recommendations?.length > 0 && (
            <div className="section-card fade-in">
              <div className="section-title">
                💡 Agronomic notes
                {results.length > 1 && (
                  <div className="seg-control">
                    {results.map((_, i) => (
                      <button key={i} className={active === i ? 'active' : ''} onClick={() => setActive(i)}>
                        {SCENARIO_NAMES[i].replace('Scenario ', '')}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <div className="recs-grid">
                {results[active].recommendations.map((rec, i) => (
                  <div key={i} className="rec-item">
                    <div className={`rec-icon rec-${rec.type}`}>
                      {rec.type === 'ok' ? '✓' : rec.type === 'warn' ? '!' : 'i'}
                    </div>
                    <div>
                      <div className="rec-title">{rec.title}</div>
                      <div className="rec-desc">{rec.desc}</div>
                    </div>
                  </div>
                ))}
              </div>
              <Note tone="info">
                These notes come from agronomic threshold rules (rainfall bands, pH ranges, N:P
                ratios), not from the model. They explain the conditions; the forecast above is the
                model's output.
              </Note>
            </div>
          )}
        </>
      )}

      {busy && results.length === 0 && <Loading label="Running scenarios…" />}

      {/* ─── Inputs ─────────────────────────────────────────────────── */}
      <div className="section-card fade-in">
        <div className="section-title">
          🎛️ Scenario inputs
          {scenarios.length < 3 && (
            <button className="btn-refresh" style={{ marginLeft: 'auto' }} onClick={addScenario}>
              + Add scenario
            </button>
          )}
        </div>

        <div className="scenario-cols">
          {scenarios.map((sc, i) => (
            <div key={i} className="scenario-col" style={{ borderTopColor: SCENARIO_COLORS[i] }}>
              <div className="scenario-col-head">
                <span className="scenario-dot" style={{ background: SCENARIO_COLORS[i] }} />
                {SCENARIO_NAMES[i]}
                {scenarios.length > 1 && (
                  <button className="scenario-remove" onClick={() => removeScenario(i)}
                          title="Remove scenario">✕</button>
                )}
              </div>

              <div className="form-field">
                <label>State</label>
                <select value={sc.state} onChange={e => setState_(i, e.target.value)}>
                  {options?.states?.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div className="form-field">
                <label>Crop</label>
                <select value={sc.crop} onChange={e => update(i, 'crop', e.target.value)}>
                  {options?.crops?.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div className="form-field">
                <label>Season</label>
                <select value={sc.season} onChange={e => update(i, 'season', e.target.value)}>
                  {options?.seasons?.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div className="form-field">
                <label>Year</label>
                <select value={sc.year} onChange={e => update(i, 'year', Number(e.target.value))}>
                  {options && Array.from(
                    { length: (options.year_max + 5) - options.year_min + 1 },
                    (_, k) => options.year_min + k
                  ).map(y => <option key={y} value={y}>{y}</option>)}
                </select>
              </div>

              {FIELDS.map(f => (
                <div key={f.key} className="slider-field">
                  <div className="slider-head">
                    <span>{f.label}</span>
                    <span className="slider-value">{fmt(sc[f.key], f.step < 1 ? 1 : 0)} {f.unit}</span>
                  </div>
                  <input
                    type="range" min={f.min} max={f.max} step={f.step} value={sc[f.key]}
                    onChange={e => update(i, f.key, Number(e.target.value))}
                    style={{ accentColor: SCENARIO_COLORS[i] }}
                  />
                </div>
              ))}
            </div>
          ))}
        </div>

        <Note tone="info" title="Selecting a state loads its soil and climate">
          The model does not take state as a feature — it infers region from soil and climate
          instead. Picking a state therefore fills in that state's recorded values, which you can
          then adjust to describe a field that differs from its regional baseline.
        </Note>
      </div>
    </Page>
  )
}


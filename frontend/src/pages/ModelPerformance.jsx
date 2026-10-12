import { useState } from 'react'
import {
  BarChart, Bar as RBar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ScatterChart, Scatter, ZAxis, ReferenceLine, Cell, LabelList,
} from 'recharts'
import { Bar, ErrorState, KpiCard, Loading, Note, PageHeader, Page, Spec } from './shared'
import { useApi, CHART_COLORS, axisProps, gridProps, tooltipStyle, fmt } from './api'

/**
 * The evaluation report. It leads with skill against naive baselines -- whether the model
 * beats repeating what already happened -- because R² on its own cannot show that. A
 * reader who finds a flattering number without its baseline stops trusting the rest.
 */
const signed = n => `${n > 0 ? '+' : ''}${fmt(n, 1)}%`
const skillColor = n => (n > 0 ? 'var(--green-600)' : 'var(--red)')

export default function ModelPerformance() {
  const { data: m, error, loading } = useApi('/api/model-metrics')
  const { data: research } = useApi('/api/research')
  const [cropSort, setCropSort] = useState('worst')

  if (loading) return <Page><Loading label="Loading evaluation results…" /></Page>
  if (error) return <Page><ErrorState error={error} /></Page>
  if (!m) return null

  const dq = m.data_quality
  const sens = m.sensitivity || {}
  const sensV2 = m.sensitivity_v2 || {}

  const sk = m.skill
  const best = m.baselines[sk.best_baseline]
  const beats = sk.vs_best_baseline_pct > 0
  const lso = m.leave_states_out
  const inputAblation = m.ablation || []
  const historyOnly = inputAblation.find(a => a.variant.startsWith('History only'))
  const shipped = inputAblation.find(a => a.variant.includes('shipped'))
  const weatherGain = historyOnly && shipped ? historyOnly.mae - shipped.mae : null
  const thinYears = (m.rolling_origin || []).filter(r => r.n < 100)

  // every predictor on the same rows, best first
  const comparisonRows = [
    ...Object.entries(m.baselines).map(([key, b]) => ({ key, name: b.label, mae: b.mae, r2: b.r2, skill: sk.vs_baseline_pct[key] })),
    { key: 'model', name: `This model (${m.version})`, mae: m.headline.mae, r2: m.headline.r2, skill: null, isModel: true },
  ].sort((a, b) => a.mae - b.mae)

  const sensRows = Object.keys(sens).map(k => ({
    key: k,
    label: LABELS[k] || k,
    sweep: `${sens[k].from}–${sens[k].to} ${sens[k].unit}`,
    v3: sens[k].median_pct_change,
    v2: sensV2[k]?.median_pct_change ?? null,
  })).sort((a, b) => b.v3 - a.v3)

  const crops = [...(m.per_crop || [])]
  const shownCrops = (cropSort === 'worst' ? crops : [...crops].reverse()).slice(0, 12)

  const importance = (m.feature_importance || []).slice(0, 14)
  const comparison = research?.model_comparison || []
  const ablation = research?.ablation || []

  return (
    <Page>
      <PageHeader
        icon="📈"
        title="Model Performance"
        subtitle={`${m.model} · ${m.version} · ${m.evaluated_on}`}
      />

      {/* ─── Headline: skill against the strongest naive baseline ───── */}
      <div className="kpi-row fade-in">
        <KpiCard
          icon="🎯" iconBg={beats ? 'var(--green-100)' : 'var(--amber-bg)'}
          label="SKILL VS NAIVE BASELINE" value={signed(sk.vs_best_baseline_pct)}
          sub={`MAE ${fmt(m.headline.mae, 3)} vs ${fmt(best.mae, 3)} t/ha`}
          title="1 − model MAE ÷ baseline MAE, against the strongest baseline. Positive means the model beats simply repeating history; negative means repeating history is better."
        />
        <KpiCard
          icon="🗺️" iconBg="var(--purple-bg)"
          label="SKILL ON UNSEEN STATES" value={signed(lso.skill.vs_best_baseline_pct)}
          sub={`MAE ${fmt(lso.model.mae, 3)} · whole states held out`}
          title="Whole states are withheld from training, so this is how the model does in a region it has never seen."
        />
        <KpiCard
          icon="📏" iconBg="var(--blue-bg)"
          label="MEAN ABSOLUTE ERROR" value={`${fmt(m.core_staples.mae, 3)}`}
          sub={`t/ha on core staples · ${fmt(m.headline.mae, 3)} on all crops`}
        />
        <KpiCard
          icon="🌾" iconBg="var(--amber-bg)"
          label="R² — CORE STAPLES" value={fmt(m.core_staples.r2, 4)}
          sub={`last-season baseline ${fmt(m.core_staples_baselines.persistence.r2, 4)} · n=${m.core_staples.n}`}
          title="Quoted beside the baseline's R²: on its own R² cannot show the model adds anything."
        />
      </div>

      {/* ─── The verdict, against baselines ─────────────────────────── */}
      <div className="section-card fade-in">
        <div className="section-title">⚖️ Does the model beat simply repeating history?</div>
        <p className="section-lede">
          Every predictor below is scored on the same {m.headline.n.toLocaleString('en-IN')} held-out
          forecasts. A baseline needs no model: it is an average, or last season's recorded yield
          carried forward. Skill is how much the model's error is lower than the baseline's.
        </p>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Predictor</th><th className="num">MAE (t/ha)</th><th className="num">R²</th>
                <th className="num">Model skill vs it</th><th style={{ width: '26%' }} />
              </tr>
            </thead>
            <tbody>
              {comparisonRows.map(r => (
                <tr key={r.key} className={r.isModel ? 'row-highlight' : ''}>
                  <td><strong>{r.name}</strong></td>
                  <td className="num"><strong>{fmt(r.mae, 3)}</strong></td>
                  <td className="num muted">{fmt(r.r2, 4)}</td>
                  <td className="num" style={r.skill == null ? undefined : { color: skillColor(r.skill) }}>
                    {r.skill == null ? '—' : signed(r.skill)}
                  </td>
                  <td>
                    <Bar value={r.mae} max={Math.max(...comparisonRows.map(x => x.mae))}
                         color={r.isModel ? CHART_COLORS.green : '#cddbd2'} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Note tone={beats ? 'info' : 'warn'}
              title={beats ? 'The model beats every baseline'
                : `The model does not yet beat "${best.label.toLowerCase()}"`}>
          The model's error is {fmt(m.headline.mae, 3)} t/ha against {fmt(best.mae, 3)} t/ha for the
          strongest baseline, a skill of <strong>{signed(sk.vs_best_baseline_pct)}</strong>. Against
          the state × crop × season average the skill is {signed(sk.vs_baseline_pct.series_mean)}, so
          the history features are doing the work.{' '}
          {weatherGain !== null && (
            <>Adding weather and soil on top of history {weatherGain > 0 ? 'lowers' : 'raises'} MAE
            by {fmt(Math.abs(weatherGain), 3)} t/ha (table below). </>
          )}
          Soil here is one constant per state and weather one value per state-year, so more inputs
          of this kind are unlikely to close the gap; finer-grained data is the lever.
        </Note>
      </div>

      {/* ─── Is the verdict stable? ─────────────────────────────────── */}
      <div className="section-card fade-in">
        <div className="section-title">🔁 Is that verdict stable?</div>
        <p className="section-lede">
          The headline is one split. Two harder checks: forecast one test year at a time, each
          trained only on the years before it, and hold out whole states.
        </p>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Test year</th><th className="num">n</th><th className="num">Model MAE</th>
                <th className="num">Last season</th><th className="num">3-yr mean</th>
                <th className="num">Skill vs last season</th>
              </tr>
            </thead>
            <tbody>
              {m.rolling_origin.map(r => (
                <tr key={r.year} className={r.n < 100 ? 'muted' : ''}>
                  <td><strong>{r.year}</strong></td>
                  <td className="num muted">{r.n}</td>
                  <td className="num"><strong>{fmt(r.model_mae, 3)}</strong></td>
                  <td className="num">{fmt(r.persistence_mae, 3)}</td>
                  <td className="num">{fmt(r.mean_3yr_mae, 3)}</td>
                  <td className="num" style={{ color: skillColor(r.skill_vs_persistence_pct) }}>
                    {signed(r.skill_vs_persistence_pct)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {thinYears.length > 0 && (
          <Note tone="info" title="Years with few records are noise">
            The dataset holds only {thinYears.map(r => `${r.n} records for ${r.year}`).join(' and ')}, so{' '}
            {thinYears.length > 1 ? 'those rows say' : 'that row says'} little. Judge the verdict by the
            years with a full set of records.
          </Note>
        )}

        <div className="table-scroll" style={{ marginTop: '1.2rem' }}>
          <table className="data-table">
            <thead>
              <tr><th>Unseen states ({lso.folds}-fold, whole states held out)</th>
                  <th className="num">MAE (t/ha)</th><th className="num">R²</th></tr>
            </thead>
            <tbody>
              <tr className="row-highlight">
                <td><strong>This model, with the state's own history</strong></td>
                <td className="num"><strong>{fmt(lso.model.mae, 3)}</strong></td>
                <td className="num muted">{fmt(lso.model.r2, 4)}</td>
              </tr>
              {Object.entries(lso.baselines).map(([k, b]) => (
                <tr key={k}>
                  <td>{b.label}</td>
                  <td className="num">{fmt(b.mae, 3)}</td>
                  <td className="num muted">{fmt(b.r2, 4)}</td>
                </tr>
              ))}
              <tr>
                <td>This model with <em>no</em> history (a region with no records)</td>
                <td className="num">{fmt(lso.no_history.mae, 3)}</td>
                <td className="num muted">{fmt(lso.no_history.r2, 4)}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <Note tone="info" title="What an unseen region gets from agronomic inputs alone">
          With no yield history, soil, weather and farm inputs beat a crop average by only{' '}
          <strong>{fmt(lso.no_history.vs_crop_mean_pct, 0)}%</strong> ({fmt(lso.no_history.mae, 2)} vs{' '}
          {fmt(lso.baselines.crop_mean.mae, 2)} t/ha). Knowing a series' own past is worth far more
          than knowing its soil.
        </Note>
      </div>

      {/* ─── What the inputs add ────────────────────────────────────── */}
      {inputAblation.length > 0 && (
        <div className="section-card fade-in">
          <div className="section-title">🧬 What each input group adds</div>
          <p className="section-lede">Same holdout, same model family, input groups added one at a time.</p>
          <div className="table-scroll">
            <table className="data-table">
              <thead><tr><th>Inputs</th><th className="num">MAE (t/ha)</th><th className="num">R²</th></tr></thead>
              <tbody>
                {inputAblation.map(a => (
                  <tr key={a.variant} className={a.variant.includes('shipped') ? 'row-highlight' : ''}>
                    <td><strong>{a.variant}</strong></td>
                    <td className="num"><strong>{fmt(a.mae, 3)}</strong></td>
                    <td className="num muted">{fmt(a.r2, 4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ─── Why there are two numbers ──────────────────────────────── */}
      <div className="section-card fade-in">
        <div className="section-title">🔍 Why this page reports two accuracy figures</div>
        <Note tone="warn" title="The headline R² is inflated by crop scale, not by skill">
          Yield magnitudes in this dataset differ by more than an order of magnitude — Sugarcane
          averages ~51 t/ha where staples sit near 2.8 t/ha. A model that merely separates
          high-magnitude crops from low-magnitude ones therefore earns a high R² without doing
          much agronomy. Removing {m.core_staples.excludes.join(' and ')} drops R² from{' '}
          <strong>{fmt(m.headline.r2, 4)}</strong> to <strong>{fmt(m.core_staples.r2, 4)}</strong>{' '}
          on the same holdout. The lower number is the one that describes performance on the
          crops most users will actually forecast, so it is the one we quote.
        </Note>

        <Note tone="danger" title={`Excluded from the model: ${dq.excluded_crops.join(', ')}`}>
          {dq.exclusion_reason} The dataset also winsorises yield at{' '}
          <strong>{dq.clip_value}</strong>, pinning <strong>{dq.clipped_rows}</strong> rows to a
          single value:
          <div className="chip-row">
            {Object.entries(dq.clipped_by_crop || {}).map(([c, n]) => (
              <span key={c} className="chip">{c} <b>{n}</b></span>
            ))}
          </div>
        </Note>
      </div>

      {/* ─── Input sensitivity: the thing accuracy cannot show ──────── */}
      <div className="section-card fade-in">
        <div className="section-title">🎚️ Input sensitivity — how far do field inputs move the forecast?</div>
        <p className="section-lede">
          How far the forecast moves when each field input is swept across its realistic range —
          median over {sens[Object.keys(sens)[0]]?.n_rows ?? 200} held-out rows, with every
          derived feature rebuilt from the perturbed value. A small number is not a bug: see the
          note below.
        </p>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Input</th><th>Swept across</th>
                <th className="num">v2</th><th className="num">{m.version} (current)</th>
                <th style={{ width: '30%' }}>Response</th>
              </tr>
            </thead>
            <tbody>
              {sensRows.map(r => (
                <tr key={r.key}>
                  <td><strong>{r.label}</strong></td>
                  <td className="muted">{r.sweep}</td>
                  <td className="num muted">{r.v2 === null ? '—' : `${fmt(r.v2, 2)}%`}</td>
                  <td className="num"><strong>{fmt(r.v3, 2)}%</strong></td>
                  <td>
                    <Bar value={r.v3} max={Math.max(...sensRows.map(x => x.v3))}
                         color={r.v3 < 5 ? CHART_COLORS.amber : CHART_COLORS.green} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Note tone="warn" title="Why the inputs barely register now">
          The forecast is last season's recorded yield plus a learned correction, and{' '}
          <code>state</code> is a feature again. Soil N, P, K and pH are one constant per state, so
          a model that responds strongly to them (v2 moved {fmt(sensV2.P?.median_pct_change, 0)}% across
          the phosphorus sweep) can only be recognising which state a row resembles, because soil
          never varies within a state in the training data.
          Once the state and its history are known, those inputs carry no extra signal, which is
          what the table above shows. The what-if sliders therefore describe a region, not a
          lever. Making them meaningful needs district- or field-level data.
        </Note>
      </div>

      {/* ─── Model selection evidence ───────────────────────────────── */}
      {comparison.length > 0 && (
        <div className="section-card fade-in">
          <div className="section-title">🏁 Why Extra Trees</div>
          <p className="section-lede">
            Candidate algorithms on identical splits. Extra Trees won on both cross-validated and
            held-out error, with the tightest CV spread.
          </p>
          <div style={{ width: '100%', height: 300 }}>
            <ResponsiveContainer>
              <BarChart data={comparison} margin={{ top: 10, right: 20, left: 0, bottom: 5 }}>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="Model" {...axisProps} interval={0} angle={-12} textAnchor="end" height={60} />
                <YAxis {...axisProps} label={{ value: 'MAE (t/ha)', angle: -90, position: 'insideLeft', style: { fontSize: 11, fill: '#485c4e' } }} />
                <Tooltip {...tooltipStyle} formatter={(v, n) => [fmt(v, 3), n]} />
                <RBar dataKey="Test_MAE" name="Test MAE" radius={[6, 6, 0, 0]}>
                  {comparison.map((row, i) => (
                    <Cell key={i} fill={row.Model === 'Extra Trees' ? CHART_COLORS.green : '#cddbd2'} />
                  ))}
                  <LabelList dataKey="Test_MAE" position="top" formatter={v => fmt(v, 2)}
                             style={{ fontSize: 10, fill: '#485c4e' }} />
                </RBar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="table-scroll" style={{ marginTop: '1rem' }}>
            <table className="data-table">
              <thead>
                <tr><th>Model</th><th className="num">CV MAE</th><th className="num">CV std</th>
                    <th className="num">Test MAE</th><th className="num">Test RMSE</th><th className="num">Test R²</th></tr>
              </thead>
              <tbody>
                {comparison.map(r => (
                  <tr key={r.Model} className={r.Model === 'Extra Trees' ? 'row-highlight' : ''}>
                    <td><strong>{r.Model}</strong></td>
                    <td className="num">{fmt(r.CV_MAE, 3)}</td>
                    <td className="num muted">{fmt(r.CV_Std, 3)}</td>
                    <td className="num">{fmt(r.Test_MAE, 3)}</td>
                    <td className="num">{fmt(r.Test_RMSE, 3)}</td>
                    <td className="num">{fmt(r.Test_R2, 4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Note tone="info">
            These figures come from the original study, which included Coconut and used{' '}
            <code>state</code>. They justify the algorithm choice; the numbers at the top of
            this page describe the model actually being served.
          </Note>
        </div>
      )}

      {/* ─── Ablation ───────────────────────────────────────────────── */}
      {ablation.length > 0 && (
        <div className="section-card fade-in">
          <div className="section-title">🧬 Feature ablation — which engineered groups earned their place</div>
          <div style={{ width: '100%', height: 280 }}>
            <ResponsiveContainer>
              <BarChart data={ablation} margin={{ top: 16, right: 20, left: 0, bottom: 5 }}>
                <CartesianGrid {...gridProps} />
                <XAxis dataKey="Configuration" {...axisProps} interval={0} angle={-12} textAnchor="end" height={70} />
                <YAxis {...axisProps} domain={['auto', 'auto']}
                       label={{ value: 'MAE (t/ha)', angle: -90, position: 'insideLeft', style: { fontSize: 11, fill: '#485c4e' } }} />
                <Tooltip {...tooltipStyle} formatter={(v, n) => [fmt(v, 4), n]} />
                <RBar dataKey="MAE" name="MAE" radius={[6, 6, 0, 0]}>
                  {ablation.map((row, i) => (
                    <Cell key={i} fill={row['Δ_MAE_from_Baseline_%'] > 1 ? CHART_COLORS.green : '#cddbd2'} />
                  ))}
                </RBar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <Note tone="info" title="Reading this honestly">
            Only the input-efficiency group produced a material gain (~8.4% MAE reduction). The NPK
            ratio, climate and soil-quality groups moved MAE by well under 1% — within noise. They
            are retained because they cost nothing at inference, not because the ablation proved
            them necessary.
          </Note>
        </div>
      )}

      {/* ─── Feature importance ─────────────────────────────────────── */}
      <div className="section-card fade-in">
        <div className="section-title">⚖️ What drives a prediction</div>
        <p className="section-lede">
          Impurity-based importance, with one-hot columns summed back into their source feature —
          otherwise <code>crop</code> appears as {'>'}50 individually weak columns instead of one
          dominant signal. It describes the learned <em>change from last season's yield</em>, not
          the yield level.
        </p>
        <div style={{ width: '100%', height: Math.max(260, importance.length * 26) }}>
          <ResponsiveContainer>
            <BarChart data={importance} layout="vertical" margin={{ top: 4, right: 40, left: 8, bottom: 4 }}>
              <CartesianGrid {...gridProps} horizontal={false} />
              <XAxis type="number" {...axisProps} />
              <YAxis type="category" dataKey="feature" width={165} {...axisProps} />
              <Tooltip {...tooltipStyle} formatter={v => [fmt(v * 100, 2) + '%', 'importance']} />
              <RBar dataKey="importance" radius={[0, 5, 5, 0]} fill={CHART_COLORS.green} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ─── Per-crop error ─────────────────────────────────────────── */}
      <div className="section-card fade-in">
        <div className="section-title">
          🌱 Where the model works, and where it does not
          <div className="seg-control">
            <button className={cropSort === 'worst' ? 'active' : ''} onClick={() => setCropSort('worst')}>Highest error</button>
            <button className={cropSort === 'best' ? 'active' : ''} onClick={() => setCropSort('best')}>Lowest error</button>
          </div>
        </div>
        <p className="section-lede">
          Absolute error per crop on the holdout. Error tracks magnitude — high-yield crops carry
          larger absolute error while often being proportionally as accurate — so mean actual yield
          is shown alongside.
        </p>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr><th>Crop</th><th className="num">n</th><th className="num">MAE</th>
                  <th className="num">Last season MAE</th><th className="num">Skill</th>
                  <th className="num">Mean actual</th><th className="num">Error / mean</th>
                  <th style={{ width: '22%' }} /></tr>
            </thead>
            <tbody>
              {shownCrops.map(c => {
                const rel = c.mean_actual > 0 ? (c.mae / c.mean_actual) * 100 : 0
                const cropSkill = c.baseline_mae > 0 ? (1 - c.mae / c.baseline_mae) * 100 : 0
                return (
                  <tr key={c.crop}>
                    <td><strong>{c.crop}</strong></td>
                    <td className="num muted">{c.n}</td>
                    <td className="num"><strong>{fmt(c.mae, 3)}</strong></td>
                    <td className="num muted">{fmt(c.baseline_mae, 3)}</td>
                    <td className="num" style={{ color: skillColor(cropSkill) }}>{signed(cropSkill)}</td>
                    <td className="num muted">{fmt(c.mean_actual, 2)}</td>
                    <td className="num" style={{ color: rel > 50 ? 'var(--red)' : rel > 25 ? 'var(--amber)' : 'var(--green-600)' }}>
                      {fmt(rel, 0)}%
                    </td>
                    <td>
                      <Bar value={rel} max={100}
                           color={rel > 50 ? CHART_COLORS.red : rel > 25 ? CHART_COLORS.amber : CHART_COLORS.green} />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* ─── Predicted vs actual ────────────────────────────────────── */}
      {m.scatter?.length > 0 && (
        <div className="section-card fade-in">
          <div className="section-title">🎯 Predicted vs actual</div>
          <p className="section-lede">
            {m.scatter.length} held-out predictions. Points on the dashed line are exact; vertical
            spread away from it is model error.
          </p>
          <div style={{ width: '100%', height: 360 }}>
            <ResponsiveContainer>
              <ScatterChart margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
                <CartesianGrid {...gridProps} vertical />
                <XAxis type="number" dataKey="a" name="Actual" {...axisProps}
                       label={{ value: 'Actual yield (t/ha)', position: 'insideBottom', offset: -4, style: { fontSize: 11, fill: '#485c4e' } }} />
                <YAxis type="number" dataKey="p" name="Predicted" {...axisProps}
                       label={{ value: 'Predicted (t/ha)', angle: -90, position: 'insideLeft', style: { fontSize: 11, fill: '#485c4e' } }} />
                <ZAxis range={[14, 14]} />
                <Tooltip {...tooltipStyle} cursor={{ strokeDasharray: '3 3' }}
                         formatter={(v, n) => [fmt(v), n]} />
                <ReferenceLine segment={[{ x: 0, y: 0 }, { x: 110, y: 110 }]}
                               stroke="#9e1a1a" strokeDasharray="6 4" />
                <Scatter data={m.scatter} fill="rgba(31,122,61,0.45)" />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* ─── Limits ─────────────────────────────────────────────────── */}
      <div className="section-card fade-in">
        <div className="section-title">🧭 Known limits</div>
        <Note tone="warn" title="Why more of the same inputs will not help">
          {dq.known_ceiling}
        </Note>
        <Note tone="info" title="Two columns in the source data contain the answer">
          <code>yield_ma2</code> and <code>yield_change</code> include the current season's yield
          ({fmt(dq.leakage.yield_ma2_contains_target_pct, 1)}% of rows), so a model trained on them
          looks accurate while forecasting nothing. They are not used. Every history feature is
          recomputed from strictly earlier seasons, and <code>test_model.py</code> checks that
          poisoning all later yields leaves the features unchanged.
        </Note>
        <Note tone="info" title="What a forecast needs">
          {m.forecast_design.requires} {m.forecast_design.anchor}{' '}
          {m.forecast_design.unscored_test_rows} holdout rows without such a season could not be
          forecast and are not scored.
        </Note>
        <div className="spec-grid">
          <Spec label="Algorithm" value={m.model} />
          <Spec label="Trees" value={m.hyperparameters.n_estimators} />
          <Spec label="Max depth" value={m.hyperparameters.max_depth} />
          <Spec label="Features"
                value={`${m.features.total} (${m.features.numeric} numeric, ${m.features.history.length} history)`} />
          <Spec label="Rows used" value={`${dq.rows_used.toLocaleString('en-IN')} of ${dq.rows_total.toLocaleString('en-IN')}`} />
          <Spec label="Added in v3.1" value={m.features.added_vs_v3.join(', ')} wide />
          <Spec label="Evaluation" value={m.evaluated_on} wide />
          <Spec label="Shipped artifact" value={m.note} wide />
        </div>
      </div>
    </Page>
  )
}

const LABELS = {
  total_rainfall_mm: 'Rainfall',
  N: 'Nitrogen (N)',
  P: 'Phosphorus (P)',
  K: 'Potassium (K)',
  pH: 'Soil pH',
  avg_temp_c: 'Temperature',
}



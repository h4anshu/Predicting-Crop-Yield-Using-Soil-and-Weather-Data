import { useState } from 'react'
import {
  BarChart, Bar as RBar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  ScatterChart, Scatter, ZAxis, ReferenceLine, Cell, LabelList,
} from 'recharts'
import { Bar, ErrorState, KpiCard, Loading, Note, PageHeader, Page, Spec } from './shared'
import { useApi, CHART_COLORS, axisProps, gridProps, tooltipStyle, fmt } from './api'

/**
 * The evaluation report. Deliberately leads with the weaker, more defensible number
 * rather than the flattering one: a reader who finds the Coconut artifact themselves
 * stops trusting everything else on the page.
 */
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
        subtitle={`${m.model} · ${m.version} · evaluated on a ${m.evaluated_on.includes('2018') ? '2018–2020' : ''} temporal holdout`}
      />

      {/* ─── Headline numbers, both of them ─────────────────────────── */}
      <div className="kpi-row fade-in">
        <KpiCard
          icon="🎯" iconBg="var(--green-100)"
          label="R² — ALL CROPS" value={fmt(m.headline.r2, 4)}
          sub={`MAE ${fmt(m.headline.mae)} t/ha · n=${m.headline.n}`}
        />
        <KpiCard
          icon="🌾" iconBg="var(--amber-bg)"
          label="R² — CORE STAPLES" value={fmt(m.core_staples.r2, 4)}
          sub={`excl. ${m.core_staples.excludes.join(', ')} · n=${m.core_staples.n}`}
          title="The conservative number. Sugarcane's large magnitude inflates the headline R²."
        />
        <KpiCard
          icon="📏" iconBg="var(--blue-bg)"
          label="MEAN ABSOLUTE ERROR" value={`${fmt(m.core_staples.mae)}`}
          sub="t/ha on core staples"
        />
        <KpiCard
          icon="🔁" iconBg="var(--purple-bg)"
          label={`${m.cv.folds}-FOLD CV MAE`} value={fmt(m.cv.mae_mean, 3)}
          sub={`± ${fmt(m.cv.mae_std, 3)} across folds`}
          title="Low spread across folds indicates the score is not an artifact of one lucky split."
        />
      </div>

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
        <div className="section-title">🎚️ Input sensitivity — does the model actually respond?</div>
        <p className="section-lede">
          A model can score well while ignoring the inputs a user can change. This measures how
          far the forecast moves when each field input is swept across its realistic range —
          median over {sens[Object.keys(sens)[0]]?.n_rows ?? 200} held-out rows, with every
          derived feature rebuilt from the perturbed value.
        </p>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Input</th><th>Swept across</th>
                <th className="num">v2 (previous)</th><th className="num">v3 (current)</th>
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
        <Note tone="info" title="What changed between v2 and v3">
          v2 used <code>state</code> as a feature. Because soil and weather are state-level
          constants here, <code>state</code> was a cleaner split than any agronomic column, so the
          trees leaned on it and pH response fell to {fmt(sensV2.pH?.median_pct_change ?? 1.13, 2)}%
          — effectively inert. Dropping <code>state</code> forces the model to locate a field from
          its soil and climate instead, raising pH response to {fmt(sens.pH?.median_pct_change, 2)}%.
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
            <code>state</code>. They justify the algorithm choice; the v3 numbers at the top of
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
          dominant signal.
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
                  <th className="num">Mean actual</th><th className="num">Error / mean</th>
                  <th style={{ width: '26%' }} /></tr>
            </thead>
            <tbody>
              {shownCrops.map(c => {
                const rel = c.mean_actual > 0 ? (c.mae / c.mean_actual) * 100 : 0
                return (
                  <tr key={c.crop}>
                    <td><strong>{c.crop}</strong></td>
                    <td className="num muted">{c.n}</td>
                    <td className="num"><strong>{fmt(c.mae, 3)}</strong></td>
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
        <Note tone="warn" title="Response is regional, not field-level">
          {dq.known_ceiling}
        </Note>
        <div className="spec-grid">
          <Spec label="Algorithm" value={m.model} />
          <Spec label="Trees" value={m.hyperparameters.n_estimators} />
          <Spec label="Max depth" value={m.hyperparameters.max_depth} />
          <Spec label="Features" value={`${m.features.total} (${m.features.numeric} numeric)`} />
          <Spec label="Dropped vs v2" value={m.features.dropped_vs_v2.join(', ') || '—'} />
          <Spec label="Rows used" value={`${dq.rows_used.toLocaleString('en-IN')} of ${dq.rows_total.toLocaleString('en-IN')}`} />
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



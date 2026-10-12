import { useState } from 'react'
import { ErrorState, KpiCard, Loading, Note, Page, PageHeader, Spec } from './shared'
import { useApi, fmt } from './api'

/**
 * The evidence page. Every pass/fail bar below was written down before the results were seen, and the page reports the
 * outcome as it came out, including the steps that failed and the one test that had to be corrected, because an account that
 * only shows its good side cannot be judged. Skill is always against simple baselines, per crop, never pooled across crops.
 */
const signed = v => (v == null ? '—' : `${v > 0 ? '+' : ''}${fmt(v, 1)}%`)
const pct = v => (v == null ? '—' : `${fmt(100 * v, 1)}%`)

function Pill({ ok }) {
  return (
    <span style={{
      padding: '0.12rem 0.55rem', borderRadius: 999, fontSize: '0.72rem', fontWeight: 700, letterSpacing: '0.04em',
      color: ok ? 'var(--green-700)' : 'var(--red)', background: ok ? 'var(--green-100)' : 'var(--red-bg)',
    }}>{ok ? 'PASS' : 'FAIL'}</span>
  )
}

export default function ModelPerformance() {
  const { data: m, error, loading } = useApi('/api/model')
  const [sort, setSort] = useState('model')

  if (loading) return <Page><Loading label="Loading the evaluation…" /></Page>
  if (error) return <Page><ErrorState error={error} /></Page>
  if (!m) return null

  const h = m.headline
  const c = m.criteria
  const K = 'Kharif Rice + Maize', W = 'Wheat (Rabi)'
  const first = c.M1.first_protocol.groups, lag = c.M1.lag_consistent.groups
  const rows = Object.entries(m.crops).map(([crop, v]) => ({ crop, ...v }))
    .sort((a, b) => sort === 'model' ? b.model.dev.skill_vs_mean3_pct - a.model.dev.skill_vs_mean3_pct
      : sort === 'mean' ? b.mean3.mean3_vs_last_published_pct - a.mean3.mean3_vs_last_published_pct : a.crop.localeCompare(b.crop))
  const years = c.M2.gain_by_year_pct

  return (
    <Page>
      <PageHeader icon="📈" title="Model & Evidence" subtitle="What the expected yield is, what was tested against it, and where nothing helped" />

      <div className="kpi-row fade-in">
        <KpiCard icon="🗺️" iconBg="var(--green-100)" label="CROPS WITH AN OUTLOOK" value={h.crops_offered}
                 sub={`${h.series.toLocaleString('en-IN')} series in ${h.districts} districts`} />
        <KpiCard icon="🧪" iconBg="var(--amber-bg)" label="MODEL BEAT THE MEAN" value={`${h.model_crops_beating_mean} of ${h.model_crops_tested}`}
                 sub="crops where a model cleared the bar set in advance" />
        <KpiCard icon="📅" iconBg="var(--blue-bg)" label="MEAN BEAT LAST SEASON" value={`${h.mean_beats_last_published_crops} of ${h.crops_offered}`}
                 sub="crops where the 3-season mean had lower error than the last published season" />
        <KpiCard icon="📏" iconBg="var(--purple-bg)" label="80% RANGE HELD" value={pct(h.range_coverage.dev_2018_2023)}
                 sub={`on 2018–23 · ${pct(h.range_coverage.confirm_2024)} on 2024`} />
      </div>

      <div className="section-card fade-in">
        <div className="section-title">⚙️ What is shown</div>
        <div className="spec-grid">
          <Spec label="Expected yield" value="the mean of the last three published seasons of the series" wide />
          <Spec label="Range" value="80%, conformal, calibrated per crop and separately for volatile and stable series" wide />
          <Spec label="Publication lag" value={`${m.history_lag_seasons} season: a ${m.forecast_years[0]} outlook uses seasons up to ${m.forecast_years[0] - 2}`} wide />
          <Spec label="Data through" value={m.data_through} />
          <Spec label="Baselines" value="the last published season repeated, and the 3-season mean" wide />
          <Spec label="Validation" value="every past season is judged using only what had been published by then" wide />
        </div>
        <Note tone="info" title="Why a model is not behind the number">
          District yields are published more than a year late. Tested the way a forecaster would meet the data, a machine-learning model trained on the
          whole table did not beat the mean of the last three published seasons by the bar set in advance, for any crop. Giving the mean, with a range that
          has been checked, is the claim the evidence supports. The mean beat repeating the last published season for most crops, which is the reason to use it.
        </Note>
      </div>

      <div className="section-card fade-in">
        <div className="section-title">📋 Tested against bars written in advance</div>
        <Note tone="warn" title="An earlier version of this test was too generous, and was corrected">
          Testing each season with a model trained on every earlier season is not allowed by the publication lag: when a forecast for year Y is
          made, the yields of Y−1 are not yet published. Training only on what would have been known, the skill of the Rice/Maize and Wheat
          models against the 3-season mean fell from {signed(first[K].dev_skill_vs_mean3_pct)} to {signed(lag[K].dev_skill_vs_mean3_pct)} and from{' '}
          {signed(first[W].dev_skill_vs_mean3_pct)} to {signed(lag[W].dev_skill_vs_mean3_pct)}, and in 2024 to {signed(lag[K].skill_2024_vs_mean3_pct)} and{' '}
          {signed(lag[W].skill_2024_vs_mean3_pct)}. Every other figure on this page uses the corrected protocol.
        </Note>
        <div className="table-scroll">
          <table className="data-table">
            <thead><tr><th>Step</th><th>The bar</th><th>What happened</th><th /></tr></thead>
            <tbody>
              <tr>
                <td><strong>1 · Train from the one table</strong></td>
                <td>Kharif Rice + Maize ≥ +1.2% and Wheat ≥ +7.8% against the 3-season mean; both above 0 in 2024</td>
                <td>As first run, Kharif {signed(first[K].dev_skill_vs_mean3_pct)} and Wheat {signed(first[W].dev_skill_vs_mean3_pct)}.
                  Corrected: Kharif {signed(lag[K].dev_skill_vs_mean3_pct)} (2024 {signed(lag[K].skill_2024_vs_mean3_pct)}), Wheat {signed(lag[W].dev_skill_vs_mean3_pct)} (2024 {signed(lag[W].skill_2024_vs_mean3_pct)})</td>
                <td><Pill ok={c.M1.first_protocol.pass} /></td>
              </tr>
              <tr>
                <td><strong>2 · Do soil, irrigation and location help?</strong></td>
                <td>Staples: ≥ 2.0% lower error, lower in ≥ 4 of 6 years, not worse in 2024</td>
                <td>{signed(c.M2.dev_gain_pct)} on 2018–23 ({Object.values(years).filter(v => v > 0).length} of 6 years better), {signed(c.M2.gain_2024_pct)} in 2024
                  (first run: {signed(c.M2.first_protocol.dev_gain_pct)}). {c.M2.pass ? 'Used.' : 'Not used.'}</td>
                <td><Pill ok={c.M2.pass} /></td>
              </tr>
              <tr>
                <td><strong>3 · One model for every crop</strong></td>
                <td>A crop is forecast by the model if ≥ +2.0% against the 3-season mean on ≥ 300 unseen forecasts, better in ≥ 4 of 6 years, and not worse in 2024</td>
                <td>{c.M3.crops_served} of {c.M3.crops_tested} crops. {c.M3.near_misses.length} reached +2.0% on 2018–23 but each missed another condition:{' '}
                  {c.M3.near_misses.map((x, i) => (
                    <span key={x.crop}>{i ? '; ' : ' '}{x.crop} ({signed(x.dev_skill_vs_mean3_pct)}, {x.years_better} of 6 years, 2024 {x.skill_2024 == null ? 'not published' : signed(x.skill_2024)})</span>
                  ))}.
                  Rice and Wheat in the pooled model: {signed(c.M3.staples_in_pooled[K])} and {signed(c.M3.staples_in_pooled[W])}.</td>
                <td><Pill ok={c.M3.pass} /></td>
              </tr>
              <tr>
                <td><strong>4 · Range around the 3-season mean</strong></td>
                <td>80% range covers 72–88% on 2018–23 and 2024; volatile series ≥ 70%</td>
                <td>Covers {pct(c.B1.coverage.dev)} and {pct(c.B1.coverage.confirm_2024)}; volatile series {pct(c.B1.coverage.flagged_dev)} and {pct(c.B1.coverage.flagged_2024)}.
                  (Written after step 3 returned nothing to serve, and before it was computed.)</td>
                <td><Pill ok={c.B1.pass} /></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div className="section-card fade-in">
        <div className="section-title">
          🌾 Crop by crop
          <div className="seg-control">
            {[['model', 'By model result'], ['mean', 'By mean vs last season'], ['crop', 'A–Z']].map(([k, label]) => (
              <button key={k} className={sort === k ? 'active' : ''} onClick={() => setSort(k)}>{label}</button>
            ))}
          </div>
        </div>
        <p className="section-lede">
          Errors are each crop's own, on seasons not yet seen, in tonnes per hectare. Skill is the percentage by which one error is lower than another
          (negative means higher). Crops are never pooled into one error figure, because their units differ by a factor of a hundred.
        </p>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr><th>Crop</th><th className="num">Forecasts</th><th className="num">Mean error</th><th className="num">Last-season error</th><th className="num">Mean vs last season</th>
                <th className="num">Model vs mean</th><th className="num">Years model better</th><th className="num">Model 2024</th></tr>
            </thead>
            <tbody>
              {rows.map(r => (
                <tr key={r.crop}>
                  <td><strong>{r.crop}</strong></td>
                  <td className="num">{r.mean3.n.toLocaleString('en-IN')}</td>
                  <td className="num">{fmt(r.mean3.mean3_mae, 3)}</td>
                  <td className="num">{fmt(r.mean3.last_published_mae, 3)}</td>
                  <td className="num"><strong>{signed(r.mean3.mean3_vs_last_published_pct)}</strong></td>
                  <td className="num">{signed(r.model.dev.skill_vs_mean3_pct)}</td>
                  <td className="num">{r.model.years_better_than_mean3} / 6</td>
                  <td className="num">{signed(r.model.confirm_2024.skill_vs_mean3_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Note tone="warn" title="Read the model columns with the number tested in mind">
          {c.M3.crops_tested} crops were tested against the same bar, so a few would clear it by luck; the requirement of 4 good years out of 6 and a
          non-negative 2024 is the guard against that. Some crops, such as sugarcane, turmeric and ginger, have errors so large for the model that their
          skill figures are dominated by a few extreme records.
        </Note>
      </div>

      <div className="section-card fade-in">
        <div className="section-title">🚫 What did not help</div>
        <ul style={{ paddingLeft: '1.2rem', lineHeight: 1.8, fontSize: '0.9rem', color: 'var(--text-medium)' }}>
          <li><strong>A model trained on the whole table.</strong> With the real publication lag it did not beat the 3-season mean for any crop by the bar set in advance.</li>
          <li><strong>Weather and satellite data.</strong> Under the publication lag they cut error by about 1% on 2018–23 and by nothing in 2024 (measured with the earlier,
            more generous protocol), so they are not used, and would need a live feed.</li>
          <li><strong>Soil, irrigation and location columns.</strong> {signed(c.M2.dev_gain_pct)} against a bar of +2.0%: small but positive in{' '}
            {Object.values(years).filter(v => v > 0).length} of 6 years, so not used. A fresh test with a bar set in advance could revisit it.</li>
          <li><strong>The earlier state-level model.</strong> It forecast a state's yield from N, P, K, pH and weather inputs and was 9.6% <em>worse</em> than
            repeating last season's yield. It has been retired.</li>
        </ul>
      </div>

      <div className="section-card fade-in">
        <div className="section-title">⚠️ Limits</div>
        <Note tone="warn" title="2024 is a rough check, not a clean test">
          Only about 28 states have published 2024 yields, so its figures are partial.
        </Note>
        <Note tone="warn" title="Ranges are wide">
          An 80% range that holds 80% of the time has to be wide for a crop whose district yields swing from year to year. Volatile series are flagged and get wider ranges.
        </Note>
        <Note tone="info" title="District, not field">
          The outlook describes a district's typical yield for the crop and season. It does not know about a field's soil test, sowing date or a flood last week.
          Madhya Pradesh district figures in the source are about twice the Centre's official total for wheat.
        </Note>
      </div>
    </Page>
  )
}

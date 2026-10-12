import { Bar, KpiCard, Note, Page, PageHeader } from '../pages/shared'
import { fmt } from '../pages/api'

const n = v => (v == null ? '—' : Number(v).toLocaleString('en-IN'))

/**
 * The overview: what the one dataset holds, and what it supports forecasting. Every figure comes from /api/stats, which
 * is derived from the master table, so this page cannot show a number the other pages disagree with.
 */
export default function Dashboard({ stats, onNavigate }) {
  const d = stats?.dataset
  const o = stats?.outlook
  if (!d) return null

  return (
    <Page>
      <PageHeader
        icon="🏠"
        title="Dashboard"
        subtitle="One dataset from state to district, and an honest account of what it can forecast"
      />

      <div className="kpi-row fade-in">
        <KpiCard icon="🗃️" iconBg="var(--green-100)" label="RECORDS" value={n(d.rows)}
                 sub={`${n(d.district_rows)} district + ${n(d.state_only_rows)} state-only`}
                 title="One row per district, crop, season and year, plus rows for the few series only the original state dataset holds." />
        <KpiCard icon="📍" iconBg="var(--blue-bg)" label="DISTRICTS" value={n(d.districts)} sub={`in ${d.states_uts} states and UTs`} />
        <KpiCard icon="🌾" iconBg="var(--amber-bg)" label="CROPS" value={n(d.crops)} sub={`with a usable yield (${d.crops_listed ?? d.crops} listed)`} />
        <KpiCard icon="📅" iconBg="var(--purple-bg)" label="YEARS" value={`${d.year_min}–${d.year_max}`} sub={`${d.columns} columns per record`} />
      </div>

      <div className="section-card fade-in">
        <div className="section-title">🧩 What is in the table</div>
        <p className="section-lede">
          Every source is joined onto the same row. A column is left empty where a source does not reach, never filled in:
          the bar shows how much of a typical district record each group fills.
        </p>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr><th>Group</th><th className="num">Columns</th><th style={{ width: '38%' }}>Filled (typical district record)</th></tr>
            </thead>
            <tbody>
              {d.groups.map(g => (
                <tr key={g.group}>
                  <td>{g.group}</td>
                  <td className="num">{g.columns}</td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                      <div style={{ flex: 1 }}><Bar value={g.filled_pct} max={100} /></div>
                      <span className="num" style={{ minWidth: 48, textAlign: 'right' }}>{fmt(g.filled_pct, 1)}%</span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Note tone="info" title="How state and district fit together">
          The original state-level dataset is almost the sum of the district data: on {fmt(d.state_vs_district.yield_within_2pct, 1)}% of
          the state-crop-season-years both hold, the two yields agree within 2% ({fmt(d.state_vs_district.yield_within_10pct, 1)}% within
          10%). So its values sit on each district record as <code>state_*</code> columns instead of in a second dataset, and the district
          data adds Rajasthan, the Union Territories and 2021–{d.year_max}.
        </Note>
      </div>

      <div className="section-card fade-in">
        <div className="section-title">🎯 What the data supports</div>
        {o ? (
          <>
            <div className="kpi-row">
              <KpiCard icon="🗺️" iconBg="var(--green-100)" label="CROPS WITH AN OUTLOOK" value={n(o.crops_offered)}
                       sub={`${n(o.series)} series in ${n(o.districts)} districts, for ${o.forecast_years.join(' and ')}`} />
              <KpiCard icon="📏" iconBg="var(--blue-bg)" label="RANGE HELD" value={`${fmt(100 * o.range_coverage.dev_2018_2023, 0)}%`}
                       sub={`of seasons not yet seen, 2018–23 · 2024: ${fmt(100 * o.range_coverage.confirm_2024, 0)}% (80% intended)`}
                       title="How often the recorded yield fell inside the 80% range, across all crops, with each range built only from seasons published by then." />
              <KpiCard icon="🧪" iconBg="var(--amber-bg)" label="MODEL BEAT THE MEAN" value={`${o.model_crops_beating_mean} of ${o.model_crops_tested}`}
                       sub="crops where a machine-learning model cleared the bar set in advance"
                       title="The bar: at least 2% lower error than the mean of the last three published seasons, in at least 4 of 6 years, and not worse in 2024." />
            </div>
            <Note tone="info" title="Why the expected yield is a simple mean">
              The expected yield is the mean of the last three published seasons. A model trained on the whole table and tested the way a forecaster
              would meet the data, knowing only what had been published by then, did not beat that mean by the bar set in advance for any of the{' '}
              {o.model_crops_tested} crops tested, so none is used. The mean itself beat repeating the last published season for{' '}
              {o.mean_beats_last_published_crops} of {o.crops_offered} crops. The Model page lists every crop and every test, including the ones that failed.
            </Note>
          </>
        ) : (
          <Note tone="warn" title="Evaluation unavailable">The outlook summary could not be loaded from the server.</Note>
        )}
        <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap', marginTop: '1rem' }}>
          <button className="btn-predict" style={{ width: 'auto', padding: '0.6rem 1.2rem' }} onClick={() => onNavigate('district')}>🗺️ District Outlook</button>
          <button className="btn-predict" style={{ width: 'auto', padding: '0.6rem 1.2rem' }} onClick={() => onNavigate('map')}>🧭 District Map</button>
          <button className="btn-predict" style={{ width: 'auto', padding: '0.6rem 1.2rem' }} onClick={() => onNavigate('model')}>📈 Model &amp; Evidence</button>
        </div>
      </div>

      <Note tone="info" title="Sources">{d.sources}.</Note>
    </Page>
  )
}

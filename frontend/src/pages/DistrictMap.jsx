import { memo, useMemo, useState } from 'react'
import { ErrorState, KpiCard, Loading, Note, Page, PageHeader } from './shared'
import { fmt, useGet, skillVerdict } from './api'

/**
 * Every forecastable district for one crop and season, coloured by what the forecast says.
 *
 * Colour defaults to the change against the last published season, but for some crops that comparison mostly
 * shows a recent unusual year bouncing back, so "against the 3-season mean" and the plain level are one click away.
 * Districts whose yield has been jumping around are hatched: the forecast there has been less reliable.
 */

const SERIES = [
  { key: 'Rice|Kharif', label: 'Rice · Kharif' },
  { key: 'Maize|Kharif', label: 'Maize · Kharif' },
  { key: 'Wheat|Rabi', label: 'Wheat · Rabi' },
]
const METRICS = [
  { key: 'change_vs_last_pct', label: 'Change vs last published season', diverging: true },
  { key: 'change_vs_mean3_pct', label: 'Change vs 3-season mean', diverging: true },
  { key: 'forecast', label: 'Forecast level (t/ha)', diverging: false },
]
const NEUTRAL = [236, 240, 233]
const RED = [158, 26, 26]
const GREEN = [31, 122, 61]
const NO_DATA = '#dfe6e0'
const SPAN = 25 // percent that saturates the diverging scale

const mix = (a, b, t) => `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * t)).join(',')})`
const divergingColor = v => (v == null ? NO_DATA : v >= 0
  ? mix(NEUTRAL, GREEN, Math.min(1, v / SPAN)) : mix(NEUTRAL, RED, Math.min(1, -v / SPAN)))

const Shape = memo(function Shape({ d, fill, onEnter, onLeave, onPick, hatched }) {
  return (
    <>
      <path d={d} fill={fill} stroke="#ffffff" strokeWidth="0.05" strokeLinejoin="round"
            onMouseEnter={onEnter} onMouseLeave={onLeave} onClick={onPick} style={{ cursor: 'pointer' }} />
      {hatched && <path d={d} fill="url(#hatch)" stroke="none" pointerEvents="none" />}
    </>
  )
})

export default function DistrictMap({ onOpen }) {
  const [sel, setSel] = useState({ series: 'Rice|Kharif', year: 2025, metric: 'change_vs_last_pct' })
  const [hover, setHover] = useState(null)
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const [crop, season] = sel.series.split('|')

  const shapes = useGet('/api/district/shapes')
  const map = useGet(`/api/district/map?crop=${crop}&season=${season}&year=${sel.year}`)
  const metric = METRICS.find(m => m.key === sel.metric)

  const geometry = useMemo(() => {
    if (!shapes.data) return null
    const [west, south, east, north] = shapes.data.bounds
    const k = Math.cos((((south + north) / 2) * Math.PI) / 180)   // keep east-west distances in proportion
    const paths = {}
    for (const [sid, rings] of Object.entries(shapes.data.shapes)) {
      paths[sid] = rings.map(r => 'M' + r.map(([x, y]) => `${((x - west) * k).toFixed(2)} ${(north - y).toFixed(2)}`).join('L') + 'Z').join('')
    }
    return { paths, width: (east - west) * k, height: north - south }
  }, [shapes.data])

  const scale = useMemo(() => {
    if (!map.data || metric.diverging) return null
    const v = map.data.districts.map(d => d.forecast).sort((a, b) => a - b)
    return { lo: v[Math.floor(v.length * 0.05)], hi: v[Math.floor(v.length * 0.95)] }
  }, [map.data, metric])

  const colorOf = d => (metric.diverging ? divergingColor(d[metric.key])
    : mix(NEUTRAL, GREEN, Math.min(1, Math.max(0, (d.forecast - scale.lo) / (scale.hi - scale.lo || 1)))))

  if (shapes.error) return <Page><ErrorState error={shapes.error} /></Page>

  const districts = map.data?.districts || []
  const byShape = new Map()
  districts.forEach(d => byShape.set(d.shape_id, d)) // districts sharing an outline (Sikkim) show the last one
  const changes = districts.map(d => d.change_vs_last_pct).filter(v => v != null).sort((a, b) => a - b)
  const median = changes.length ? changes[Math.floor(changes.length / 2)] : null
  const dev = map.data?.skill?.dev_2018_2023
  const h = hover != null ? byShape.get(hover) : null

  return (
    <Page>
      <PageHeader icon="🧭" title="District Map" subtitle="Where the next-season forecast sits against recent history, district by district" />

      <div className="section-card fade-in">
        <div className="section-title">🎛️ What to draw</div>
        <div className="input-row cols-3">
          <div className="form-field">
            <label>Crop · season</label>
            <select value={sel.series} onChange={e => setSel({ ...sel, series: e.target.value })}>
              {SERIES.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          </div>
          <div className="form-field">
            <label>Forecast year</label>
            <select value={sel.year} onChange={e => setSel({ ...sel, year: Number(e.target.value) })}>
              <option value={2025}>2025</option>
              <option value={2026}>2026</option>
            </select>
          </div>
          <div className="form-field">
            <label>Colour by</label>
            <select value={sel.metric} onChange={e => setSel({ ...sel, metric: e.target.value })}>
              {METRICS.map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
            </select>
          </div>
        </div>
      </div>

      {(map.loading || shapes.loading) && <Loading label="Drawing the map…" />}
      {map.error && <div className="section-card"><Note tone="warn" title="No map for this selection">{map.error}</Note></div>}

      {map.data && geometry && (
        <>
          <div className="kpi-row fade-in">
            <KpiCard icon="🗺️" iconBg="var(--green-100)" label="DISTRICTS FORECAST" value={districts.length.toLocaleString('en-IN')}
                     sub={`${map.data.group} · ${map.data.forecast_year}`} />
            <KpiCard icon="📈" iconBg="var(--blue-bg)" label="MEDIAN CHANGE VS LAST PUBLISHED"
                     value={median == null ? '—' : `${median > 0 ? '+' : ''}${fmt(median, 1)}%`}
                     sub="across mapped districts" />
            <KpiCard icon="⚠️" iconBg="var(--amber-bg)" label="VOLATILE (HATCHED)" value={districts.filter(d => d.low_trust).length}
                     sub="forecast less reliable, wider range" />
          </div>

          <div className="section-card fade-in">
            <div className="section-title">{SERIES.find(s => s.key === sel.series).label} · {metric.label}</div>
            <div style={{ position: 'relative', maxWidth: 640, margin: '0 auto' }}
                 onMouseMove={e => { const r = e.currentTarget.getBoundingClientRect(); setPos({ x: e.clientX - r.left, y: e.clientY - r.top }) }}>
              <svg viewBox={`0 0 ${geometry.width.toFixed(2)} ${geometry.height.toFixed(2)}`} style={{ width: '100%', height: 'auto', display: 'block' }}
                   role="img" aria-label="Map of India coloured by district forecast">
                <defs>
                  <pattern id="hatch" width="0.5" height="0.5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                    <line x1="0" y1="0" x2="0" y2="0.5" stroke="#2a3d30" strokeWidth="0.12" opacity="0.55" />
                  </pattern>
                </defs>
                {Object.entries(geometry.paths).map(([sid, d]) => {
                  const dist = byShape.get(sid)
                  return (
                    <Shape key={sid} d={d} fill={dist ? colorOf(dist) : NO_DATA} hatched={Boolean(dist?.low_trust)}
                           onEnter={dist ? () => setHover(sid) : undefined} onLeave={() => setHover(null)}
                           onPick={dist ? () => onOpen({ state: dist.state, district: String(dist.district_code), series: sel.series, year: sel.year }) : undefined} />
                  )
                })}
              </svg>
              {h && (
                <div style={{
                  position: 'absolute', left: Math.min(pos.x + 14, 380), top: pos.y + 14, pointerEvents: 'none', zIndex: 5,
                  background: '#fff', border: '1px solid #b8c9bd', borderRadius: 10, padding: '0.5rem 0.7rem',
                  fontSize: '0.82rem', boxShadow: '0 6px 20px rgba(0,0,0,0.12)', minWidth: 190,
                }}>
                  <strong>{h.name}</strong>, {h.state}
                  <div>Forecast <strong>{fmt(h.forecast)}</strong> t/ha ({fmt(h.low)}–{fmt(h.high)})</div>
                  <div>Last published {fmt(h.last_published)} · 3-season mean {fmt(h.mean3)}</div>
                  <div>{h.change_vs_last_pct > 0 ? '+' : ''}{fmt(h.change_vs_last_pct, 1)}% vs last published</div>
                  {h.low_trust && <div style={{ color: 'var(--amber)' }}>Volatile series: less reliable</div>}
                  <div style={{ color: 'var(--text-light)', marginTop: 4 }}>Click for the full forecast</div>
                </div>
              )}
            </div>
            <Legend metric={metric} scale={scale} />
          </div>

          <div className="section-card fade-in">
            <div className="section-title">⚖️ How to read this</div>
            {dev && (
              <Note tone={skillVerdict(map.data.group, dev.skill_vs_mean3_pct).tone}
                    title={skillVerdict(map.data.group, dev.skill_vs_mean3_pct).title}>
                On seasons it had not seen (2018–2023) its error was {fmt(dev.skill_vs_last_published_pct, 1)}% lower than repeating the
                last published season and {fmt(dev.skill_vs_mean3_pct, 1)}% lower than the 3-season mean. Colours are forecasts, not
                measurements: a dark red district is one where the model expects less than its recent record, with the range shown on hover.
              </Note>
            )}
            <Note tone="info" title="Why “vs last published” is not the whole story">
              District yields are published more than a year late, so “last published” is the season before last, and a single odd
              season makes the next one look like a swing back. The 3-season mean option damps that. Outlines are simplified for
              drawing; do not use them to measure area. Districts with no outline or no recent record are grey.
            </Note>
          </div>
        </>
      )}
    </Page>
  )
}

function Legend({ metric, scale }) {
  const stops = metric.diverging
    ? [-SPAN, -SPAN / 2, 0, SPAN / 2, SPAN].map(v => ({ label: `${v > 0 ? '+' : ''}${v}%`, color: divergingColor(v) }))
    : [0, 0.25, 0.5, 0.75, 1].map(t => ({ label: fmt(scale.lo + (scale.hi - scale.lo) * t, 1), color: mix(NEUTRAL, GREEN, t) }))
  return (
    <div style={{ display: 'flex', justifyContent: 'center', gap: '1.4rem', flexWrap: 'wrap', marginTop: '0.8rem', fontSize: '0.8rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        {stops.map(s => (
          <span key={s.label} style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
            <span style={{ width: 34, height: 12, background: s.color, border: '1px solid #cdd8cf' }} />
            <span>{s.label}</span>
          </span>
        ))}
      </div>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        <span style={{ width: 20, height: 12, background: `repeating-linear-gradient(45deg, #d9e2da, #d9e2da 2px, #7d8d82 2px, #7d8d82 3px)`, border: '1px solid #cdd8cf' }} /> volatile series
      </span>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
        <span style={{ width: 20, height: 12, background: NO_DATA, border: '1px solid #cdd8cf' }} /> no forecast
      </span>
    </div>
  )
}

import { useState, useEffect } from 'react'
import { API_BASE } from '../constants'

/**
 * One fetch hook for every page. Returns { data, error, loading }.
 *
 * Kept in a .js file separate from the shared components so Fast Refresh keeps
 * working: a module that exports both components and plain functions loses it.
 */
export function useApi(path, seed = null) {
  const [state, setState] = useState({ data: seed, error: null, loading: seed === null })

  useEffect(() => {
    if (!path) return
    let alive = true
    fetch(`${API_BASE}${path}`)
      .then(r => {
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
        return r.json()
      })
      .then(d => { if (alive) setState({ data: d, error: null, loading: false }) })
      .catch(e => { if (alive) setState(s => ({ ...s, error: e.message, loading: false })) })
    return () => { alive = false }
  }, [path])

  return state
}

function errorText(data, r) {
  const d = data?.detail
  return typeof d === 'string' ? d
    : Array.isArray(d) ? d.map(e => `${e.loc?.at(-1)}: ${e.msg.replace(/^Value error, /, '')}`).join('; ')
    : `${r.status} ${r.statusText}`
}

/** GET a JSON endpoint; throws an Error carrying the server's own explanation on a non-2xx. */
export async function getJson(path) {
  const r = await fetch(`${API_BASE}${path}`)
  const data = await r.json().catch(() => null)
  if (!r.ok) throw new Error(errorText(data, r))
  return data
}

/**
 * Like useApi, but safe to re-point at a new path: until the new response arrives it reports loading
 * (never the previous path's data), and it never sets state synchronously inside the effect.
 */
export function useGet(path) {
  const [res, setRes] = useState({ path: null, data: null, error: null })
  useEffect(() => {
    if (!path) return undefined
    let alive = true
    getJson(path)
      .then(data => { if (alive) setRes({ path, data, error: null }) })
      .catch(e => { if (alive) setRes({ path, data: null, error: e.message }) })
    return () => { alive = false }
  }, [path])
  const fresh = res.path === path
  return { data: fresh ? res.data : null, error: fresh ? res.error : null, loading: Boolean(path) && !fresh }
}

export const CHART_COLORS = {
  green: '#1f7a3d',
  blue: '#1e5c9e',
  amber: '#a8630a',
  purple: '#5c359e',
  teal: '#166b5f',
  red: '#9e1a1a',
}

/** Shared Recharts styling so every chart on every page reads as one system. */
export const axisProps = {
  tick: { fontSize: 11, fill: '#485c4e' },
  stroke: '#b8c9bd',
}

export const gridProps = {
  strokeDasharray: '3 3',
  stroke: '#e3ebe5',
  vertical: false,
}

export const tooltipStyle = {
  contentStyle: {
    background: '#fff',
    border: '1px solid #b8c9bd',
    borderRadius: 10,
    fontSize: '0.82rem',
    boxShadow: '0 6px 20px rgba(0,0,0,0.1)',
  },
}

export function fmt(n, digits = 2) {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  return Number(n).toLocaleString('en-IN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

/**
 * State, district, crop and season, and year selection for the outlook, shared by the Dashboard and the District Outlook page.
 * `initial` pre-selects a series (a click on the District Map). Until the options arrive every list is empty.
 */
export function useSeriesPicker(initial, fallbackState = 'Punjab') {
  const opts = useGet('/api/district/options')
  const [sel, setSel] = useState(initial || {})
  const options = opts.data?.states
  const states = options ? Object.keys(options).sort() : []
  const state = states.includes(sel.state) ? sel.state : (states.includes(fallbackState) ? fallbackState : states[0])
  const districts = state ? Object.entries(options[state]).sort((a, b) => a[1].name.localeCompare(b[1].name)) : []
  const district = districts.find(([c]) => c === sel.district)?.[0] ?? districts[0]?.[0]
  const seriesList = district ? options[state][district].series : []
  const seriesKey = s => `${s.crop}|${s.season}`
  const series = seriesList.find(s => seriesKey(s) === sel.series) ?? seriesList[0]
  const year = sel.year ?? 2025
  const query = district && series
    ? `district_code=${district}&crop=${encodeURIComponent(series.crop)}&season=${encodeURIComponent(series.season)}` : null
  return { opts, sel, setSel, states, state, districts, district, seriesList, series, seriesKey, year, query }
}

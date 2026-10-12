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

/**
 * POST a forecast request. Throws an Error carrying the server's own explanation (a 422
 * says which label or range was wrong, or that the series has no history) instead of a
 * bare "422 Unprocessable Entity".
 */
export async function postPredict(body) {
  const r = await fetch(`${API_BASE}/api/predict`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await r.json().catch(() => null)
  if (!r.ok) {
    const d = data?.detail
    const text = typeof d === 'string' ? d
      : Array.isArray(d) ? d.map(e => `${e.loc?.at(-1)}: ${e.msg.replace(/^Value error, /, '')}`).join('; ')
      : null
    throw new Error(text || `${r.status} ${r.statusText}`)
  }
  return data
}

/**
 * A forecast anchors on a series' own history, so only state/crop/season combinations
 * that have records are offered. `options.series` is {state: {crop: [seasons]}}; until
 * the live options arrive the bundled seed has no such map and the full lists are used.
 */
export function cropsFor(options, state) {
  const s = options?.series?.[state]
  return s ? Object.keys(s) : options?.crops ?? []
}

export function seasonsFor(options, state, crop) {
  return options?.series?.[state]?.[crop] ?? options?.seasons ?? []
}

/** Keep the current crop/season when still valid for `state`, else the first valid one. */
export function reconcile(options, state, crop, season) {
  const crops = cropsFor(options, state)
  const nextCrop = crops.includes(crop) ? crop : crops[0] ?? crop
  const seasons = seasonsFor(options, state, nextCrop)
  return { crop: nextCrop, season: seasons.includes(season) ? season : seasons[0] ?? season }
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
 * How to describe a model against the 3-season mean, from the measured skill alone. Three tiers, so a margin of a
 * couple of percent is not promoted to "beats the baselines".
 */
export function skillVerdict(group, pctVsMean3) {
  if (pctVsMean3 < 2) return { tone: 'warn', title: `For ${group} this model is about as good as the 3-season average` }
  if (pctVsMean3 < 5) return { tone: 'info', title: `For ${group} this model is a little better than the 3-season average` }
  return { tone: 'info', title: `For ${group} this model beats both simple baselines` }
}

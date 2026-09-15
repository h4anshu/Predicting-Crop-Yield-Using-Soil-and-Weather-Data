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

// Fails if the seed data baked into src/constants.js has drifted from the live API.
// Run after re-training the model or changing the dataset:  node check-constants.mjs
// Check against a local API instead of the deployed one:  API_BASE=http://localhost:8000 node check-constants.mjs
import assert from 'node:assert'
import { API_BASE as DEPLOYED_API, DEFAULT_OPTIONS, DEFAULT_STATS } from './src/constants.js'

const API_BASE = process.env.API_BASE ?? DEPLOYED_API

const get = async (p) => {
  const r = await fetch(`${API_BASE}${p}`)
  assert.equal(r.status, 200, `${p} returned ${r.status}`)
  return r.json()
}

// every key the seed has must equal the live value; the live payload may carry more (the model summary)
const [options, stats] = await Promise.all([get('/api/options'), get('/api/stats')])
for (const [seed, live, name] of [[DEFAULT_OPTIONS, options, 'options'], [DEFAULT_STATS, stats, 'stats']]) {
  for (const key of Object.keys(seed)) {
    if (seed[key] === null) continue
    assert.deepStrictEqual(seed[key], live[key],
      `constants.js ${name}.${key} is stale — update it from ${API_BASE}`)
  }
}
console.log('OK: seed data matches live API')

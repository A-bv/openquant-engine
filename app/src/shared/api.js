// Single source of truth for the API base URL.
//
// Dev falls back to the local FastAPI server. Production builds must set
// VITE_API_URL at build time — the old fallback guessed `hostname:8000`,
// which is a broken URL on any static host (e.g. a-bv.github.io:8000).
const API = import.meta.env.VITE_API_URL
  || (import.meta.env.DEV ? 'http://127.0.0.1:8000' : null)

if (!API) {
  throw new Error(
    'VITE_API_URL is not set. Production builds need the API address at ' +
    'build time, e.g. VITE_API_URL=https://openquant-api.onrender.com npm run build'
  )
}

export default API

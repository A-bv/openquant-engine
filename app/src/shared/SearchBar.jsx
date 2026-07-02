import { useState } from 'react'

function fmt(n, decimals = 1) {
  if (n == null) return '—'
  if (Math.abs(n) >= 1e12) return `$${(n / 1e12).toFixed(decimals)}T`
  if (Math.abs(n) >= 1e9)  return `$${(n / 1e9).toFixed(decimals)}B`
  if (Math.abs(n) >= 1e6)  return `$${(n / 1e6).toFixed(decimals)}M`
  return `$${n.toFixed(2)}`
}

export default function SearchBar({ onAnalyse, loading, data, value = '', showSummary = true }) {
  const [input, setInput] = useState(value)

  const handleSubmit = (e) => {
    e.preventDefault()
    const t = input.trim().toUpperCase()
    if (t) onAnalyse(t)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <form onSubmit={handleSubmit} className="search-form">
        <input
          value={input}
          onChange={e => setInput(e.target.value.toUpperCase())}
          placeholder="Enter ticker — e.g. ACN, AAPL, MSFT"
          disabled={loading}
          className="ticker-input"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="primary-button"
        >
          {loading ? 'Analysing…' : 'Analyse'}
        </button>
      </form>

      {showSummary && data && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <span style={{
            background: '#E6F1FB',
            color: '#185FA5',
            borderRadius: 6,
            padding: '3px 10px',
            fontSize: 13,
            fontWeight: 600,
          }}>
            {data.ticker}
          </span>
          <span style={{ fontSize: 13, color: '#111827', fontWeight: 500 }}>
            {data.company_name}
          </span>
          {data.sector && (
            <span style={{ fontSize: 12, color: '#9CA3AF' }}>· {data.sector}</span>
          )}
          <span style={{ marginLeft: 'auto', fontSize: 15, fontWeight: 700, color: '#111827' }}>
            {fmt(data.current_price, 2).replace('$', '')} <span style={{ fontSize: 12, color: '#6B7280', fontWeight: 400 }}>USD · {fmt(data.market_cap)} mkt cap</span>
          </span>
        </div>
      )}
    </div>
  )
}

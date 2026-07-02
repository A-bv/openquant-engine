import { useState } from 'react'
import axios from 'axios'
import DisclosureSection from '../../shared/DisclosureSection'
import EPFLCitation from '../../shared/EPFLCitation'

const PRESETS = [
  { label: 'Tech basket', value: 'AAPL, MSFT, NVDA, GOOGL, AMZN, META' },
  { label: 'Diversified (stocks + gold + bonds)', value: 'AAPL, JPM, XOM, GLD, TLT' },
]

const pct = (x, d = 1) => `${(x * 100).toFixed(d)}%`

function MetricCard({ label, value, sub }) {
  return (
    <div style={{ background: '#F8FAFC', borderRadius: 8, padding: '14px 16px' }}>
      <div style={{ fontSize: 12, color: '#6B7280' }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, color: '#111827', marginTop: 2 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: '#9CA3AF', marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

export default function DiversificationLab({ API }) {
  const [input, setInput] = useState(PRESETS[0].value)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [data, setData] = useState(null)

  const run = async (raw) => {
    const tickers = (raw ?? input)
      .split(/[\s,]+/).map(s => s.trim().toUpperCase()).filter(Boolean)
    if (tickers.length < 2) { setError('Enter at least 2 tickers.'); return }
    setInput(tickers.join(', '))
    setLoading(true); setError(null); setData(null)
    try {
      const res = await axios.post(`${API}/diversification`, { tickers, years: 3 })
      setData(res.data)
    } catch (e) {
      const detail = e.response?.data?.detail
      setError(
        (typeof detail === 'object' ? detail?.error : detail) ||
        'Diversification request failed. Is the backend running?'
      )
    } finally {
      setLoading(false)
    }
  }

  const topIdx = data ? data.risk_contributions.indexOf(Math.max(...data.risk_contributions)) : -1
  const order = data
    ? data.tickers.map((_, i) => i).sort((a, b) => data.risk_contributions[b] - data.risk_contributions[a])
    : []
  const maxRisk = data ? Math.max(...data.risk_contributions) : 1

  return (
    <>
      <section className="card intro-card">
        <div className="eyebrow">Risk &amp; Portfolio Lab</div>
        <h1 className="page-title">How many bets are you really making?</h1>
        <p className="page-copy">
          Enter the tickers you hold (equal-weighted). OpenQuant pulls 3 years of
          real returns and works out, from how they move together, how many
          <em> independent</em> bets your portfolio actually is, and which holding
          secretly drives your risk.
        </p>
        <p className="intro-proof">
          Real market data · exam-tested formulas · your real number of bets
        </p>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '14px 0 10px' }}>
          {PRESETS.map(p => (
            <button key={p.label} onClick={() => run(p.value)} disabled={loading}
              style={{ fontSize: 12, padding: '6px 12px', borderRadius: 8, border: '0.5px solid #D1D5DB', background: '#fff', cursor: 'pointer', color: '#374151' }}>
              {p.label}
            </button>
          ))}
        </div>

        <div style={{ display: 'flex', gap: 8 }}>
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && run()}
            placeholder="AAPL, MSFT, NVDA, ..."
            style={{ flex: 1, padding: '10px 14px', fontSize: 14, borderRadius: 8, border: '0.5px solid #D1D5DB', fontFamily: 'inherit' }}
          />
          <button onClick={() => run()} disabled={loading}
            style={{ padding: '10px 20px', fontSize: 14, fontWeight: 600, borderRadius: 8, border: 'none', background: '#111827', color: '#fff', cursor: 'pointer' }}>
            {loading ? 'Analysing…' : 'Analyse'}
          </button>
        </div>
      </section>

      {error && (
        <div style={{ background: '#FCEBEB', border: '0.5px solid #F5B5B5', borderRadius: 8, padding: '14px 18px', color: '#A32D2D', fontSize: 13 }}>
          {error}
        </div>
      )}

      {data && (
        <>
          {/* Layer 1 — the result */}
          <section className="card">
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap', marginBottom: 4 }}>
              <span style={{ fontSize: 30, fontWeight: 700, color: '#111827' }}>
                {data.n_holdings} holdings = {data.effective_bets.toFixed(1)} bets
              </span>
              <span style={{ fontSize: 13, color: '#6B7280' }}>in real risk terms</span>
            </div>
            <div style={{ fontSize: 12, color: '#9CA3AF', marginBottom: 16 }}>{data.tickers.join(' · ')}</div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
              <MetricCard label="Effective bets" value={data.effective_bets.toFixed(1)} sub={`from ${data.n_holdings} positions`} />
              <MetricCard label="Real volatility" value={pct(data.portfolio_vol)} sub="per year" />
              <MetricCard label="If uncorrelated" value={pct(data.independent_vol)} sub={`you carry ${data.risk_multiple.toFixed(1)}× that risk`} />
            </div>

            {topIdx >= 0 && (
              <div style={{ marginTop: 16, padding: '12px 14px', background: '#F8FAFC', borderLeft: '3px solid #185FA5', borderRadius: '0 8px 8px 0', fontSize: 14, color: '#374151' }}>
                Risk is driven by <strong>{data.tickers[topIdx]}</strong>: {Math.round(data.weights[topIdx] * 100)}% of your money, but <strong>{Math.round(data.risk_contributions[topIdx] * 100)}% of your risk</strong>.
              </div>
            )}

            <div style={{ marginTop: 10, fontSize: 13, color: '#6B7280', display: 'flex', gap: 8 }}>
              <span>⚠️</span>
              <span>In a crisis, holdings tend to move together, so your real diversification is even weaker than this calm-times snapshot.</span>
            </div>
          </section>

          {/* Layer 2 — show your work */}
          <DisclosureSection
            eyebrow="Show your work"
            title="Per-holding risk decomposition & formulas"
            summary="Open this for each holding's true risk share, how the holdings move together, the Sharpe ratio, and the source pinned by tests."
          >
            <h3 style={{ fontSize: 14, fontWeight: 700, color: '#111827', margin: '0 0 4px' }}>
              Risk contribution by holding
              <EPFLCitation source="Berk-DeMarzo Ch.11.3-11.5 · formula sheet p.2-3" test="test_portfolio.py::TestExam2P4_ReducesToTwoAsset" />
            </h3>
            <p style={{ fontSize: 12, color: '#6B7280', margin: '0 0 12px' }}>
              Euler decomposition: a position's risk share can far exceed its share of the money.
            </p>

            {order.map(i => (
              <div key={data.tickers[i]} style={{ display: 'grid', gridTemplateColumns: '64px 1fr 152px', alignItems: 'center', gap: 10, margin: '7px 0' }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: '#111827' }}>{data.tickers[i]}</span>
                <span style={{ position: 'relative', height: 18, background: '#F1F5F9', borderRadius: 4, overflow: 'hidden' }}>
                  <span style={{ position: 'absolute', left: 0, top: 0, bottom: 0, width: `${(data.risk_contributions[i] / maxRisk * 100).toFixed(0)}%`, background: i === topIdx ? '#FAD4D4' : '#CFE3F7' }} />
                  <span style={{ position: 'absolute', left: 8, top: 0, lineHeight: '18px', fontSize: 12, color: i === topIdx ? '#A32D2D' : '#185FA5' }}>{pct(data.risk_contributions[i])} of risk</span>
                </span>
                <span style={{ fontSize: 11, color: '#9CA3AF', textAlign: 'right' }}>{Math.round(data.weights[i] * 100)}% cap · vol {pct(data.standalone_vols[i], 0)}</span>
              </div>
            ))}

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: 10, marginTop: 14 }}>
              <MetricCard label="Avg correlation" value={data.mean_correlation.toFixed(2)} sub="off-diagonal mean" />
              <MetricCard label="Diversification ratio" value={data.diversification_ratio.toFixed(2)} sub="bets = DR²" />
              <MetricCard label="Sharpe" value={data.sharpe.toFixed(2)} sub={`(${pct(data.expected_return, 0)} − ${pct(data.risk_free_rate, 0)}) / ${pct(data.portfolio_vol, 0)}`} />
            </div>

            <div style={{ marginTop: 14, fontSize: 12, color: '#9CA3AF', lineHeight: 1.6, fontFamily: 'monospace' }}>
              Var(R_p) = wᵀΣw &nbsp;·&nbsp; σ_indep = √(Σ wᵢ²σᵢ²) &nbsp;·&nbsp; bets = (Σ wᵢσᵢ / σ_p)²
            </div>
            <div style={{ marginTop: 6, fontSize: 11, color: '#9CA3AF' }}>
              Computed from {data.trading_days} real trading days. Pinned against the
              Sample Exam 2 portfolio problem (σ_p = 0.07 at ρ = −1; min-variance ω_Y = 0.20).
            </div>
          </DisclosureSection>
        </>
      )}
    </>
  )
}

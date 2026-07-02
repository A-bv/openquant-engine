const fmt$ = v => v == null || !Number.isFinite(v) ? '—' : `$${v.toFixed(2)}`
const fmtMcap = v => {
  if (v == null || !Number.isFinite(v)) return '—'
  const b = v / 1e9
  if (b >= 1000) return `$${(b/1000).toFixed(1)}T`
  if (b >= 100)  return `$${b.toFixed(0)}B`
  return `$${b.toFixed(1)}B`
}
const pct = (v, d = 1) => v == null || !Number.isFinite(v) ? '—' : `${(v * 100).toFixed(d)}%`

function Metric({ label, value, detail, tone = 'neutral' }) {
  const colour = tone === 'red' ? '#A32D2D'
    : tone === 'green' ? '#2F6B2F'
    : tone === 'blue' ? '#185FA5'
    : '#111827'

  return (
    <div className="metric-tile">
      <div className="metric-label">
        {label}
      </div>
      <div className="metric-value" style={{ color: colour }}>
        {value}
      </div>
      {detail && (
        <div className="metric-detail">
          {detail}
        </div>
      )}
    </div>
  )
}

export default function HeroVerdict({ d }) {
  if (!d) return null

  const p = d.current_price
  const ivBase = d.dcf?.base?.iv
  const upside = (Number.isFinite(p) && Number.isFinite(ivBase) && p > 0)
    ? (ivBase / p - 1)
    : null
  const implied = d.reverse_dcf?.implied_growth
  const historical = d.reverse_dcf?.historical_median
  const gap = d.reverse_dcf?.gap_vs_historical
  const baseGap = upside == null ? null : Math.abs(upside)

  const analysisText = !d.dcf || !Number.isFinite(implied)
    ? `The DCF model could not be fully computed for ${d.company_name}. See the warnings below.`
    : `At ${fmt$(p)}, the market is asking you to believe ${d.company_name} can grow free cash flow at ${pct(implied)} per year for the next decade.`

  const decisionText = Number.isFinite(gap)
    ? gap > 0.05
      ? `That is ${pct(gap)} above its historical median. The question is whether you believe that acceleration.`
      : gap < -0.05
        ? `That is ${pct(Math.abs(gap))} below its historical median. The price is assuming a slowdown.`
        : `That is close to its historical median. The price mostly assumes continuity.`
    : 'The useful output is the assumption, not an action label.'

  return (
    <section className="card hero-card">
      <div className="hero-grid">
        <div>
          <div className="hero-company">
            <h2>{d.company_name}</h2>
            <span className="ticker-pill">
              {d.ticker}
            </span>
            <span style={{ fontSize: 12, color: '#9CA3AF' }}>· {d.sector}</span>
          </div>
          <div className="hero-statement">
            {analysisText}
          </div>
          <p className="hero-support">
            {decisionText}
          </p>
        </div>

        <div className="metric-stack">
          <Metric
            label="Market price"
            value={fmt$(p)}
            detail={`${fmtMcap(d.market_cap)} market cap`}
          />
          <Metric
            label="Base DCF value"
            value={fmt$(ivBase)}
            detail={upside == null ? 'No model gap' : `${pct(baseGap)} ${upside >= 0 ? 'above' : 'below'} market price`}
            tone={upside == null ? 'neutral' : upside >= 0 ? 'green' : 'red'}
          />
          <Metric
            label="Implied growth"
            value={pct(implied)}
            detail={`${pct(historical)} historical median`}
            tone="blue"
          />
        </div>
      </div>

      <div className="method-note">
        This is not an action signal. It is a map of the assumptions today's
        price requires.
      </div>
    </section>
  )
}

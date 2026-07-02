const pct = v => (v == null || !Number.isFinite(v)) ? '—' : `${(v * 100).toFixed(1)}%`
const num = (v, d = 2) => (v == null || !Number.isFinite(v)) ? '—' : v.toFixed(d)

function Row({ label, value, explanation, highlight }) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'flex-start',
      gap: 16,
      padding: '12px 0',
      borderBottom: '0.5px solid #F3F4F6',
    }}>
      <div style={{ flex: '0 0 180px', fontSize: 13, fontWeight: 600, color: '#111827' }}>
        {label}
      </div>
      <div style={{ flex: 1, fontSize: 12, color: '#6B7280', lineHeight: 1.5 }}>
        {explanation}
      </div>
      <div style={{
        fontSize: highlight ? 18 : 15,
        fontWeight: 700,
        color: highlight ? '#185FA5' : '#111827',
        minWidth: 70,
        textAlign: 'right',
      }}>
        {value}
      </div>
    </div>
  )
}

export default function WACCBreakdown({ wacc }) {
  const betaFinite = Number.isFinite(wacc?.beta)
  const betaMove = betaFinite ? ((wacc.beta - 1) * 100).toFixed(0) : '—'
  const direction = betaFinite && wacc.beta >= 1 ? 'more' : 'less'

  return (
    <div style={{ display: 'flex', flexDirection: 'column' }}>
      <Row
        label="Risk-free rate"
        explanation="Return on 10-year US Treasury — the baseline safe return"
        value={pct(wacc.risk_free_rate)}
      />
      <Row
        label={`Beta · ${num(wacc.beta)}`}
        explanation={betaFinite
          ? `How much this company moves relative to the market. ${num(wacc.beta)} means it moves ~${Math.abs(betaMove)}% ${direction} than the S&P 500`
          : `Beta could not be computed for this company (insufficient price history or flat market over the lookback window).`}
        value={num(wacc.beta)}
      />
      <Row
        label="Market risk premium"
        explanation="Extra return investors demand for stocks over Treasury bonds (Damodaran estimate)"
        value={pct(wacc.market_risk_premium)}
      />
      <Row
        label="Cost of equity"
        explanation={`CAPM: ${pct(wacc.risk_free_rate)} + ${num(wacc.beta)} × ${pct(wacc.market_risk_premium)} = ${pct(wacc.cost_of_equity)}`}
        value={pct(wacc.cost_of_equity)}
      />
      <Row
        label="Cost of debt (after-tax)"
        explanation={`Pre-tax cost ${pct(wacc.cost_of_debt_pretax)} × (1 − ${pct(wacc.tax_rate)} tax rate). Cheaper than equity — debt is senior in bankruptcy`}
        value={pct(wacc.cost_of_debt_aftertax)}
      />
      <Row
        label="WACC"
        explanation={`${pct(wacc.equity_weight)} equity × ${pct(wacc.cost_of_equity)} + ${pct(wacc.debt_weight)} debt × ${pct(wacc.cost_of_debt_aftertax)} = ${pct(wacc.wacc)}`}
        value={pct(wacc.wacc)}
        highlight
      />
    </div>
  )
}

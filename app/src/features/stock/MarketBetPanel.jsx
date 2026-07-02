/**
 * The featured "reverse DCF" panel — the project's signature insight.
 *
 * Tells the user what growth rate today's price implies, framed as
 * "the market's bet." Comes second on the page, right after the hero.
 */

import EPFLCitation from '../../shared/EPFLCitation'
import LearnMore from '../../shared/LearnMore'

const pct = (v, d = 1) => v == null || !Number.isFinite(v) ? '—' : `${(v * 100).toFixed(d)}%`

function GrowthBar({ label, value, max, colour, reference = false }) {
  if (!Number.isFinite(value)) return null
  const width = Math.max(0, Math.min(100, (value / max) * 100))
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, fontSize: 12 }}>
      <div style={{ width: 160, color: '#6B7280', flexShrink: 0 }}>{label}</div>
      <div style={{ flex: 1, height: 18, background: '#F3F4F6', borderRadius: 3, position: 'relative' }}>
        <div style={{
          height: '100%',
          width: `${width}%`,
          background: colour,
          borderRadius: 3,
          borderRight: reference ? `2px dashed ${colour}` : 'none',
        }} />
      </div>
      <div style={{ minWidth: 60, textAlign: 'right', fontWeight: 700, color: '#111827' }}>
        {pct(value)}
      </div>
    </div>
  )
}

export default function MarketBetPanel({ d }) {
  if (!d || !d.reverse_dcf || d.reverse_dcf.failed) {
    return (
      <section style={{
        background: '#FFFFFF', border: '0.5px solid #E5E7EB',
        borderRadius: 12, padding: '20px 24px',
      }}>
        <div style={{ fontSize: 13, color: '#A32D2D' }}>
          Reverse DCF could not be computed for this stock.
        </div>
      </section>
    )
  }

  const r = d.reverse_dcf
  const gap = r.gap_vs_historical
  const max = Math.max(0.05, ...[
    r.implied_growth, r.historical_median, r.historical_mean, r.revenue_cagr, r.gdp_growth,
  ].filter(Number.isFinite))

  return (
    <section style={{
      background: '#FFFFFF',
      border: '0.5px solid #E5E7EB',
      borderRadius: 12,
      padding: '24px 28px',
    }}>
      <h3 style={{ fontSize: 16, fontWeight: 700, color: '#111827', margin: 0, marginBottom: 4 }}>
        What is the market's bet?
        <EPFLCitation source="Berk-DeMarzo Ch.9 · growing perpetuity (reverse DCF)" test="test_epfl_exam1.py::TestExam1Problem3_NPV_IRR" />
        <LearnMore section="marketsBet" />
      </h3>
      <p style={{ fontSize: 13, color: '#6B7280', lineHeight: 1.5, marginBottom: 16, maxWidth: 720 }}>
        Instead of asking <em>"what is {d.company_name} worth?"</em>, we work backwards:
        what growth rate would {d.company_name}'s free cash flow need to deliver for
        today's price to be the right answer? We solve for it numerically.
      </p>

      <div style={{ display: 'flex', gap: 16, marginBottom: 20, flexWrap: 'wrap' }}>
        <BigStat
          label="Market-implied growth"
          value={pct(r.implied_growth)}
          subtitle="required to justify today's price"
          colour="#185FA5"
        />
        <BigStat
          label="Historical median"
          value={pct(r.historical_median)}
          subtitle={`what ${d.company_name} actually delivered`}
          colour="#3B6D11"
        />
        <BigStat
          label="Gap"
          value={(gap >= 0 ? '+' : '') + (gap * 100).toFixed(1) + 'pp'}
          subtitle={gap >= 0 ? 'market wants more than history' : 'market wants less than history'}
          colour={Math.abs(gap) < 0.05 ? '#3B6D11' : Math.abs(gap) < 0.15 ? '#854D0E' : '#A32D2D'}
        />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <GrowthBar label="Implied (today's price)" value={r.implied_growth} max={max} colour="#185FA5" />
        <GrowthBar label="Historical median" value={r.historical_median} max={max} colour="#3B6D11" reference />
        <GrowthBar label="Historical mean" value={r.historical_mean} max={max} colour="#9CA3AF" />
        <GrowthBar label="Revenue CAGR" value={r.revenue_cagr} max={max} colour="#9CA3AF" />
        <GrowthBar label="GDP (long run)" value={r.gdp_growth} max={max} colour="#D1D5DB" />
      </div>

      <div style={{
        marginTop: 18, padding: '12px 14px',
        background: '#F0F9FF', borderRadius: 8,
        fontSize: 13, color: '#1E3A5F', lineHeight: 1.5,
      }}>
        {gap < -0.05
          ? `The market is pricing ${d.company_name} for growth ${pct(Math.abs(gap), 1)} below its historical pace — implying the run is slowing down. If you think it's not, the stock looks cheap.`
          : gap > 0.05
            ? `The market is pricing ${d.company_name} for growth ${pct(gap, 1)} above its historical pace — implying acceleration. You need to believe the growth is sustainable.`
            : `The market is pricing ${d.company_name} for growth approximately in line with its historical pace. The price says "keep doing what you've been doing."`}
      </div>
    </section>
  )
}

function BigStat({ label, value, subtitle, colour }) {
  return (
    <div style={{ flex: 1, minWidth: 180 }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 28, fontWeight: 800, color: colour, lineHeight: 1, marginBottom: 4 }}>
        {value}
      </div>
      <div style={{ fontSize: 11, color: '#9CA3AF', lineHeight: 1.4 }}>{subtitle}</div>
    </div>
  )
}

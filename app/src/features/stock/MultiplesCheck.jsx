/**
 * Sanity check — how does the DCF output compare to relative valuation
 * (P/E, EV/EBITDA, FCF yield)?
 */
import Term from '../../shared/Term'
import { DEFS } from '../../shared/defs'

const fmt = (v, d = 1) => v == null || !Number.isFinite(v) ? '—' : v.toFixed(d)
const pct = (v, d = 2) => v == null || !Number.isFinite(v) ? '—' : `${(v * 100).toFixed(d)}%`

const BENCHMARKS = {
  ev_ebitda: { value: 12, label: 'auto / industrial sector' },
  pe_ratio:  { value: 22, label: 'S&P 500 average' },
  fcf_yield: { value: 0.045, label: '10-yr Treasury' },
}

function MultipleCard({ label, value, benchmark, formatter, premium }) {
  return (
    <div style={{
      flex: 1, minWidth: 160,
      background: '#FAFBFC',
      border: '0.5px solid #E5E7EB',
      borderRadius: 8,
      padding: '14px 16px',
    }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 22, fontWeight: 800, color: '#111827', lineHeight: 1 }}>
        {formatter(value)}
      </div>
      <div style={{ fontSize: 11, color: '#9CA3AF', marginTop: 6 }}>
        Benchmark: {formatter(benchmark.value)} ({benchmark.label})
      </div>
      {premium && (
        <div style={{ fontSize: 10, fontWeight: 700, color: '#A32D2D', marginTop: 4 }}>
          {premium}
        </div>
      )}
    </div>
  )
}

export default function MultiplesCheck({ d }) {
  if (!d?.multiples) return null
  const m = d.multiples

  const evx = Number.isFinite(m.ev_ebitda) && m.ev_ebitda > 0
    ? `Premium ${(m.ev_ebitda / BENCHMARKS.ev_ebitda.value).toFixed(1)}× sector`
    : null
  const pex = Number.isFinite(m.pe_ratio) && m.pe_ratio > 0
    ? `Premium ${(m.pe_ratio / BENCHMARKS.pe_ratio.value).toFixed(1)}× S&P`
    : null
  const fy = Number.isFinite(m.fcf_yield) && m.fcf_yield > 0
    ? `Treasury yields ${(BENCHMARKS.fcf_yield.value / m.fcf_yield).toFixed(1)}× more`
    : null

  return (
    <section style={{
      background: '#FFFFFF',
      border: '0.5px solid #E5E7EB',
      borderRadius: 12,
      padding: '20px 24px',
    }}>
      <h3 style={{ fontSize: 14, fontWeight: 700, color: '#111827', margin: 0, marginBottom: 4 }}>
        Sanity check — multiples
      </h3>
      <p style={{ fontSize: 12, color: '#6B7280', lineHeight: 1.5, marginBottom: 14, maxWidth: 720 }}>
        Three independent metrics, cross-checking the DCF output. They don't prove the model
        right — they show whether the conclusion is corroborated by other ways of looking at the stock.
      </p>
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
        <MultipleCard
          label={<Term def={DEFS.PE}>P / E</Term>}
          value={m.pe_ratio}
          benchmark={BENCHMARKS.pe_ratio}
          formatter={v => `${fmt(v, 1)}×`}
          premium={pex}
        />
        <MultipleCard
          label={<Term def={DEFS.EVEBITDA}>EV / EBITDA</Term>}
          value={m.ev_ebitda}
          benchmark={BENCHMARKS.ev_ebitda}
          formatter={v => `${fmt(v, 1)}×`}
          premium={evx}
        />
        <MultipleCard
          label={<Term def={DEFS.FCFyield}>FCF yield</Term>}
          value={m.fcf_yield}
          benchmark={BENCHMARKS.fcf_yield}
          formatter={v => pct(v)}
          premium={fy}
        />
      </div>
    </section>
  )
}

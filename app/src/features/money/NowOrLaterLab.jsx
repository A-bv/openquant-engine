import { useEffect, useState } from 'react'
import axios from 'axios'
import DisclosureSection from '../../shared/DisclosureSection'
import EPFLCitation from '../../shared/EPFLCitation'

const PRESETS = [
  {
    label: 'Lottery / settlement',
    blurb: '$15M cash now, or $1M every year for 30 years?',
    kind: 'receive', lumpSum: 15000000, payment: 1000000, nPayments: 30, ratePct: 8, firstToday: true,
  },
  {
    label: '0% financing vs cash discount',
    blurb: 'Pay $18,000 cash, or $4,000/yr for 5 years at 0%?',
    kind: 'pay', lumpSum: 18000, payment: 4000, nPayments: 5, ratePct: 6, firstToday: false,
  },
  {
    label: 'Pension buyout',
    blurb: '$400k lump sum, or $30k every year for 25 years?',
    kind: 'receive', lumpSum: 400000, payment: 30000, nPayments: 25, ratePct: 4, firstToday: true,
  },
]

function fmt(v, cur = '$') {
  const a = Math.abs(v), s = v < 0 ? '-' : ''
  if (a >= 1e12) return `${s}${cur}${(a / 1e12).toFixed(2)}T`
  if (a >= 1e9) return `${s}${cur}${(a / 1e9).toFixed(2)}B`
  if (a >= 1e6) return `${s}${cur}${(a / 1e6).toFixed(2)}M`
  if (a >= 1e3) return `${s}${cur}${(a / 1e3).toFixed(1)}K`
  return `${s}${cur}${a.toFixed(2)}`
}

export default function NowOrLaterLab({ API }) {
  const [p, setP] = useState(PRESETS[0])
  const [lumpSum, setLump] = useState(PRESETS[0].lumpSum)
  const [payment, setPayment] = useState(PRESETS[0].payment)
  const [nPayments, setN] = useState(PRESETS[0].nPayments)
  const [ratePct, setRate] = useState(PRESETS[0].ratePct)
  const [kind, setKind] = useState(PRESETS[0].kind)
  const [firstToday, setFirstToday] = useState(PRESETS[0].firstToday)
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  const applyPreset = (preset) => {
    setP(preset)
    setLump(preset.lumpSum); setPayment(preset.payment); setN(preset.nPayments)
    setRate(preset.ratePct); setKind(preset.kind); setFirstToday(preset.firstToday)
  }

  useEffect(() => {
    const id = setTimeout(async () => {
      try {
        const res = await axios.post(`${API}/now-or-later`, {
          lump_sum: Number(lumpSum), payment: Number(payment),
          n_payments: Number(nPayments), rate: Number(ratePct) / 100,
          first_payment_today: firstToday, kind,
        })
        setData(res.data); setError(null)
      } catch (e) {
        const detail = e.response?.data?.detail
        setError((typeof detail === 'object' ? detail?.error : detail) || 'Calculation failed. Is the backend running?')
      }
    }, 250)
    return () => clearTimeout(id)
  }, [API, lumpSum, payment, nPayments, ratePct, kind, firstToday])

  const nowLabel = kind === 'pay' ? 'Pay cash now' : 'Take it now'
  const laterLabel = "Spread it out (today's value)"
  const maxBar = data ? Math.max(data.lump_sum, data.stream_pv) : 1

  return (
    <>
      <section className="card intro-card">
        <div className="eyebrow">Everyday money</div>
        <h1 className="page-title">Take it now, or spread it out?</h1>
        <p className="page-copy">
          Money later is worth less than money today. Pick any "lump sum now
          versus payments over time" choice, like a lottery, a settlement, 0%
          financing, or a pension buyout, and see which is really worth more,
          plus the one assumption that decides it.
        </p>
        <p className="intro-proof">
          Works for everyone · no account, no ticker · the time value of money
        </p>

        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', margin: '14px 0 6px' }}>
          {PRESETS.map(preset => (
            <button key={preset.label} onClick={() => applyPreset(preset)}
              style={{
                fontSize: 12, padding: '6px 12px', borderRadius: 8, cursor: 'pointer', color: '#374151',
                border: p.label === preset.label ? '2px solid #185FA5' : '0.5px solid #D1D5DB',
                background: p.label === preset.label ? '#EFF6FF' : '#fff',
              }}>
              {preset.label}
            </button>
          ))}
        </div>
        <p style={{ fontSize: 12, color: '#9CA3AF', margin: '0 0 14px' }}>{p.blurb}</p>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
          <label style={{ fontSize: 12, color: '#6B7280' }}>
            {kind === 'pay' ? 'Cash price now' : 'Amount offered now'}
            <input type="number" value={lumpSum} onChange={e => setLump(e.target.value)}
              style={inp} />
            <span style={{ display: 'block', fontSize: 11, color: '#9CA3AF', marginTop: 3 }}>
              {lumpSum ? fmt(Number(lumpSum), '$') : ''}
            </span>
          </label>
          <label style={{ fontSize: 12, color: '#6B7280' }}>
            Each payment
            <input type="number" value={payment} onChange={e => setPayment(e.target.value)} style={inp} />
            <span style={{ display: 'block', fontSize: 11, color: '#9CA3AF', marginTop: 3 }}>
              {payment ? fmt(Number(payment), '$') : ''}
            </span>
          </label>
          <label style={{ fontSize: 12, color: '#6B7280' }}>
            Number of payments
            <input type="number" value={nPayments} onChange={e => setN(e.target.value)} style={inp} />
          </label>
        </div>

        <div style={{ marginTop: 16 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, color: '#374151' }}>
            <span>How much is your money worth to you? <strong>{Number(ratePct).toFixed(1)}%/yr</strong></span>
            <span style={{ fontSize: 11, color: '#9CA3AF' }}>the assumption that decides it</span>
          </div>
          <input type="range" min="0" max="15" step="0.5" value={ratePct}
            onChange={e => setRate(e.target.value)} style={{ width: '100%', marginTop: 4 }} />
        </div>

        <div style={{ marginTop: 12, display: 'flex', gap: 6 }}>
          {['receive', 'pay'].map(k => (
            <button key={k} onClick={() => setKind(k)}
              style={{
                fontSize: 12, padding: '4px 10px', borderRadius: 6, cursor: 'pointer',
                border: '0.5px solid #D1D5DB', color: kind === k ? '#fff' : '#6B7280',
                background: kind === k ? '#374151' : '#fff',
              }}>
              {k === 'receive' ? "I'm receiving this money" : "I'm paying this money"}
            </button>
          ))}
        </div>
      </section>

      {error && (
        <div style={{ background: '#FCEBEB', border: '0.5px solid #F5B5B5', borderRadius: 8, padding: '14px 18px', color: '#A32D2D', fontSize: 13 }}>
          {error}
        </div>
      )}

      {data && !error && (
        <>
          <section className="card">
            <div style={{ fontSize: 30, fontWeight: 700, color: '#111827', marginBottom: 14 }}>
              {data.summary_lines[0]}
            </div>

            {/* now vs later comparison bars */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 16 }}>
              <Bar label={nowLabel} value={data.lump_sum} max={maxBar} cur={data.currency}
                highlight={data.winner === 'now'} />
              <Bar label={laterLabel} value={data.stream_pv} max={maxBar} cur={data.currency}
                highlight={data.winner === 'later'} sub={`paper total ${fmt(data.nominal_total, data.currency)}`} />
            </div>

            {data.summary_lines.slice(1, 3).map((line, i) => (
              <p key={i} style={{ fontSize: 14, color: '#374151', margin: '2px 0' }}>{line}</p>
            ))}

            <div style={{ marginTop: 12, padding: '10px 14px', background: '#F8FAFC', borderLeft: '3px solid #185FA5', borderRadius: '0 8px 8px 0', fontSize: 13, color: '#374151' }}>
              {data.summary_lines[3]}
            </div>
          </section>

          <DisclosureSection
            eyebrow="Show your work"
            title="The present-value calculation & break-even rate"
            summary="Open this to see how each payment is discounted to today, the rate at which the answer flips, and the source it is checked against."
          >
            <h3 style={{ fontSize: 14, fontWeight: 700, color: '#111827', margin: '0 0 8px' }}>
              Present value, step by step
              <EPFLCitation source="Berk-DeMarzo Ch.4 · EPFL formula sheet p.1 · PFEM slides 17-20" test="test_money.py::TestPFEMLottery" />
            </h3>
            <pre style={{ fontSize: 12, color: '#374151', background: '#F8FAFC', padding: 14, borderRadius: 8, overflowX: 'auto', lineHeight: 1.5, fontFamily: 'ui-monospace, monospace' }}>
              {data.detail_lines.join('\n')}
            </pre>
          </DisclosureSection>
        </>
      )}
    </>
  )
}

const inp = {
  width: '100%', marginTop: 4, padding: '8px 10px', fontSize: 14,
  borderRadius: 8, border: '0.5px solid #D1D5DB', fontFamily: 'inherit',
}

function Bar({ label, value, max, cur, highlight, sub }) {
  const pct = max > 0 ? Math.max(2, (value / max) * 100) : 0
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 3 }}>
        <span style={{ color: highlight ? '#185FA5' : '#6B7280', fontWeight: highlight ? 700 : 400 }}>{label}</span>
        <span style={{ color: '#111827', fontWeight: 700 }}>{fmt(value, cur)}</span>
      </div>
      <div style={{ height: 22, background: '#F1F5F9', borderRadius: 4, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: highlight ? '#185FA5' : '#CFE3F7' }} />
      </div>
      {sub && <div style={{ fontSize: 11, color: '#9CA3AF', marginTop: 2 }}>{sub}</div>}
    </div>
  )
}

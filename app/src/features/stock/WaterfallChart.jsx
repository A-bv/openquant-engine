// Simple custom waterfall built with divs — Recharts waterfall support is
// limited, so we render a proportional bar layout ourselves.

const fmtB = v => {
  if (v == null || !Number.isFinite(v)) return '—'
  const b = Math.abs(v) / 1e9
  const sign = v < 0 ? '-' : ''
  return `${sign}$${b >= 100 ? b.toFixed(0) : b.toFixed(1)}B`
}

const COLOURS = {
  pv_fcf:    { bar: '#185FA5', bg: '#E6F1FB', text: '#185FA5' },
  pv_tv:     { bar: '#7C3AED', bg: '#EDE9FE', text: '#6D28D9' },
  debt:      { bar: '#A32D2D', bg: '#FCEBEB', text: '#A32D2D' },
  equity:    { bar: '#3B6D11', bg: '#EAF3DE', text: '#3B6D11' },
}

function Bar({ label, value, sublabel, colour, pct }) {
  const c = COLOURS[colour]
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, flex: 1, minWidth: 0 }}>
      <div style={{
        background: c.bg,
        border: `0.5px solid ${c.bar}`,
        borderRadius: 8,
        padding: '12px 14px',
        textAlign: 'center',
      }}>
        <div style={{ fontSize: 10, fontWeight: 600, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
          {label}
        </div>
        <div style={{ fontSize: 20, fontWeight: 700, color: c.text, lineHeight: 1 }}>
          {fmtB(value)}
        </div>
        {pct != null && (
          <div style={{ fontSize: 10, color: '#9CA3AF', marginTop: 4 }}>
            {(pct * 100).toFixed(0)}% of EV
          </div>
        )}
      </div>
      {sublabel && (
        <div style={{ fontSize: 11, color: '#9CA3AF', textAlign: 'center', lineHeight: 1.3 }}>
          {sublabel}
        </div>
      )}
    </div>
  )
}

function Arrow() {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      color: '#D1D5DB',
      fontSize: 18,
      flexShrink: 0,
      paddingBottom: 24,
    }}>
      →
    </div>
  )
}

export default function WaterfallChart({ dcfBase, netDebt, companyName }) {
  if (!dcfBase) return null

  // Reconstruct components from the base scenario. Treat null/non-finite
  // as missing so arithmetic doesn't poison the chart with NaN bars.
  const pvFCFs = Number.isFinite(dcfBase.pv_fcfs) ? dcfBase.pv_fcfs : 0
  const pvTV   = Number.isFinite(dcfBase.pv_tv)   ? dcfBase.pv_tv   : 0
  const netDebtSafe = Number.isFinite(netDebt) ? netDebt : 0
  const ev     = pvFCFs + pvTV
  const equity = ev - netDebtSafe
  const tvPct  = ev > 0 ? pvTV / ev : null
  const netCash = netDebtSafe < 0
  const ivPerShare = Number.isFinite(dcfBase.iv) ? dcfBase.iv.toFixed(2) : '—'

  return (
    <div>
      <div style={{ fontSize: 13, fontWeight: 600, color: '#111827', marginBottom: 12 }}>
        {companyName} — Base Case Value Build-Up
      </div>
      <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, minWidth: 480 }}>
        <Bar
          label="PV of FCFs (Yrs 1–10)"
          value={pvFCFs}
          colour="pv_fcf"
          sublabel="Sum of discounted cash flows"
        />
        <Arrow />
        <Bar
          label="PV of Terminal Value"
          value={pvTV}
          colour="pv_tv"
          pct={tvPct}
          sublabel="Discounted perpetuity beyond yr 10"
        />
        <Arrow />
        <Bar
          label={netCash ? 'Plus: Net Cash' : 'Less: Net Debt'}
          value={netDebtSafe}
          colour="debt"
          sublabel={netCash ? 'Cash exceeds total debt' : 'Total debt minus cash'}
        />
        <Arrow />
        <Bar
          label="Equity Value (Base IV)"
          value={equity}
          colour="equity"
          sublabel={`$${ivPerShare} per share`}
        />
      </div>
      </div>
      <div style={{ fontSize: 11, color: '#9CA3AF', marginTop: 10 }}>
        Enterprise Value = PV of FCFs + PV of Terminal Value = {fmtB(ev)}.
        {tvPct != null
          ? ` Terminal value accounts for ${(tvPct * 100).toFixed(0)}% of EV — the most uncertain assumption.`
          : ' Enterprise value is non-positive — terminal value share is undefined.'}
      </div>
    </div>
  )
}

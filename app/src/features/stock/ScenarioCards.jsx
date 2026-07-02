import { useIsMobile } from '../../shared/useIsMobile'

const pct = (v, sign = true) => {
  if (v == null) return '—'
  const s = sign && v > 0 ? '+' : ''
  return `${s}${(v * 100).toFixed(1)}%`
}
const usd = v => v == null ? '—' : `$${v.toFixed(2)}`

const configs = {
  conservative: {
    label: 'Conservative',
    accent: '#A32D2D',
    bg: '#FCEBEB',
    borderColor: '#F5B5B5',
    description: 'FCF grows at 70% of historical median — pessimistic case',
  },
  base: {
    label: 'Base',
    accent: '#185FA5',
    bg: '#E6F1FB',
    borderColor: '#93C5FD',
    description: 'FCF continues at historical median — central case',
  },
  optimistic: {
    label: 'Optimistic',
    accent: '#3B6D11',
    bg: '#EAF3DE',
    borderColor: '#B5D98A',
    description: 'FCF grows at 130% of historical median — optimistic case',
  },
}

function ScenarioCard({ name, scenario, currentPrice }) {
  const cfg = configs[name]
  // null/non-finite IV or price → tri-state "unknown" instead of silently
  // falling into the below-price (red) branch.
  const haveCompare = Number.isFinite(scenario?.iv) && Number.isFinite(currentPrice)
  const above = haveCompare ? scenario.iv > currentPrice : null
  return (
    <div style={{
      flex: 1,
      minWidth: 0,
      background: '#FFFFFF',
      border: `0.5px solid ${cfg.borderColor}`,
      borderRadius: 12,
      padding: '16px 14px',
      display: 'flex',
      flexDirection: 'column',
      gap: 10,
    }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: cfg.accent, textTransform: 'uppercase', letterSpacing: '0.07em' }}>
        {cfg.label}
      </div>
      <div>
        <div style={{ fontSize: 22, fontWeight: 700, color: cfg.accent, lineHeight: 1 }}>
          {usd(scenario.iv)}
        </div>
        <div style={{
          marginTop: 6,
          display: 'inline-block',
          fontSize: 11,
          fontWeight: 600,
          color: above == null ? '#6B7280' : (above ? '#3B6D11' : '#A32D2D'),
          background: above == null ? '#F3F4F6' : (above ? '#EAF3DE' : '#FCEBEB'),
          borderRadius: 4,
          padding: '2px 6px',
          whiteSpace: 'nowrap',
        }}>
          {pct(scenario.upside)} vs price
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 6, fontSize: 11 }}>
          <span style={{ color: '#6B7280', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>FCF growth</span>
          <span style={{ color: '#111827', fontWeight: 600, flexShrink: 0, whiteSpace: 'nowrap' }}>{pct(scenario.growth, false)}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 6, fontSize: 11 }}>
          <span style={{ color: '#6B7280', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 }}>TV share</span>
          <span style={{ color: '#111827', fontWeight: 600, flexShrink: 0, whiteSpace: 'nowrap' }}>{pct(scenario.tv_pct, false)}</span>
        </div>
      </div>
      <div style={{ fontSize: 10, color: '#9CA3AF', lineHeight: 1.4 }}>
        {cfg.description}
      </div>
    </div>
  )
}

export default function ScenarioCards({ dcf, currentPrice }) {
  const isMobile = useIsMobile()
  return (
    <div style={{ display: 'flex', flexDirection: isMobile ? 'column' : 'row', gap: 10 }}>
      {['conservative', 'base', 'optimistic'].map(name => (
        <ScenarioCard key={name} name={name} scenario={dcf[name]} currentPrice={currentPrice} />
      ))}
    </div>
  )
}

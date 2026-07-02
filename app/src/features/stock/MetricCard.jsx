const colours = {
  positive: { text: '#3B6D11', bg: '#EAF3DE' },
  negative: { text: '#A32D2D', bg: '#FCEBEB' },
  neutral:  { text: '#185FA5', bg: '#E6F1FB' },
  default:  { text: '#111827', bg: '#FFFFFF' },
}

export default function MetricCard({ label, value, explanation, colour = 'default' }) {
  const c = colours[colour] || colours.default
  return (
    <div style={{
      background: '#FFFFFF',
      border: '0.5px solid #E5E7EB',
      borderRadius: 12,
      padding: '20px 24px',
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
    }}>
      <div style={{ fontSize: 10, fontWeight: 600, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
        {label}
      </div>
      <div style={{ fontSize: 28, fontWeight: 700, color: c.text, lineHeight: 1.1 }}>
        {value}
      </div>
      {explanation && (
        <div style={{ fontSize: 12, color: '#6B7280', lineHeight: 1.4 }}>
          {explanation}
        </div>
      )}
    </div>
  )
}

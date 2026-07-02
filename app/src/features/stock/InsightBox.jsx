const schemes = {
  green: { text: '#3B6D11', bg: '#EAF3DE', border: '#B5D98A' },
  red:   { text: '#A32D2D', bg: '#FCEBEB', border: '#F5B5B5' },
  blue:  { text: '#185FA5', bg: '#E6F1FB', border: '#93C5FD' },
}

export default function InsightBox({ children, colour = 'blue' }) {
  const s = schemes[colour] || schemes.blue
  return (
    <div style={{
      background: s.bg,
      border: `0.5px solid ${s.border}`,
      borderRadius: 8,
      padding: '14px 18px',
      color: s.text,
      fontSize: 13,
      lineHeight: 1.55,
    }}>
      {children}
    </div>
  )
}

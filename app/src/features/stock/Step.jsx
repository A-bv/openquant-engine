export default function Step({ number, title, why, children }) {
  return (
    <section style={{
      background: '#FFFFFF',
      border: '0.5px solid #E5E7EB',
      borderRadius: 12,
      padding: '32px 36px',
      display: 'flex',
      flexDirection: 'column',
      gap: 20,
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
        <div style={{
          minWidth: 32,
          height: 32,
          borderRadius: '50%',
          background: '#E6F1FB',
          color: '#185FA5',
          fontSize: 13,
          fontWeight: 700,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
          marginTop: 2,
        }}>
          {number}
        </div>
        <div>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: '#111827', lineHeight: 1.3, marginBottom: 6 }}>
            {title}
          </h2>
          <p style={{ fontSize: 12, color: '#6B7280', lineHeight: 1.55 }}>
            {why}
          </p>
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {children}
      </div>
    </section>
  )
}

const tone = {
  green: { bg: '#ECFDF3', border: '#B7E4C7', text: '#245B35', label: 'GREEN' },
  amber: { bg: '#FFFBEB', border: '#FDE68A', text: '#854D0E', label: 'AMBER' },
  red: { bg: '#FCEBEB', border: '#F5B5B5', text: '#A32D2D', label: 'RED' },
}

function RatingPill({ rating }) {
  const t = tone[rating] || tone.amber
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      borderRadius: 999,
      padding: '3px 8px',
      fontSize: 10,
      fontWeight: 800,
      color: t.text,
      background: t.bg,
      border: `0.5px solid ${t.border}`,
      letterSpacing: '0.04em',
    }}>
      {t.label}
    </span>
  )
}

export default function ModelQualityPanel({ d }) {
  if (!d?.diagnostic && !d?.audit && !d?.red_flags) return null

  const diagnostic = d.diagnostic
  const flags = d.red_flags?.flags || []
  const formulas = d.audit?.formula_references || []
  const auditSummary = d.audit?.summary || {}
  const flaggedDims = (diagnostic?.dimensions || []).filter(x => x.rating !== 'green')

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {diagnostic && (
        <section style={{
          background: '#FFFFFF',
          border: '0.5px solid #E5E7EB',
          borderRadius: 10,
          padding: '14px 16px',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
            <RatingPill rating={diagnostic.rating} />
            <div style={{ fontSize: 13, fontWeight: 800, color: '#111827' }}>
              Assumption diagnostic
            </div>
          </div>
          <p style={{ fontSize: 12, color: '#4B5563', lineHeight: 1.55, margin: 0, marginBottom: 8 }}>
            {diagnostic.summary}
          </p>
          <p style={{ fontSize: 11, color: '#6B7280', lineHeight: 1.5, margin: 0 }}>
            {diagnostic.disclaimer}
          </p>
          {flaggedDims.length > 0 && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: 8, marginTop: 12 }}>
              {flaggedDims.map(dim => (
                <div key={dim.name} style={{
                  border: '0.5px solid #E5E7EB',
                  borderRadius: 8,
                  padding: '10px 12px',
                  background: '#FAFBFC',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 5 }}>
                    <strong style={{ fontSize: 12, color: '#111827' }}>{dim.name}</strong>
                    <RatingPill rating={dim.rating} />
                  </div>
                  <div style={{ fontSize: 11, color: '#6B7280', lineHeight: 1.45 }}>
                    {dim.message}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {flags.length > 0 && (
        <section style={{
          background: '#FFF7ED',
          border: '0.5px solid #FED7AA',
          borderRadius: 10,
          padding: '14px 16px',
        }}>
          <div style={{ fontSize: 13, fontWeight: 800, color: '#9A3412', marginBottom: 8 }}>
            Main caveats before reading the numbers
          </div>
          <ul style={{ margin: 0, paddingLeft: 18, color: '#7C2D12' }}>
            {flags.map(flag => (
              <li key={flag} style={{ fontSize: 12, lineHeight: 1.5, marginBottom: 5 }}>
                {flag}
              </li>
            ))}
          </ul>
        </section>
      )}

      {formulas.length > 0 && (
        <section style={{
          background: '#F8FAFC',
          border: '0.5px solid #E2E8F0',
          borderRadius: 10,
          padding: '14px 16px',
        }}>
          <div style={{ fontSize: 13, fontWeight: 800, color: '#111827', marginBottom: 8 }}>
            Course formula trace
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 8 }}>
            {formulas.slice(0, 6).map(item => (
              <div key={item.name} style={{
                background: '#FFFFFF',
                border: '0.5px solid #E5E7EB',
                borderRadius: 8,
                padding: '10px 12px',
              }}>
                <div style={{ fontSize: 12, fontWeight: 800, color: '#111827', marginBottom: 4 }}>
                  {item.name}
                </div>
                <div style={{ fontSize: 11, color: '#185FA5', lineHeight: 1.4, marginBottom: 4 }}>
                  {item.formula}
                </div>
                <div style={{ fontSize: 10, color: '#6B7280', lineHeight: 1.4 }}>
                  {item.source}
                </div>
              </div>
            ))}
          </div>
          {auditSummary.Generated && (
            <div style={{ fontSize: 10, color: '#9CA3AF', marginTop: 10 }}>
              Generated: {auditSummary.Generated} · Data: {auditSummary['Financial Data']} / {auditSummary['Price Data']}
            </div>
          )}
        </section>
      )}
    </div>
  )
}

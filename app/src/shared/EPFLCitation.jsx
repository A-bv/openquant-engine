/**
 * Small inline badge citing the EPFL source of a formula.
 * Renders as a tiny superscript-style pill that appears next to each number.
 *
 * Example: <EPFLCitation source="EPFL FS p.4 · Berk-DeMarzo Ch.15.5" />
 */
export default function EPFLCitation({ source, test }) {
  if (!source && !test) return null
  return (
    <span
      title={[source, test && `verified by ${test}`].filter(Boolean).join(' · ')}
      style={{
        display: 'inline-block',
        marginLeft: 6,
        padding: '1px 6px',
        fontSize: 10,
        fontWeight: 600,
        color: '#6B7280',
        background: '#F3F4F6',
        border: '0.5px solid #E5E7EB',
        borderRadius: 999,
        verticalAlign: 'middle',
        cursor: 'help',
        letterSpacing: '0.02em',
      }}
    >
      B&D
    </span>
  )
}

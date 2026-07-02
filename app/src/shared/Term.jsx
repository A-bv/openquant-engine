/**
 * Inline jargon tooltip. Wraps a term in a dotted-underline span with a
 * native browser tooltip showing the definition. Beginners can hover any
 * underlined term to learn what it means; experts ignore the styling.
 *
 * Usage:
 *   <Term def="Weighted Average Cost of Capital — the discount rate.">WACC</Term>
 */
export default function Term({ children, def }) {
  return (
    <abbr title={def} style={{
      textDecoration: 'underline dotted',
      textDecorationColor: '#9CA3AF',
      textUnderlineOffset: 3,
      cursor: 'help',
    }}>
      {children}
    </abbr>
  )
}

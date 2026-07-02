/**
 * Per-stock conclusion + take-aways.
 *
 * Sits at the end of the analysis. Three parts:
 *   1. Narrative summary (3 sentences in plain English)
 *   2. Three numbered take-aways the user can repeat in a conversation
 *   3. Three concrete next actions (no dead-end pages)
 *
 * The point is to send the user away with insight, not just data.
 */

const pct = (v, d = 1) => v == null || !Number.isFinite(v) ? '—' : `${(v * 100).toFixed(d)}%`
const fmt$ = (v) => v == null || !Number.isFinite(v) ? '—' : `$${v.toFixed(0)}`

const PEER_TICKERS = ['AAPL', 'MSFT', 'TSLA', 'NVDA', 'GOOGL', 'AMZN', 'META', 'ACN', 'JPM', 'KO']

export default function Conclusion({ d, onAnalyse }) {
  if (!d || !d.is_suitable || !d.dcf || !d.reverse_dcf) return null

  const p = d.current_price
  const ivBase = d.dcf?.base?.iv
  const haveValues = Number.isFinite(p) && Number.isFinite(ivBase)

  // Model gap bucket, not an investment recommendation.
  const upside = haveValues ? (ivBase / p - 1) : null
  const modelGap = upside == null ? null
    : upside > 0.20 ? 'model value above price'
    : upside < -0.20 ? 'model value below price'
    : 'model value near price'

  // Three sentences in plain English
  const implied = d.reverse_dcf?.implied_growth
  const historical = d.reverse_dcf?.historical_median
  const gap = d.reverse_dcf?.gap_vs_historical

  const summary = haveValues && Number.isFinite(implied) ? (
    <>
      <p style={{ marginBottom: 8 }}>
        At <strong>{fmt$(p)}</strong>, the market is pricing {d.company_name} as if it
        will grow free cash flow at <strong>{pct(implied)}</strong>/year for the next decade.
        Its historical median growth has been <strong>{pct(historical)}</strong>/year — a
        gap of <strong>{(gap != null ? (gap >= 0 ? '+' : '') + (gap * 100).toFixed(1) : '—')}pp</strong>.
      </p>
      <p style={{ marginBottom: 8 }}>
        Under our textbook DCF model, the base-case value is <strong>{fmt$(ivBase)}</strong>{' '}
        — {modelGap === 'model value above price' ? <>about <strong>{pct(upside)}</strong> above today's price.</>
            : modelGap === 'model value below price' ? <>about <strong>{pct(Math.abs(upside))}</strong> below today's price.</>
            : <>roughly in line with the market.</>}
      </p>
      <p>
        But our model has had limited predictive power historically
        (R² = 0.04 across 50 stocks 2014–2024). Treat this as <strong>one
        defensible framework</strong> — not the answer.
      </p>
    </>
  ) : (
    <p>
      Some data was missing or the model couldn't fully run for this stock.
      Check the warnings above.
    </p>
  )

  // Three take-aways
  const takeaways = []
  if (haveValues && Number.isFinite(implied) && Number.isFinite(historical)) {
    takeaways.push({
      label: gap > 0.05
        ? `The market is asking for ${pct(Math.abs(gap))} MORE growth than ${d.company_name} has historically delivered.`
        : gap < -0.05
          ? `The market is pricing for ${pct(Math.abs(gap))} LESS growth than ${d.company_name} has historically delivered.`
          : `The market is pricing growth roughly in line with ${d.company_name}'s historical pace.`,
      detail: 'This is the actual investment question — not "what is it worth" but "do you believe this growth trajectory continues."',
    })
  }
  takeaways.push({
      label: modelGap === 'model value below price'
      ? `The model value is below the market price. To justify today's price, at least one assumption above needs to be too conservative.`
      : modelGap === 'model value above price'
        ? `The model value is above the market price. To rely on that gap, you need to believe the growth and WACC assumptions are defensible.`
        : `The model value is near the market price, meaning the market and model assumptions are broadly similar.`,
    detail: 'No model can tell you the future. It can only make explicit what belief the market price already contains.',
  })
  takeaways.push({
    label: 'The strongest caution in this report is calibration: R² = 0.04 means even when the math is right, the stock-return signal has limited predictive power.',
    detail: "That's not a flaw of this tool — it's a property of DCF valuation in general. The advantage of OpenQuant is that we tell you, instead of pretending otherwise.",
  })

  return (
    <section style={{
      background: '#FFFFFF',
      border: '0.5px solid #E5E7EB',
      borderRadius: 12,
      padding: '26px 32px',
    }}>
      {/* Heading */}
      <h3 style={{ fontSize: 18, fontWeight: 800, color: '#111827', margin: 0, marginBottom: 12, letterSpacing: '-0.01em' }}>
        What you learned about {d.company_name}
      </h3>

      {/* Summary */}
      <div style={{ fontSize: 14, color: '#374151', lineHeight: 1.65, marginBottom: 22, maxWidth: 720 }}>
        {summary}
      </div>

      {/* Take-aways */}
      <div style={{
        background: '#FAFBFC',
        border: '0.5px solid #E5E7EB',
        borderRadius: 10,
        padding: '18px 20px',
        marginBottom: 22,
      }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 12 }}>
          Three take-aways
        </div>
        <ol style={{ paddingLeft: 22, margin: 0, color: '#111827' }}>
          {takeaways.map((t, i) => (
            <li key={i} style={{ marginBottom: 14, fontSize: 13, lineHeight: 1.55 }}>
              <div style={{ fontWeight: 600 }}>{t.label}</div>
              <div style={{ fontSize: 12, color: '#6B7280', marginTop: 4 }}>{t.detail}</div>
            </li>
          ))}
        </ol>
      </div>

      {/* Actions */}
      <div style={{ fontSize: 11, fontWeight: 700, color: '#6B7280', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 10 }}>
        What to do next
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>

        {/* Try another ticker */}
        <div style={{
          background: '#F0F9FF',
          border: '0.5px solid #BAE6FD',
          borderRadius: 8,
          padding: '12px 14px',
        }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#0C4A6E', marginBottom: 6 }}>
            → Compare with another stock
          </div>
          <div style={{ fontSize: 12, color: '#075985', marginBottom: 8 }}>
            See how the model behaves on a different profile.
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {PEER_TICKERS
              .filter(t => t !== d.ticker)
              .slice(0, 6)
              .map(t => (
                <button
                  key={t}
                  onClick={() => onAnalyse && onAnalyse(t)}
                  style={{
                    fontSize: 11,
                    fontFamily: 'inherit',
                    fontWeight: 600,
                    color: '#0C4A6E',
                    background: '#FFFFFF',
                    border: '0.5px solid #BAE6FD',
                    borderRadius: 999,
                    padding: '4px 10px',
                    cursor: 'pointer',
                    letterSpacing: '0.02em',
                  }}
                >
                  {t}
                </button>
              ))}
          </div>
        </div>

        {/* Override assumptions */}
        <div style={{
          background: '#FEFCE8',
          border: '0.5px solid #FDE68A',
          borderRadius: 8,
          padding: '12px 14px',
        }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#854D0E', marginBottom: 4 }}>
            → Try your own assumptions
          </div>
          <div style={{ fontSize: 12, color: '#854D0E', lineHeight: 1.5 }}>
            Don't believe our β or WACC? Scroll up to <em>"Try your own assumptions"</em> —
            move any slider and watch the intrinsic value recompute live.
          </div>
        </div>

        {/* Backtest summary */}
        <div style={{
          background: '#F5F3FF',
          border: '0.5px solid #DDD6FE',
          borderRadius: 8,
          padding: '12px 14px',
        }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#5B21B6', marginBottom: 4 }}>
            → Understand the model's track record
          </div>
          <div style={{ fontSize: 12, color: '#5B21B6', lineHeight: 1.5 }}>
            The reliability panel above shows the main 2014-2024 backtest result:
            the formulas are tested, but the stock-valuation signal is not yet
            calibrated as a reliable return predictor.
          </div>
        </div>
      </div>

      {/* Signature */}
      <div style={{
        marginTop: 18, paddingTop: 14,
        borderTop: '0.5px solid #F3F4F6',
        fontSize: 11, color: '#9CA3AF',
        letterSpacing: '0.04em', textAlign: 'center',
      }}>
        Theory. Reality. You decide.
      </div>
    </section>
  )
}

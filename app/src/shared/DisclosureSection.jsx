import { useState } from 'react'

export default function DisclosureSection({
  title,
  eyebrow,
  summary,
  children,
  defaultOpen = false,
}) {
  const [open, setOpen] = useState(defaultOpen)

  return (
    <section className="card disclosure">
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        aria-expanded={open}
        className="disclosure-button"
      >
        <span>
          {eyebrow && (
            <span className="eyebrow" style={{ display: 'block', marginBottom: 5 }}>
              {eyebrow}
            </span>
          )}
          <span className="disclosure-title">
            {title}
          </span>
          {summary && (
            <span className="disclosure-summary">
              {summary}
            </span>
          )}
        </span>
        <span className="disclosure-icon">
          {open ? '-' : '+'}
        </span>
      </button>

      {open && (
        <div className="disclosure-body">
          {children}
        </div>
      )}
    </section>
  )
}

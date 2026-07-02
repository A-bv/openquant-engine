/**
 * Global Glossary drawer — a slide-out side panel listing every jargon
 * term used on the page, with plain-English definitions and textbook
 * citations.
 *
 * Accessible from the header. Closeable via the "✕" button, the
 * backdrop click, or the Escape key. Keeps the page flow clean by
 * default; users can dive into definitions on demand.
 */

import { useEffect } from 'react'
import { GLOSSARY } from './explanations'

export default function Glossary({ open, onClose }) {
  // Close on Escape
  useEffect(() => {
    if (!open) return
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <>
      {/* backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0,
          background: 'rgba(15, 23, 42, 0.45)',
          zIndex: 50,
        }}
      />
      {/* drawer */}
      <aside style={{
        position: 'fixed',
        top: 0, right: 0, bottom: 0,
        width: 'min(440px, 92vw)',
        background: '#FFFFFF',
        zIndex: 60,
        overflowY: 'auto',
        boxShadow: '-8px 0 24px rgba(0,0,0,0.12)',
        display: 'flex',
        flexDirection: 'column',
      }}>
        {/* header */}
        <div style={{
          position: 'sticky', top: 0,
          background: '#FFFFFF',
          padding: '16px 22px',
          borderBottom: '0.5px solid #E5E7EB',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 800, color: '#111827' }}>
              Glossary
            </div>
            <div style={{ fontSize: 11, color: '#6B7280', marginTop: 2 }}>
              Every term used on this page, in plain English.
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close glossary"
            style={{
              fontSize: 18,
              color: '#6B7280',
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              padding: 4,
              lineHeight: 1,
            }}
          >
            ✕
          </button>
        </div>

        {/* entries */}
        <div style={{ padding: '8px 22px 24px', flex: 1 }}>
          {GLOSSARY.map((entry, i) => (
            <div key={i} style={{
              padding: '14px 0',
              borderBottom: i < GLOSSARY.length - 1 ? '0.5px solid #F3F4F6' : 'none',
            }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
                <span style={{ fontSize: 14, fontWeight: 700, color: '#111827' }}>
                  {entry.term}
                </span>
                {entry.short && entry.short !== entry.term && (
                  <span style={{ fontSize: 11, color: '#9CA3AF' }}>· {entry.short}</span>
                )}
                {entry.chapter && (
                  <span style={{
                    marginLeft: 'auto',
                    fontSize: 10,
                    fontWeight: 600,
                    color: '#6B7280',
                    background: '#F3F4F6',
                    padding: '2px 6px',
                    borderRadius: 999,
                  }}>
                    B&D {entry.chapter}
                  </span>
                )}
              </div>
              <div style={{ fontSize: 12, color: '#4B5563', lineHeight: 1.55 }}>
                {entry.def}
              </div>
            </div>
          ))}
        </div>

        {/* footer */}
        <div style={{
          padding: '14px 22px',
          borderTop: '0.5px solid #F3F4F6',
          fontSize: 11,
          color: '#9CA3AF',
          textAlign: 'center',
          letterSpacing: '0.04em',
        }}>
          All definitions sourced from Berk &amp; DeMarzo, <em>Corporate Finance</em> 2nd ed.
        </div>
      </aside>
    </>
  )
}

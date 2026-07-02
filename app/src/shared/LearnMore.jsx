/**
 * Inline "Learn more" expandable for each section.
 *
 * Visually subtle: a small text link in the section header that, when
 * clicked, expands a soft-background block under the title with plain-
 * English explanation paragraphs.
 *
 * Default state is COLLAPSED — keeps the page flow clean as the user
 * specified. Users opt into depth on demand, per section.
 *
 * Usage:
 *   <SectionHeader>
 *     <h3>Section title</h3>
 *     <LearnMore section="marketsBet" />
 *   </SectionHeader>
 */

import { useState } from 'react'
import { SECTION_EXPLANATIONS } from './explanations'

export default function LearnMore({ section }) {
  const [open, setOpen] = useState(false)
  const content = SECTION_EXPLANATIONS[section]
  if (!content) return null

  return (
    <>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          fontSize: 11,
          fontWeight: 600,
          color: open ? '#6B7280' : '#185FA5',
          background: 'none',
          border: 'none',
          padding: 0,
          cursor: 'pointer',
          fontFamily: 'inherit',
          letterSpacing: '0.02em',
          marginLeft: 10,
        }}
      >
        {open ? '× Close' : 'Learn more ›'}
      </button>

      {open && (
        <div style={{
          marginTop: 12,
          padding: '14px 18px',
          background: '#F8FAFC',
          borderLeft: '3px solid #93C5FD',
          borderRadius: '0 8px 8px 0',
          fontSize: 13,
          color: '#374151',
          lineHeight: 1.65,
        }}>
          <div style={{
            fontSize: 11,
            fontWeight: 700,
            color: '#6B7280',
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            marginBottom: 8,
          }}>
            {content.title}
          </div>
          {content.body.map((para, i) => (
            <p key={i} style={{
              margin: 0,
              marginBottom: i < content.body.length - 1 ? 10 : 0,
            }}>
              {para}
            </p>
          ))}
        </div>
      )}
    </>
  )
}

'use client'

import { useState } from 'react'
import { personas } from '@/lib/personas'
import PersonaCard from '@/components/alidade/personas/PersonaCard'
import PersonaAccordion from '@/components/alidade/personas/PersonaAccordion'
import PersonaDrawer from '@/components/alidade/personas/PersonaDrawer'

const row1 = personas.filter(p => p.row === 1)
const row2 = personas.filter(p => p.row === 2)
const drawerPersonas = personas.filter(p => p.row === 'drawer')

function BottomIllustration() {
  return (
    <svg viewBox="0 0 300 80" width="100%" height="80" style={{ display: 'block' }}>
      <rect width="300" height="80" fill="#ede9e0" />
      {/* Mondrian divider */}
      <rect x="145" y="0" width="10" height="80" fill="#00358e" />
      <rect x="145" y="50" width="10" height="30" fill="#c8102e" />
      {/* Figure left */}
      <circle cx="100" cy="35" r="3" fill="#2a2a2a" />
      <line x1="100" y1="38" x2="100" y2="52" stroke="#2a2a2a" strokeWidth="1.5" />
      <line x1="100" y1="52" x2="97" y2="60" stroke="#2a2a2a" strokeWidth="1" />
      <line x1="100" y1="52" x2="103" y2="60" stroke="#2a2a2a" strokeWidth="1" />
      <line x1="100" y1="43" x2="110" y2="40" stroke="#2a2a2a" strokeWidth="1" />
      {/* Figure right */}
      <circle cx="200" cy="35" r="3" fill="#2a2a2a" />
      <line x1="200" y1="38" x2="200" y2="52" stroke="#2a2a2a" strokeWidth="1.5" />
      <line x1="200" y1="52" x2="197" y2="60" stroke="#2a2a2a" strokeWidth="1" />
      <line x1="200" y1="52" x2="203" y2="60" stroke="#2a2a2a" strokeWidth="1" />
      <line x1="200" y1="43" x2="190" y2="40" stroke="#2a2a2a" strokeWidth="1" />
      {/* Signal arc */}
      <path d="M 112,38 Q 150,15 188,38" fill="none" stroke="#f5c800" strokeWidth="1.5" strokeDasharray="4 3" />
      <circle cx="150" cy="18" r="2.5" fill="#f5c800" />
      {/* Label */}
      <text x="130" y="75" fill="#999999" fontSize="7" fontFamily="monospace">future state</text>
    </svg>
  )
}

export default function PortfolioSuggestionsPage() {
  const [activeRow1, setActiveRow1] = useState<number | null>(null)
  const [activeRow2, setActiveRow2] = useState<number | null>(null)

  const handleRow1Click = (id: number) => {
    setActiveRow1(activeRow1 === id ? null : id)
  }
  const handleRow2Click = (id: number) => {
    setActiveRow2(activeRow2 === id ? null : id)
  }

  const activeRow1Persona = row1.find(p => p.id === activeRow1)
  const activeRow2Persona = row2.find(p => p.id === activeRow2)

  return (
    <div style={{ maxWidth: '1080px', margin: '0 auto', padding: '0 1.5rem 3rem' }}>
      {/* Header */}
      <div
        style={{
          borderTop: '2.5px solid #2a2a2a',
          borderBottom: '2.5px solid #2a2a2a',
          padding: '1.25rem 0',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-end',
          marginBottom: '2.5rem',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        <div>
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '10px',
              letterSpacing: '3px',
              textTransform: 'uppercase',
              color: 'var(--body-2)',
              marginBottom: '6px',
            }}
          >
            Alidade &middot; Explore
          </div>
          <h1
            style={{
              fontFamily: 'var(--font-display)',
              fontStyle: 'italic',
              fontSize: '2.8rem',
              color: 'var(--body-1)',
              margin: 0,
              lineHeight: 1.1,
            }}
          >
            Portfolio Suggestions
          </h1>
        </div>
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '9px',
            letterSpacing: '2px',
            textTransform: 'uppercase',
            color: 'var(--body-2)',
            lineHeight: 2.2,
            textAlign: 'right',
          }}
        >
          7 Personas / Based on IALD signals / Updated daily
        </div>
      </div>

      {/* Intro copy */}
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: '11px',
          color: 'var(--body-2)',
          lineHeight: 1.9,
          marginBottom: '2rem',
          maxWidth: '600px',
        }}
      >
        Select a persona that matches your investment philosophy.
        Each surfaces 12 candidates &mdash; 6 featured, 6 on request.
        Signals are weighted to your mindset.
      </div>

      {/* Row 1 */}
      <div className="persona-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '15px', marginBottom: '15px' }}>
        {row1.map(p => (
          <PersonaCard key={p.id} persona={p} isActive={activeRow1 === p.id} onClick={() => handleRow1Click(p.id)} />
        ))}
      </div>
      {activeRow1Persona && (
        <div style={{ marginBottom: '15px' }}>
          <PersonaAccordion persona={activeRow1Persona} />
        </div>
      )}

      {/* Row 2 */}
      <div className="persona-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '15px', marginBottom: '15px' }}>
        {row2.map(p => (
          <PersonaCard key={p.id} persona={p} isActive={activeRow2 === p.id} onClick={() => handleRow2Click(p.id)} />
        ))}
      </div>
      {activeRow2Persona && (
        <div style={{ marginBottom: '15px' }}>
          <PersonaAccordion persona={activeRow2Persona} />
        </div>
      )}

      {/* Drawer */}
      <div style={{ marginBottom: '2.5rem', marginTop: '1.5rem' }}>
        <PersonaDrawer personas={drawerPersonas} />
      </div>

      {/* Bottom info strip */}
      <div
        className="info-strip"
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr 1fr',
          border: '2.5px solid #2a2a2a',
          borderRadius: '10px',
          overflow: 'hidden',
          marginBottom: '2.5rem',
        }}
      >
        <div style={{ padding: '1.25rem', borderRight: '1px solid #ddd8ce' }}>
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '9px',
              letterSpacing: '2px',
              textTransform: 'uppercase',
              color: 'var(--body-2)',
              marginBottom: '10px',
            }}
          >
            New collectors required
          </div>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {['Prediction market feeds', 'Congressional trade alerts', 'Revolving door dataset'].map(item => (
              <li
                key={item}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '11px',
                  color: 'var(--body-1)',
                  lineHeight: 1.9,
                }}
              >
                &bull; {item}
              </li>
            ))}
          </ul>
        </div>
        <div style={{ padding: '1.25rem', borderRight: '1px solid #ddd8ce' }}>
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '9px',
              letterSpacing: '2px',
              textTransform: 'uppercase',
              color: 'var(--body-2)',
              marginBottom: '10px',
            }}
          >
            Datestamp precision
          </div>
          <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
            {['Event time: millisecond', 'Observed time: second', 'Available time: computed'].map(item => (
              <li
                key={item}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: '11px',
                  color: 'var(--body-1)',
                  lineHeight: 1.9,
                }}
              >
                &bull; {item}
              </li>
            ))}
          </ul>
        </div>
        <div style={{ padding: '0', background: '#ede9e0' }}>
          <BottomIllustration />
        </div>
      </div>

      {/* Footer */}
      <div
        style={{
          borderTop: '2.5px solid #2a2a2a',
          padding: '1rem 0',
          display: 'flex',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '0.5rem',
        }}
      >
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '9px',
            letterSpacing: '2px',
            textTransform: 'uppercase',
            color: 'var(--body-2)',
          }}
        >
          Alidade &middot; Portfolio Suggestions
        </span>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '9px',
            letterSpacing: '2px',
            textTransform: 'uppercase',
            color: 'var(--body-2)',
          }}
        >
          IALD v2 &middot; 7 personas &middot; Experimental
        </span>
      </div>
    </div>
  )
}

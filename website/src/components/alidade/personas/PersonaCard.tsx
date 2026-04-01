import type { Persona } from '@/lib/personas'
import PersonaIllustration from './PersonaIllustration'

interface PersonaCardProps {
  persona: Persona
  isActive: boolean
  onClick: () => void
}

export default function PersonaCard({ persona, isActive, onClick }: PersonaCardProps) {
  return (
    <div
      onClick={onClick}
      className="persona-card"
      style={{
        border: '2.5px solid #2a2a2a',
        borderRadius: '10px',
        background: 'var(--card-bg)',
        cursor: 'pointer',
        transition: 'transform 0.15s ease, box-shadow 0.15s ease',
        overflow: 'hidden',
        ...(isActive ? { transform: 'translateY(-2px)', boxShadow: '5px 5px 0 #2a2a2a' } : {}),
      }}
      onMouseEnter={e => {
        if (!isActive) {
          e.currentTarget.style.transform = 'translateY(-2px)'
          e.currentTarget.style.boxShadow = '5px 5px 0 #2a2a2a'
        }
      }}
      onMouseLeave={e => {
        if (!isActive) {
          e.currentTarget.style.transform = 'none'
          e.currentTarget.style.boxShadow = 'none'
        }
      }}
    >
      {/* Accent bar */}
      <div style={{ height: '10px', background: persona.color }} />

      {/* Card body */}
      <div style={{ padding: '1.25rem' }}>
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '9px',
            letterSpacing: '2px',
            textTransform: 'uppercase',
            color: 'var(--body-2)',
            marginBottom: '4px',
          }}
        >
          Persona {String(persona.id).padStart(2, '0')}
        </div>
        <div
          style={{
            fontFamily: 'var(--font-display)',
            fontStyle: 'italic',
            fontSize: '1.35rem',
            color: 'var(--body-1)',
            marginBottom: '10px',
            lineHeight: 1.3,
          }}
        >
          {persona.name}
        </div>
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '11.5px',
            fontStyle: 'italic',
            color: 'var(--body-1)',
            lineHeight: 1.65,
            minHeight: '60px',
            marginBottom: '12px',
          }}
        >
          &ldquo;{persona.quote}&rdquo;
        </div>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '9px',
              letterSpacing: '2px',
              textTransform: 'uppercase',
              padding: '3px 8px',
              background: persona.color,
              color: persona.color === '#f5c800' ? '#1e1e1e' : '#ffffff',
              borderRadius: '3px',
            }}
          >
            {persona.timeframe}
          </span>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: '9px',
              letterSpacing: '2px',
              textTransform: 'uppercase',
              padding: '3px 8px',
              border: '1.5px solid #2a2a2a',
              color: 'var(--body-1)',
              borderRadius: '3px',
            }}
          >
            {persona.badge}
          </span>
        </div>
      </div>

      {/* Illustration */}
      <PersonaIllustration slug={persona.slug} />

      {/* Expand hint */}
      <div
        style={{
          borderTop: '1px solid #ddd8ce',
          padding: '8px 1.25rem',
          textAlign: 'right',
          fontFamily: 'var(--font-mono)',
          fontSize: '9px',
          letterSpacing: '2px',
          textTransform: 'uppercase',
          color: 'var(--body-2)',
        }}
      >
        {isActive ? 'Collapse \u2191' : 'Expand \u2193'}
      </div>
    </div>
  )
}

import type { Persona } from '@/lib/personas'

interface PersonaAccordionProps {
  persona: Persona
}

export default function PersonaAccordion({ persona }: PersonaAccordionProps) {
  return (
    <div
      className="persona-accordion"
      style={{
        border: '2.5px solid #2a2a2a',
        borderRadius: '10px',
        background: 'var(--card-bg)',
        padding: '1.5rem',
        display: 'grid',
        gridTemplateColumns: '1fr 260px',
        gap: '2rem',
      }}
    >
      {/* Left: character + signals */}
      <div>
        <div
          style={{
            fontFamily: 'var(--font-display)',
            fontStyle: 'italic',
            fontSize: '1.1rem',
            color: 'var(--body-1)',
            marginBottom: '12px',
          }}
        >
          {persona.name}
        </div>
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '11px',
            color: 'var(--body-2)',
            lineHeight: 1.9,
            marginBottom: '16px',
          }}
        >
          {persona.character}
        </div>
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '9px',
            letterSpacing: '2px',
            textTransform: 'uppercase',
            color: 'var(--body-2)',
            marginBottom: '8px',
          }}
        >
          Key Signals
        </div>
        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {persona.signals.map((signal, i) => (
            <li
              key={i}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '11px',
                color: 'var(--body-1)',
                lineHeight: 1.9,
                paddingLeft: '12px',
                position: 'relative',
              }}
            >
              <span
                style={{
                  position: 'absolute',
                  left: 0,
                  color: persona.color,
                }}
              >
                &bull;
              </span>
              {signal}
            </li>
          ))}
        </ul>
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '11px',
            color: 'var(--body-2)',
            marginTop: '16px',
          }}
        >
          12 suggestions &middot; coming soon
        </div>
      </div>

      {/* Right: alignment */}
      <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '9px',
            letterSpacing: '2px',
            textTransform: 'uppercase',
            color: 'var(--body-2)',
            marginBottom: '8px',
          }}
        >
          IALD / Analyst Alignment
        </div>
        <div
          style={{
            fontFamily: 'var(--font-display)',
            fontStyle: 'italic',
            fontSize: '1.8rem',
            color: 'var(--body-1)',
            marginBottom: '8px',
          }}
        >
          {persona.alignment}%
        </div>
        {/* Alignment bar */}
        <div
          style={{
            width: '100%',
            height: '3px',
            background: '#ddd8ce',
            borderRadius: '2px',
            position: 'relative',
          }}
        >
          <div
            style={{
              width: `${persona.alignment}%`,
              height: '3px',
              background: persona.color,
              borderRadius: '2px',
            }}
          />
        </div>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            marginTop: '4px',
          }}
        >
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '8px', color: 'var(--body-2)' }}>
            Inverted
          </span>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: '8px', color: 'var(--body-2)' }}>
            Full alignment
          </span>
        </div>
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: '11px',
            color: 'var(--body-2)',
            lineHeight: 1.9,
            marginTop: '12px',
          }}
        >
          {persona.alignmentLabel}
        </div>
      </div>
    </div>
  )
}

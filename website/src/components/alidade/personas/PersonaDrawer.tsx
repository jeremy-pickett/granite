'use client'

import { useState } from 'react'
import type { Persona } from '@/lib/personas'
import PersonaAccordion from './PersonaAccordion'

interface PersonaDrawerProps {
  personas: Persona[]
}

const biasStates = [
  { label: 'CONFIRMED', description: 'Insider cluster buy pre-catalyst', opacity: 1 },
  { label: 'PROBABLE', description: 'Options flow skew + above-avg volume', opacity: 0.85 },
  { label: 'INFERRED', description: 'Congressional transaction \u00b13 days', opacity: 0.7 },
  { label: 'SUGGESTED', description: 'IALD elevated, analysts neutral', opacity: 0.55 },
  { label: 'GOSSIP-GRADE', description: 'Prediction market divergence', opacity: 0.4 },
  { label: 'SPECULATIVE', description: 'Sector rotation, no specific signal', opacity: 0.28 },
  { label: 'UNRESOLVABLE', description: 'Anomaly present, catalyst unknown', opacity: 0.18 },
]

export default function PersonaDrawer({ personas }: PersonaDrawerProps) {
  const [expandedId, setExpandedId] = useState<number | null>(null)

  return (
    <div
      style={{
        border: '2.5px solid #2a2a2a',
        borderRadius: '10px',
        background: 'var(--card-bg)',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          padding: '12px 1.25rem 8px',
          fontFamily: 'var(--font-mono)',
          fontSize: '9px',
          letterSpacing: '3px',
          textTransform: 'uppercase',
          color: 'var(--body-2)',
        }}
      >
        Additional personas
      </div>
      {personas.map(persona => (
        <div key={persona.id}>
          <div
            onClick={() => setExpandedId(expandedId === persona.id ? null : persona.id)}
            style={{
              padding: '10px 1.25rem',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              cursor: 'pointer',
              borderTop: '1px solid #ddd8ce',
            }}
          >
            <span
              style={{
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                background: persona.color,
                flexShrink: 0,
              }}
            />
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '9px',
                letterSpacing: '2px',
                textTransform: 'uppercase',
                color: 'var(--body-2)',
                flexShrink: 0,
              }}
            >
              {String(persona.id).padStart(2, '0')}
            </span>
            <span
              style={{
                fontFamily: 'var(--font-display)',
                fontStyle: 'italic',
                fontSize: '1.1rem',
                color: 'var(--body-1)',
                flex: 1,
              }}
            >
              {persona.name}
            </span>
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
                flexShrink: 0,
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
                color: 'var(--body-2)',
                flexShrink: 0,
              }}
            >
              {expandedId === persona.id ? 'Hide \u2191' : 'Show \u2193'}
            </span>
          </div>
          {expandedId === persona.id && (
            <div style={{ padding: '0 1.25rem 1.25rem' }}>
              <PersonaAccordion persona={persona} />
              {/* Bias state table for persona 07 */}
              {persona.slug === 'catalyst-calendar' && (
                <div style={{ marginTop: '16px' }}>
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
                    Directional Bias State
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    {biasStates.map(state => (
                      <div
                        key={state.label}
                        style={{
                          display: 'flex',
                          gap: '16px',
                          alignItems: 'baseline',
                        }}
                      >
                        <span
                          style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: '9px',
                            letterSpacing: '2px',
                            textTransform: 'uppercase',
                            color: `rgba(30, 30, 30, ${state.opacity})`,
                            width: '120px',
                            flexShrink: 0,
                          }}
                        >
                          {state.label}
                        </span>
                        <span
                          style={{
                            fontFamily: 'var(--font-mono)',
                            fontSize: '11px',
                            color: `rgba(30, 30, 30, ${state.opacity})`,
                            lineHeight: 1.9,
                          }}
                        >
                          {state.description}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

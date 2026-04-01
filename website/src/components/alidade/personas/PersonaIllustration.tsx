interface PersonaIllustrationProps {
  slug: string
}

function AsymmetryHunter() {
  return (
    <svg viewBox="0 0 300 80" width="100%" height="80" style={{ display: 'block' }}>
      <rect width="300" height="80" fill="#ede9e0" />
      {/* Mondrian blue block left */}
      <rect x="0" y="0" width="30" height="50" fill="#00358e" />
      {/* Mondrian red block right */}
      <rect x="270" y="20" width="30" height="60" fill="#c8102e" />
      {/* Office building */}
      <rect x="110" y="10" width="80" height="55" fill="#2a2a2a" stroke="#1e1e1e" strokeWidth="1" />
      {/* Windows grid */}
      {[0, 1, 2, 3].map(row =>
        [0, 1, 2].map(col => (
          <rect
            key={`${row}-${col}`}
            x={118 + col * 24}
            y={16 + row * 12}
            width="16"
            height="8"
            fill="#f5f0e8"
          />
        ))
      )}
      {/* Tiny figure with binoculars */}
      <circle cx="72" cy="58" r="3" fill="#2a2a2a" />
      <line x1="72" y1="61" x2="72" y2="72" stroke="#2a2a2a" strokeWidth="1.5" />
      <line x1="72" y1="64" x2="68" y2="68" stroke="#2a2a2a" strokeWidth="1.2" />
      <line x1="72" y1="63" x2="80" y2="60" stroke="#2a2a2a" strokeWidth="1.2" />
      <circle cx="81" cy="59" r="2" fill="none" stroke="#2a2a2a" strokeWidth="1" />
      <circle cx="85" cy="58" r="2" fill="none" stroke="#2a2a2a" strokeWidth="1" />
      <line x1="72" y1="72" x2="69" y2="78" stroke="#2a2a2a" strokeWidth="1.2" />
      <line x1="72" y1="72" x2="75" y2="78" stroke="#2a2a2a" strokeWidth="1.2" />
      {/* Yellow dot at feet */}
      <circle cx="70" cy="76" r="2.5" fill="#f5c800" />
      {/* Ground */}
      <line x1="0" y1="78" x2="300" y2="78" stroke="#c8c4bc" strokeWidth="0.5" />
    </svg>
  )
}

function BoardWhisperer() {
  return (
    <svg viewBox="0 0 300 80" width="100%" height="80" style={{ display: 'block' }}>
      <rect width="300" height="80" fill="#ede9e0" />
      {/* Yellow block right */}
      <rect x="260" y="0" width="40" height="35" fill="#f5c800" />
      {/* Boardroom table baseline */}
      <rect x="40" y="52" width="220" height="2" fill="#2a2a2a" />
      {/* Bar chart bars with circle heads */}
      {[0, 1, 2, 3, 4, 5].map(i => {
        const x = 60 + i * 36
        const h = [28, 22, 32, 18, 38, 25][i]
        const isSignal = i === 4
        return (
          <g key={i}>
            <rect x={x - 4} y={52 - h} width="8" height={h} fill={isSignal ? '#c8102e' : '#2a2a2a'} opacity={isSignal ? 1 : 0.6} />
            <circle cx={x} cy={52 - h - 5} r="4" fill={isSignal ? '#c8102e' : '#2a2a2a'} opacity={isSignal ? 1 : 0.5} />
          </g>
        )
      })}
      {/* Red signal dot above bar 4 */}
      <circle cx="204" cy="4" r="3" fill="#c8102e" />
      <line x1="204" y1="7" x2="204" y2="14" stroke="#c8102e" strokeWidth="1" strokeDasharray="2 2" />
      {/* Ground strip */}
      <rect x="0" y="70" width="300" height="10" fill="#d9d4ca" />
    </svg>
  )
}

function VolatilityArchaeologist() {
  return (
    <svg viewBox="0 0 300 80" width="100%" height="80" style={{ display: 'block' }}>
      <rect width="300" height="80" fill="#ede9e0" />
      {/* Yellow block left */}
      <rect x="0" y="10" width="25" height="40" fill="#f5c800" />
      {/* Strata layers */}
      <rect x="0" y="40" width="300" height="14" fill="#d4c9a8" />
      <rect x="0" y="54" width="300" height="13" fill="#c4b898" />
      <rect x="0" y="67" width="300" height="13" fill="#b4a888" />
      {/* Tiny figure with tool */}
      <circle cx="150" cy="32" r="2.5" fill="#2a2a2a" />
      <line x1="150" y1="34.5" x2="150" y2="42" stroke="#2a2a2a" strokeWidth="1.2" />
      <line x1="150" y1="42" x2="147" y2="47" stroke="#2a2a2a" strokeWidth="1" />
      <line x1="150" y1="42" x2="153" y2="47" stroke="#2a2a2a" strokeWidth="1" />
      <line x1="150" y1="37" x2="156" y2="44" stroke="#2a2a2a" strokeWidth="1" />
      <line x1="156" y1="44" x2="156" y2="48" stroke="#8a7a5a" strokeWidth="1.5" />
      {/* Anomaly marker */}
      <circle cx="210" cy="47" r="3" fill="#c8102e" />
      <line x1="210" y1="30" x2="210" y2="75" stroke="#c8102e" strokeWidth="1" strokeDasharray="3 2" />
      <text x="218" y="50" fill="#c8102e" fontSize="7" fontFamily="monospace">anomaly</text>
    </svg>
  )
}

function AnalystFader() {
  return (
    <svg viewBox="0 0 300 80" width="100%" height="80" style={{ display: 'block' }}>
      <rect width="300" height="80" fill="#ede9e0" />
      {/* Blue block right */}
      <rect x="270" y="0" width="30" height="45" fill="#00358e" />
      {/* Ground strip */}
      <rect x="0" y="70" width="300" height="10" fill="#d9d4ca" />
      {/* Price curve peaking then declining */}
      <polyline
        points="30,60 60,55 90,48 120,38 150,28 170,22 190,25 210,35 240,48 260,55"
        fill="none"
        stroke="#2a2a2a"
        strokeWidth="2"
      />
      {/* Earnings dashed marker */}
      <line x1="170" y1="10" x2="170" y2="68" stroke="#555555" strokeWidth="1" strokeDasharray="3 3" />
      <text x="173" y="16" fill="#555555" fontSize="6" fontFamily="monospace">earnings</text>
      {/* Dark figure left (you) */}
      <circle cx="60" cy="60" r="2.5" fill="#2a2a2a" />
      <line x1="60" y1="62.5" x2="60" y2="70" stroke="#2a2a2a" strokeWidth="1.2" />
      {/* Faded figure right (analyst) */}
      <circle cx="240" cy="52" r="2.5" fill="#aaaaaa" />
      <line x1="240" y1="54.5" x2="240" y2="62" stroke="#aaaaaa" strokeWidth="1.2" />
    </svg>
  )
}

function GovernanceArbitrageur() {
  return (
    <svg viewBox="0 0 300 80" width="100%" height="80" style={{ display: 'block' }}>
      <rect width="300" height="80" fill="#ede9e0" />
      {/* Red block left */}
      <rect x="0" y="0" width="25" height="50" fill="#c8102e" />
      {/* Revolving door square */}
      <rect x="120" y="15" width="60" height="50" fill="none" stroke="#2a2a2a" strokeWidth="1.5" />
      <line x1="150" y1="15" x2="150" y2="65" stroke="#2a2a2a" strokeWidth="1.5" />
      {/* Sine wave path through door */}
      <path
        d="M 80,40 Q 110,25 135,40 Q 150,50 165,40 Q 190,25 220,40"
        fill="none"
        stroke="#555555"
        strokeWidth="1.2"
      />
      {/* Dark figure left approaching */}
      <circle cx="85" cy="50" r="2.5" fill="#2a2a2a" />
      <line x1="85" y1="52.5" x2="85" y2="62" stroke="#2a2a2a" strokeWidth="1.2" />
      <line x1="85" y1="62" x2="82" y2="68" stroke="#2a2a2a" strokeWidth="1" />
      <line x1="85" y1="62" x2="88" y2="68" stroke="#2a2a2a" strokeWidth="1" />
      {/* Faded figure right departing */}
      <circle cx="215" cy="50" r="2.5" fill="#aaaaaa" />
      <line x1="215" y1="52.5" x2="215" y2="62" stroke="#aaaaaa" strokeWidth="1.2" />
      <line x1="215" y1="62" x2="212" y2="68" stroke="#aaaaaa" strokeWidth="1" />
      <line x1="215" y1="62" x2="218" y2="68" stroke="#aaaaaa" strokeWidth="1" />
      {/* Red dot above center */}
      <circle cx="150" cy="8" r="3" fill="#c8102e" />
    </svg>
  )
}

function DiligentSaver() {
  return (
    <svg viewBox="0 0 300 130" width="100%" height="130" style={{ display: 'block' }}>
      <rect width="300" height="130" fill="#ede9e0" />
      {/* Sky */}
      <rect x="0" y="0" width="300" height="70" fill="#c8e0f0" />
      {/* Ground */}
      <rect x="0" y="70" width="300" height="50" fill="#b8d898" />
      {/* Mondrian blocks */}
      <rect x="0" y="0" width="35" height="35" fill="#00358e" />
      <rect x="260" y="0" width="40" height="25" fill="#f5c800" />
      <rect x="265" y="25" width="35" height="20" fill="#c8102e" />
      {/* Treeline silhouettes */}
      {[60, 90, 115, 140, 180, 210, 235].map((x, i) => (
        <ellipse key={i} cx={x} cy={70} rx={12 + (i % 3) * 3} ry={10 + (i % 2) * 5} fill="#7aaa5a" opacity="0.6" />
      ))}
      {/* Benchmark dashed line */}
      <line x1="30" y1="55" x2="250" y2="48" stroke="#888888" strokeWidth="1" strokeDasharray="4 3" />
      {/* Performance line above benchmark */}
      <polyline
        points="30,54 60,52 90,49 120,46 150,43 180,40 210,37 240,35"
        fill="none"
        stroke="#00358e"
        strokeWidth="2"
      />
      {/* Tiny gardener figure */}
      <circle cx="160" cy="82" r="3" fill="#2a2a2a" />
      <line x1="160" y1="85" x2="160" y2="98" stroke="#2a2a2a" strokeWidth="1.5" />
      <line x1="160" y1="98" x2="157" y2="106" stroke="#2a2a2a" strokeWidth="1.2" />
      <line x1="160" y1="98" x2="163" y2="106" stroke="#2a2a2a" strokeWidth="1.2" />
      {/* Wide-brim hat */}
      <ellipse cx="160" cy="80" rx="6" ry="1.5" fill="#2a2a2a" />
      {/* Arm reaching to plant */}
      <line x1="160" y1="90" x2="170" y2="95" stroke="#2a2a2a" strokeWidth="1.2" />
      {/* Small plant */}
      <line x1="172" y1="105" x2="172" y2="95" stroke="#5a8a3a" strokeWidth="1.5" />
      <ellipse cx="169" cy="94" rx="3" ry="4" fill="#7aaa5a" />
      <ellipse cx="175" cy="93" rx="3" ry="4" fill="#7aaa5a" />
      {/* Mondrian strip at bottom */}
      <rect x="0" y="120" width="100" height="10" fill="#00358e" />
      <rect x="100" y="120" width="100" height="10" fill="#f5c800" />
      <rect x="200" y="120" width="100" height="10" fill="#c8102e" />
    </svg>
  )
}

function CatalystCalendar() {
  return (
    <svg viewBox="0 0 300 80" width="100%" height="80" style={{ display: 'block' }}>
      <rect width="300" height="80" fill="#ede9e0" />
      {/* Calendar grid */}
      <rect x="60" y="10" width="180" height="55" fill="none" stroke="#2a2a2a" strokeWidth="1" />
      {[0, 1, 2, 3, 4, 5].map(i => (
        <line key={`v${i}`} x1={90 + i * 30} y1="10" x2={90 + i * 30} y2="65" stroke="#c8c4bc" strokeWidth="0.5" />
      ))}
      {[0, 1, 2].map(i => (
        <line key={`h${i}`} x1="60" y1={24 + i * 14} x2="240" y2={24 + i * 14} stroke="#c8c4bc" strokeWidth="0.5" />
      ))}
      {/* Event markers */}
      <circle cx="105" cy="31" r="4" fill="#f5c800" />
      <circle cx="195" cy="45" r="4" fill="#c8102e" />
      <rect x="148" y="17" width="4" height="10" fill="#00358e" />
      {/* Tiny figure */}
      <circle cx="40" cy="45" r="2.5" fill="#2a2a2a" />
      <line x1="40" y1="47.5" x2="40" y2="58" stroke="#2a2a2a" strokeWidth="1.2" />
      <line x1="40" y1="51" x2="46" y2="48" stroke="#2a2a2a" strokeWidth="1" />
      {/* Yellow block */}
      <rect x="270" y="50" width="30" height="30" fill="#f5c800" />
    </svg>
  )
}

const illustrations: Record<string, () => React.JSX.Element> = {
  'asymmetry-hunter': AsymmetryHunter,
  'board-whisperer': BoardWhisperer,
  'volatility-archaeologist': VolatilityArchaeologist,
  'analyst-fader': AnalystFader,
  'governance-arbitrageur': GovernanceArbitrageur,
  'diligent-saver': DiligentSaver,
  'catalyst-calendar': CatalystCalendar,
}

export default function PersonaIllustration({ slug }: PersonaIllustrationProps) {
  const Illustration = illustrations[slug]
  if (!Illustration) return null
  return (
    <div style={{ borderTop: '1.5px solid #c8c4bc' }}>
      <Illustration />
    </div>
  )
}

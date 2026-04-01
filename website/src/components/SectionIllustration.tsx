export default function SectionIllustration() {
  return (
    <div className="section-scene-window" style={{ width: '280px', height: '340px' }}>
      <div className="scene-paper">
        <svg viewBox="0 0 280 340" xmlns="http://www.w3.org/2000/svg" style={{ width: '100%', height: '100%' }}>
          <rect x="0" y="0" width="280" height="340" fill="#F5F0E8" />
          <path
            d="M20,300 Q100,120 260,160"
            fill="none"
            stroke="#8A7A60"
            strokeWidth=".8"
            strokeDasharray="3,5"
            opacity=".4"
          />
          <g transform="translate(38,288)">
            <rect x="-4" y="22" width="5" height="15" rx="2" fill="#3A3428" />
            <rect x="2" y="24" width="5" height="13" rx="2" fill="#3A3428" />
            <rect x="-7" y="8" width="17" height="18" rx="2" fill="#5A5040" />
            <rect x="-4" y="8" width="4" height="7" rx="1" fill="#7A2020" opacity=".7" />
            <circle cx="2" cy="4" r="6" fill="#D0A870" />
            <rect x="-4" y="-3" width="12" height="8" rx="3" fill="#7A2020" />
            <rect x="-18" y="16" width="14" height="2.5" rx="1.5" fill="#8A7860" transform="rotate(-12,-11,17)" />
          </g>
          <g transform="translate(68,295)" opacity=".6">
            <ellipse cx="0" cy="12" rx="10" ry="7" fill="#8A5A30" />
            <circle cx="-4" cy="6" r="6" fill="#8A5A30" />
            <path d="M-8,2 L-14,-4 L-6,1 Z" fill="#8A5A30" />
            <path d="M-1,2 L4,-5  L2,1  Z" fill="#8A5A30" />
            <path
              d="M8,14 Q18,10 22,18"
              fill="none"
              stroke="#8A5A30"
              strokeWidth="3"
              strokeLinecap="round"
            />
          </g>
          <text
            x="140"
            y="50"
            textAnchor="middle"
            fontFamily="Georgia,serif"
            fontStyle="italic"
            fontSize="10"
            fill="#C8BFA8"
            opacity=".5"
          >
            the signal is the subject
          </text>
          <text
            x="262"
            y="333"
            textAnchor="end"
            fontFamily="Georgia,serif"
            fontStyle="italic"
            fontSize="8"
            fill="#A89878"
            opacity=".5"
          >
            Pickett after Semp&eacute;
          </text>
        </svg>
      </div>
      <div className="scene-frame" />
    </div>
  );
}

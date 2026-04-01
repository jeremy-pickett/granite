export default function HeroIllustration() {
  return (
    <svg className="scene-svg" viewBox="0 0 380 520" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="sky-cream" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#EDE5D0" />
          <stop offset="100%" stopColor="#F5F0E8" />
        </linearGradient>
        <linearGradient id="ground-wash" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#DDD5BE" />
          <stop offset="100%" stopColor="#E8E0CB" />
        </linearGradient>
      </defs>

      {/* Sky wash */}
      <rect x="0" y="0" width="380" height="520" fill="url(#sky-cream)" />
      <rect x="0" y="310" width="380" height="210" fill="url(#ground-wash)" />

      {/* Far buildings (ink, very light) */}
      <rect x="0" y="260" width="28" height="250" fill="#BDB5A0" opacity=".4" />
      <rect x="30" y="290" width="20" height="220" fill="#BDB5A0" opacity=".3" />
      <rect x="52" y="240" width="35" height="270" fill="#BDB5A0" opacity=".35" />
      <rect x="310" y="250" width="30" height="270" fill="#BDB5A0" opacity=".4" />
      <rect x="342" y="270" width="40" height="250" fill="#BDB5A0" opacity=".3" />
      <rect x="345" y="232" width="18" height="280" fill="#BDB5A0" opacity=".35" />

      {/* Mid buildings */}
      <rect x="0" y="310" width="40" height="210" fill="#A8A090" opacity=".5" />
      <rect x="42" y="330" width="25" height="190" fill="#A8A090" opacity=".4" />
      <rect x="320" y="305" width="45" height="215" fill="#A8A090" opacity=".5" />
      <rect x="360" y="320" width="20" height="200" fill="#A8A090" opacity=".4" />

      {/* Ground plane */}
      <rect x="0" y="410" width="380" height="110" fill="#C8BFA8" opacity=".6" />
      <line x1="0" y1="410" x2="380" y2="410" stroke="#8A8070" strokeWidth=".8" opacity=".4" />

      {/* Moon */}
      <circle cx="298" cy="55" r="28" fill="#F0E8D5" stroke="#C8BFA8" strokeWidth=".8" />
      <circle cx="288" cy="48" r="8" fill="#E0D8C5" opacity=".6" />
      <circle cx="298" cy="60" r="5" fill="#E0D8C5" opacity=".4" />

      {/* Signal arc */}
      <path
        d="M 30,380 Q 140,180 240,240 Q 320,290 355,320"
        fill="none"
        stroke="#8A7A60"
        strokeWidth=".8"
        strokeDasharray="4,6"
        opacity=".35"
      />

      {/* ROBOT COURIER */}
      <g className="robot-float" transform="translate(85,280)">
        <rect x="-12" y="0" width="32" height="46" rx="6" fill="#7090A0" opacity=".85" />
        <rect x="-8" y="3" width="24" height="3" rx="1" fill="#5A7888" />
        <rect x="-8" y="8" width="24" height="3" rx="1" fill="#5A7888" />
        <rect x="-6" y="44" width="7" height="7" rx="2" fill="#5A7888" />
        <rect x="3" y="44" width="7" height="7" rx="2" fill="#5A7888" />
        <rect x="12" y="44" width="7" height="7" rx="2" fill="#5A7888" />
        <ellipse cx="-2" cy="53" rx="3" ry="4" fill="#C06020" opacity=".7" className="ant-glow" />
        <ellipse cx="6" cy="54" rx="3" ry="5" fill="#D08030" opacity=".6" className="ant-glow2" />
        <ellipse cx="15" cy="53" rx="3" ry="4" fill="#C06020" opacity=".7" className="ant-glow" />
        <rect x="-8" y="2" width="24" height="40" rx="4" fill="#90B0C0" />
        <rect x="-3" y="8" width="14" height="14" rx="2" fill="#6A9AAC" />
        <circle cx="0" cy="13" r="2.5" fill="#C06020" className="ant-glow" />
        <circle cx="6" cy="13" r="2.5" fill="#1AA882" className="ant-glow2" />
        <circle cx="11" cy="13" r="2.5" fill="#C8972A" className="ant-glow" />
        <rect x="-6" y="-20" width="20" height="24" rx="6" fill="#90B0C0" />
        <rect x="-2" y="-15" width="12" height="7" rx="2" fill="#C8972A" opacity=".9" className="ant-glow" />
        <line x1="4" y1="-20" x2="4" y2="-30" stroke="#6A9AAC" strokeWidth="1.5" />
        <circle cx="4" cy="-32" r="3" fill="#C06020" className="ant-glow" />
        <rect x="-26" y="8" width="18" height="6" rx="3" fill="#90B0C0" />
        <rect x="-44" y="2" width="20" height="16" rx="2" fill="#F5F0E8" stroke="#C8972A" strokeWidth="1" className="ant-glow" />
        <rect x="-42" y="4" width="16" height="10" rx="1" fill="#C8D8E8" opacity=".6" />
        <rect x="16" y="10" width="14" height="5" rx="3" fill="#90B0C0" />
        <rect x="-4" y="41" width="8" height="14" rx="3" fill="#6A9AAC" />
        <rect x="6" y="41" width="8" height="14" rx="3" fill="#6A9AAC" />
        <rect x="-7" y="52" width="12" height="6" rx="3" fill="#4A7080" />
        <rect x="4" y="52" width="12" height="6" rx="3" fill="#4A7080" />
      </g>

      {/* PROFESSOR */}
      <g transform="translate(284,355)">
        <rect x="-5" y="28" width="6" height="18" rx="2" fill="#3A3428" />
        <rect x="2" y="30" width="6" height="16" rx="2" fill="#3A3428" />
        <rect x="-8" y="10" width="20" height="22" rx="3" fill="#5A5040" />
        <rect x="-3" y="10" width="5" height="8" rx="1" fill="#8A3020" opacity=".7" />
        <circle cx="3" cy="5" r="8" fill="#D0A870" />
        <rect x="-5" y="-4" width="16" height="10" rx="4" fill="#7A2020" />
        <rect x="10" y="18" width="14" height="10" rx="1" fill="#F0E8D5" stroke="#C8BFA8" strokeWidth=".5" />
        <rect x="-22" y="22" width="18" height="3" rx="1.5" fill="#8A7860" transform="rotate(-15,-13,24)" />
      </g>

      {/* Footprints */}
      <ellipse cx="265" cy="425" rx="4" ry="2.5" fill="#A89878" opacity=".3" transform="rotate(-15,265,425)" />
      <ellipse cx="272" cy="430" rx="4" ry="2.5" fill="#A89878" opacity=".25" transform="rotate(-10,272,430)" />
      <ellipse cx="280" cy="424" rx="4" ry="2.5" fill="#A89878" opacity=".2" transform="rotate(-12,280,424)" />

      {/* Scan line overlay */}
      <rect className="scan-line" x="0" y="0" width="380" height="2" fill="#1AA882" opacity=".08" />

      {/* Cross-hatch sky */}
      <line x1="0" y1="80" x2="380" y2="88" stroke="#C8BFA8" strokeWidth=".3" opacity=".3" />
      <line x1="0" y1="120" x2="380" y2="128" stroke="#C8BFA8" strokeWidth=".3" opacity=".25" />
      <line x1="0" y1="160" x2="380" y2="168" stroke="#C8BFA8" strokeWidth=".3" opacity=".2" />
      <line x1="0" y1="200" x2="380" y2="208" stroke="#C8BFA8" strokeWidth=".3" opacity=".15" />

      {/* Signature */}
      <text
        x="355"
        y="512"
        textAnchor="end"
        fontFamily="Georgia,serif"
        fontStyle="italic"
        fontSize="9"
        fill="#A89878"
        opacity=".6"
      >
        Pickett after Semp&eacute;
      </text>
    </svg>
  );
}

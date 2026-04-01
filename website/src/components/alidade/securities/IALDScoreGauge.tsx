'use client';

import { useEffect, useState } from 'react';

interface IALDScoreGaugeProps {
  score: number | null;
  verdict?: string | null;
  size?: 'sm' | 'md' | 'lg';
  showVerdict?: boolean;
  bounce?: boolean; // animated entrance with overshoot bounce
}

function getScoreColor(score: number | null): string {
  if (score === null) return 'text-ald-text-dim';
  if (score >= 0.75) return 'text-ald-red';
  if (score >= 0.50) return 'text-ald-amber';
  if (score >= 0.25) return 'text-ald-blue';
  return 'text-ald-text-dim';
}

function getStrokeColor(score: number | null): string {
  if (score === null) return '#333';
  if (score >= 0.75) return '#F87171';
  if (score >= 0.50) return '#FBBF24';
  if (score >= 0.25) return '#6A8FD8';
  return '#555';
}

const sizes = {
  sm: { container: 'w-14 h-14', text: 'text-sm', verdictText: 'text-[10px]' },
  md: { container: 'w-20 h-20', text: 'text-lg', verdictText: 'text-xs' },
  lg: { container: 'w-28 h-28', text: 'text-2xl', verdictText: 'text-sm' },
};

export default function IALDScoreGauge({
  score,
  verdict,
  size = 'md',
  showVerdict = true,
  bounce = false,
}: IALDScoreGaugeProps) {
  const { container, text, verdictText } = sizes[size];

  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  const pct = score !== null ? Math.min(score, 1) : 0;
  const targetOffset = circumference - pct * circumference;

  // For bounce animation, start fully empty and animate to target
  const [offset, setOffset] = useState(bounce ? circumference : targetOffset);

  useEffect(() => {
    if (bounce && score !== null) {
      // Small delay to trigger the CSS transition after mount
      const timer = setTimeout(() => setOffset(targetOffset), 50);
      return () => clearTimeout(timer);
    } else {
      setOffset(targetOffset);
    }
  }, [bounce, score, targetOffset, circumference]);

  return (
    <div className="flex flex-col items-center">
      {bounce && (
        <style>{`
          @keyframes iald-bounce-stroke {
            0% { stroke-dashoffset: ${circumference}; }
            70% { stroke-dashoffset: ${targetOffset - (circumference * 0.03)}; }
            85% { stroke-dashoffset: ${targetOffset + (circumference * 0.015)}; }
            100% { stroke-dashoffset: ${targetOffset}; }
          }
        `}</style>
      )}
      <div className={`${container} relative`}>
        <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
          <circle
            cx="50" cy="50" r={radius}
            fill="none"
            stroke="rgba(106,143,216,0.08)"
            strokeWidth="6"
          />
          {score !== null && (
            <circle
              cx="50" cy="50" r={radius}
              fill="none"
              stroke={getStrokeColor(score)}
              strokeWidth="6"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={offset}
              style={bounce ? {
                animation: 'iald-bounce-stroke 1.2s cubic-bezier(0.34, 1.56, 0.64, 1) forwards',
                animationDelay: '0.1s',
              } : undefined}
              className={bounce ? '' : 'transition-all duration-700 ease-out'}
            />
          )}
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className={`font-mono font-light ${text} ${getScoreColor(score)}`}>
            {score !== null ? score.toFixed(2) : '--'}
          </span>
        </div>
      </div>
      {showVerdict && verdict && (
        <span className={`mt-1 font-mono uppercase tracking-wider ${verdictText} ${getScoreColor(score)}`}>
          {verdict}
        </span>
      )}
    </div>
  );
}

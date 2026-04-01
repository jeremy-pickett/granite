'use client';

import { useState, useEffect } from 'react';

const TARGET = new Date('2026-07-01T00:00:00Z').getTime();

export default function Countdown() {
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const diff = Math.max(0, TARGET - now);
  const days = Math.floor(diff / 86_400_000);
  const hours = Math.floor((diff % 86_400_000) / 3_600_000);
  const minutes = Math.floor((diff % 3_600_000) / 60_000);
  const seconds = Math.floor((diff % 60_000) / 1_000);

  return (
    <div className="countdown">
      <div className="countdown-segments">
        <div className="countdown-segment">
          <span className="countdown-value">{String(days).padStart(3, '0')}</span>
          <span className="countdown-label">days</span>
        </div>
        <span className="countdown-sep">:</span>
        <div className="countdown-segment">
          <span className="countdown-value">{String(hours).padStart(2, '0')}</span>
          <span className="countdown-label">hrs</span>
        </div>
        <span className="countdown-sep">:</span>
        <div className="countdown-segment">
          <span className="countdown-value">{String(minutes).padStart(2, '0')}</span>
          <span className="countdown-label">min</span>
        </div>
        <span className="countdown-sep">:</span>
        <div className="countdown-segment">
          <span className="countdown-value">{String(seconds).padStart(2, '0')}</span>
          <span className="countdown-label">sec</span>
        </div>
      </div>
    </div>
  );
}

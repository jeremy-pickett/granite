'use client';

import { useEffect } from 'react';

export default function LayerBar() {
  useEffect(() => {
    const fills = document.querySelectorAll('.layer-fill');
    const targets = ['100%', '12%', '90%', '99%', '100%'];
    fills.forEach((f, i) => {
      (f as HTMLElement).style.width = '0%';
      setTimeout(() => {
        (f as HTMLElement).style.width = targets[i];
      }, 900 + i * 120);
    });
  }, []);

  return (
    <div className="layer-bar">
      <div className="layer-row-item">
        <span className="layer-label-sm">A</span>
        <div className="layer-track"><div className="layer-fill amber" style={{ width: '100%' }} /></div>
      </div>
      <div className="layer-row-item">
        <span className="layer-label-sm">BC</span>
        <div className="layer-track"><div className="layer-fill dim" /></div>
      </div>
      <div className="layer-row-item">
        <span className="layer-label-sm">D</span>
        <div className="layer-track"><div className="layer-fill amber" style={{ width: '90%' }} /></div>
      </div>
      <div className="layer-row-item">
        <span className="layer-label-sm">E</span>
        <div className="layer-track"><div className="layer-fill" style={{ width: '99%' }} /></div>
      </div>
      <div className="layer-row-item">
        <span className="layer-label-sm">F</span>
        <div className="layer-track"><div className="layer-fill" style={{ width: '100%' }} /></div>
      </div>
    </div>
  );
}

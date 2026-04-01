'use client';

import { useState, useRef, useEffect, type ReactNode } from 'react';

interface TooltipProps {
  content: ReactNode;
  children: ReactNode;
  position?: 'top' | 'bottom' | 'left' | 'right';
  maxWidth?: number;
  delay?: number;
}

export default function Tooltip({
  content,
  children,
  position = 'top',
  maxWidth = 320,
  delay = 150,
}: TooltipProps) {
  const [visible, setVisible] = useState(false);
  const [coords, setCoords] = useState({ top: 0, left: 0 });
  const triggerRef = useRef<HTMLSpanElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const show = () => {
    timerRef.current = setTimeout(() => setVisible(true), delay);
  };

  const hide = () => {
    clearTimeout(timerRef.current);
    setVisible(false);
  };

  useEffect(() => {
    if (!visible || !triggerRef.current || !tooltipRef.current) return;

    const trigger = triggerRef.current.getBoundingClientRect();
    const tooltip = tooltipRef.current.getBoundingClientRect();
    const padding = 8;

    let top = 0;
    let left = 0;

    switch (position) {
      case 'top':
        top = trigger.top - tooltip.height - padding;
        left = trigger.left + trigger.width / 2 - tooltip.width / 2;
        break;
      case 'bottom':
        top = trigger.bottom + padding;
        left = trigger.left + trigger.width / 2 - tooltip.width / 2;
        break;
      case 'left':
        top = trigger.top + trigger.height / 2 - tooltip.height / 2;
        left = trigger.left - tooltip.width - padding;
        break;
      case 'right':
        top = trigger.top + trigger.height / 2 - tooltip.height / 2;
        left = trigger.right + padding;
        break;
    }

    // Keep tooltip on screen
    if (left < 8) left = 8;
    if (left + tooltip.width > window.innerWidth - 8) {
      left = window.innerWidth - tooltip.width - 8;
    }
    if (top < 8) {
      top = trigger.bottom + padding;
    }

    setCoords({ top, left });
  }, [visible, position]);

  // Clean up timer on unmount
  useEffect(() => () => clearTimeout(timerRef.current), []);

  return (
    <>
      <span
        ref={triggerRef}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        className="inline-flex cursor-help"
      >
        {children}
      </span>
      {visible && (
        <div
          ref={tooltipRef}
          role="tooltip"
          className="fixed z-[9999] rounded-lg border border-ald-border bg-ald-deep shadow-xl"
          style={{
            top: coords.top,
            left: coords.left,
            maxWidth,
          }}
        >
          <div className="px-4 py-3 text-sm leading-relaxed text-ald-text">
            {content}
          </div>
        </div>
      )}
    </>
  );
}

/* Convenience sub-components for structured tooltip content */

export function TipTitle({ children }: { children: ReactNode }) {
  return (
    <div className="mb-1.5 font-mono text-xs font-bold uppercase tracking-wider text-ald-ivory">
      {children}
    </div>
  );
}

export function TipBody({ children }: { children: ReactNode }) {
  return <div className="text-xs leading-relaxed text-ald-text-muted">{children}</div>;
}

export function TipScale({
  items,
}: {
  items: { color: string; label: string; description: string }[];
}) {
  return (
    <div className="mt-2 space-y-1">
      {items.map((item) => (
        <div key={item.label} className="flex items-center gap-2">
          <span
            className="inline-block h-2.5 w-2.5 shrink-0 rounded-sm"
            style={{ backgroundColor: item.color }}
          />
          <span className="font-mono text-xs text-ald-text">{item.label}</span>
          <span className="text-xs text-ald-text-dim">{item.description}</span>
        </div>
      ))}
    </div>
  );
}

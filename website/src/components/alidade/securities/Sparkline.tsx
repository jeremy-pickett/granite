'use client';

interface SparklinePoint {
  d: string;
  s: number;
}

interface SparklineProps {
  points: SparklinePoint[];
  width?: number;
  height?: number;
  color?: string;
}

export default function Sparkline({
  points,
  width = 80,
  height = 24,
  color,
}: SparklineProps) {
  if (!points || points.length === 0) {
    return (
      <svg width={width} height={height} className="opacity-20">
        <line
          x1={0} y1={height / 2} x2={width} y2={height / 2}
          stroke="currentColor" strokeWidth={1} strokeDasharray="2,2"
          className="text-ald-text-dim"
        />
      </svg>
    );
  }

  // Single data point — show a dot at center-right
  if (points.length === 1) {
    const s = Number(points[0].s);
    const dotColor = color ?? (s >= 0.75 ? '#F87171' : s >= 0.5 ? '#FBBF24' : s >= 0.25 ? '#6A8FD8' : '#555');
    return (
      <svg width={width} height={height}>
        <circle cx={width - 4} cy={height / 2} r={3} fill={dotColor} />
        <line x1={0} y1={height / 2} x2={width - 8} y2={height / 2}
          stroke={dotColor} strokeWidth={1} strokeDasharray="2,3" opacity={0.3} />
      </svg>
    );
  }

  const scores = points.map((p) => Number(p.s));
  const min = Math.min(...scores);
  const max = Math.max(...scores);
  const range = max - min || 0.01;

  const pad = 2;
  const innerH = height - pad * 2;
  const step = (width - pad * 2) / (scores.length - 1);

  const pts = scores.map((s, i) => {
    const x = pad + i * step;
    const y = pad + innerH - ((s - min) / range) * innerH;
    return `${x},${y}`;
  });

  const polyline = pts.join(' ');

  // Gradient fill beneath the line
  const firstPt = pts[0];
  const lastPt = pts[pts.length - 1];
  const fillPath = `M${firstPt} ${pts.slice(1).map((p) => `L${p}`).join(' ')} L${pad + (scores.length - 1) * step},${height} L${pad},${height} Z`;

  // Determine color from last score if not provided
  const lastScore = scores[scores.length - 1];
  const strokeColor =
    color ??
    (lastScore >= 0.75
      ? '#F87171'
      : lastScore >= 0.5
        ? '#FBBF24'
        : lastScore >= 0.25
          ? '#6A8FD8'
          : '#555');

  const gradientId = `spark-${points.length}-${Math.round(lastScore * 100)}`;

  return (
    <svg width={width} height={height} className="shrink-0">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={strokeColor} stopOpacity={0.25} />
          <stop offset="100%" stopColor={strokeColor} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={fillPath} fill={`url(#${gradientId})`} />
      <polyline
        points={polyline}
        fill="none"
        stroke={strokeColor}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* End dot */}
      <circle
        cx={pad + (scores.length - 1) * step}
        cy={pad + innerH - ((lastScore - min) / range) * innerH}
        r={2}
        fill={strokeColor}
      />
    </svg>
  );
}

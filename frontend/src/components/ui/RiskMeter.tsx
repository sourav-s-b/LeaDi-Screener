import React, { useEffect, useState } from 'react';

interface RiskMeterProps {
  value: number;   // 0–1
  size?: number;
  label?: string;
}

function getRiskConfig(v: number) {
  if (v < 0.35) return { label: 'Low Risk',      color: '#10b981', bg: 'bg-emerald-50', text: 'text-emerald-700', badge: 'badge-green' };
  if (v < 0.65) return { label: 'Moderate Risk', color: '#f59e0b', bg: 'bg-amber-50',   text: 'text-amber-700',   badge: 'badge-amber' };
  return         { label: 'High Risk',           color: '#ef4444', bg: 'bg-red-50',     text: 'text-red-700',     badge: 'badge-red'   };
}

export default function RiskMeter({ value, size = 120, label }: RiskMeterProps) {
  const [animated, setAnimated] = useState(0);

  useEffect(() => {
    const raf = requestAnimationFrame(() => setAnimated(value));
    return () => cancelAnimationFrame(raf);
  }, [value]);

  const cfg      = getRiskConfig(value);
  const cx       = size / 2;
  const cy       = size / 2;
  const r        = size * 0.38;
  const stroke   = size * 0.085;
  const circ     = Math.PI * r;           // half-circle arc length
  
  
  

  // Arc path (half circle, bottom open)
  const arc = (pct: number) => {
    const angle = Math.PI * pct;          // 0 → π
    const x = cx + r * Math.cos(Math.PI + angle);
    const y = cy + r * Math.sin(Math.PI + angle);
    return `${x},${y}`;
  };

  const trackD = `M ${cx - r},${cy} A ${r},${r} 0 0,1 ${cx + r},${cy}`;
  const fillD  = `M ${cx - r},${cy} A ${r},${r} 0 0,1 ${arc(animated)}`;

  return (
    <div className="flex flex-col items-center gap-1">
      <svg width={size} height={size * 0.6} viewBox={`0 0 ${size} ${size * 0.6}`} overflow="visible">
        {/* Track */}
        <path
          d={trackD}
          fill="none"
          stroke="#f1f5f9"
          strokeWidth={stroke}
          strokeLinecap="round"
        />
        {/* Fill */}
        <path
          d={fillD}
          fill="none"
          stroke={cfg.color}
          strokeWidth={stroke}
          strokeLinecap="round"
          style={{ transition: 'all 0.8s cubic-bezier(0.34,1.56,0.64,1)' }}
        />
        {/* Value text */}
        <text
          x={cx}
          y={size * 0.52}
          textAnchor="middle"
          fontSize={size * 0.2}
          fontWeight="700"
          fontFamily="Syne, sans-serif"
          fill={cfg.color}
        >
          {Math.round(animated * 100)}%
        </text>
      </svg>

      {/* Risk label */}
      <span className={`badge ${cfg.badge} text-xs`}>
        {label ?? cfg.label}
      </span>
    </div>
  );
}

export { getRiskConfig };

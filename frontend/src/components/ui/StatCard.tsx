import React from 'react';
import { LucideIcon, TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface StatCardProps {
  label:      string;
  value:      string | number;
  unit?:      string;
  icon?:      LucideIcon;
  iconColor?: string;
  trend?:     'up' | 'down' | 'flat';
  trendText?: string;
  delay?:     number;
}

export default function StatCard({
  label, value, unit, icon: Icon, iconColor = 'text-brand-600',
  trend, trendText, delay = 0,
}: StatCardProps) {
  const TrendIcon = trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : Minus;
  const trendColor = trend === 'up' ? 'text-emerald-600' : trend === 'down' ? 'text-red-500' : 'text-slate-400';

  return (
    <div
      className="card p-5 animate-fade-up"
      style={{ animationDelay: `${delay}ms`, animationFillMode: 'both' }}
    >
      <div className="flex items-start justify-between mb-3">
        <p className="text-xs font-medium text-slate-400 uppercase tracking-wide">{label}</p>
        {Icon && (
          <div className="w-7 h-7 rounded-lg bg-slate-50 flex items-center justify-center">
            <Icon size={14} className={iconColor} strokeWidth={2} />
          </div>
        )}
      </div>

      <div className="flex items-baseline gap-1">
        <span className="text-2xl font-display font-700 text-slate-900">{value}</span>
        {unit && <span className="text-xs text-slate-400">{unit}</span>}
      </div>

      {trendText && (
        <div className={`flex items-center gap-1 mt-2 ${trendColor}`}>
          <TrendIcon size={11} />
          <span className="text-[11px] font-medium">{trendText}</span>
        </div>
      )}
    </div>
  );
}

import React from 'react';
import { CheckCircle2, AlertTriangle, XCircle, Clock } from 'lucide-react';
import RiskMeter, { getRiskConfig } from './RiskMeter';

interface ResultCardProps {
  risk:        number;
  label:       string;
  confidence?: number;
  meta?:       { key: string; value: string | number }[];
  timestamp?:  string;
}

export default function ResultCard({ risk, label, confidence, meta, timestamp }: ResultCardProps) {
  const cfg = getRiskConfig(risk);

  const StatusIcon =
    risk < 0.35 ? CheckCircle2 :
    risk < 0.65 ? AlertTriangle : XCircle;

  return (
    <div className={`card p-6 animate-fade-up`}>
      <div className="flex items-start gap-6">
        {/* Gauge */}
        <div className="shrink-0">
          <RiskMeter value={risk} size={110} />
        </div>

        {/* Details */}
        <div className="flex-1 min-w-0 pt-1">
          <div className="flex items-center gap-2 mb-3">
            <StatusIcon size={16} className={cfg.text} />
            <h3 className="font-semibold text-slate-900 text-[15px]">{label}</h3>
          </div>

          {confidence !== undefined && (
            <div className="mb-4">
              <div className="flex justify-between text-xs text-slate-400 mb-1">
                <span>Confidence</span>
                <span>{Math.round(confidence * 100)}%</span>
              </div>
              <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-brand-500 rounded-full transition-all duration-700"
                  style={{ width: `${confidence * 100}%` }}
                />
              </div>
            </div>
          )}

          {meta && meta.length > 0 && (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
              {meta.map(({ key, value }) => (
                <div key={key}>
                  <dt className="text-[11px] text-slate-400">{key}</dt>
                  <dd className="text-sm font-medium text-slate-700 font-mono">{value}</dd>
                </div>
              ))}
            </dl>
          )}

          {timestamp && (
            <div className="flex items-center gap-1 mt-3 pt-3 border-t border-slate-100">
              <Clock size={11} className="text-slate-300" />
              <span className="text-[11px] text-slate-400">
                {new Date(timestamp).toLocaleString()}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

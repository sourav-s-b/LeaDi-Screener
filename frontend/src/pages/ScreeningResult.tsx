import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Mic, Eye, PenLine, RotateCcw, Home, AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';
import RiskMeter, { getRiskConfig } from '../components/ui/RiskMeter';

interface TestResult {
  risk:  number;
  label: string;
}

interface Props {
  results: Record<string, TestResult>;
  onReset: () => void;
}

const MODULE_META = [
  { id: 'dysarthria',  icon: Mic,     label: 'Dysarthria',  bg: 'bg-violet-50 border-violet-100', iconCls: 'text-violet-600' },
  { id: 'dyslexia',   icon: Eye,     label: 'Dyslexia',    bg: 'bg-sky-50 border-sky-100',       iconCls: 'text-sky-600'    },
  { id: 'handwriting', icon: PenLine, label: 'Handwriting', bg: 'bg-emerald-50 border-emerald-100', iconCls: 'text-emerald-600' },
];

function overallRisk(results: Record<string, TestResult>): number {
  const vals = Object.values(results).map(r => r.risk);
  if (!vals.length) return 0;
  // Weighted: max contributes 50%, mean contributes 50%
  const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
  const max  = Math.max(...vals);
  return (mean + max) / 2;
}

export default function ScreeningResult({ results, onReset }: Props) {
  const navigate = useNavigate();
  const overall  = overallRisk(results);
  const cfg      = getRiskConfig(overall);

  const StatusIcon = overall < 0.35 ? CheckCircle2 : overall < 0.65 ? AlertTriangle : XCircle;

  return (
    <div className="max-w-2xl mx-auto space-y-6 animate-fade-up py-4">

      {/* Header */}
      <div className="text-center space-y-1">
        <h2 className="text-xl font-display font-700 text-slate-900">Screening Complete</h2>
        <p className="text-sm text-slate-400">All three modules have been analysed</p>
      </div>

      {/* Overall score card */}
      <div className="card p-8 flex flex-col items-center gap-4 text-center">
        <RiskMeter value={overall} size={150} />
        <div className="space-y-1">
          <div className="flex items-center justify-center gap-2">
            <StatusIcon size={16} className={cfg.text} />
            <h3 className="font-semibold text-slate-900 text-lg">{cfg.label}</h3>
          </div>
          <p className="text-xs text-slate-400 max-w-sm">
            Overall combined risk from all three screening modules.
            This score is not a clinical diagnosis — consult a specialist for professional assessment.
          </p>
        </div>
      </div>

      {/* Per-module breakdown */}
      <div className="space-y-3">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Module Results</p>
        {MODULE_META.map(({ id, icon: Icon, label, bg, iconCls }) => {
          const r = results[id];
          if (!r) return null;
          const modCfg = getRiskConfig(r.risk);
          return (
            <div key={id} className="card p-5 flex items-center gap-4">
              <div className={`w-10 h-10 rounded-xl border shrink-0 flex items-center justify-center ${bg}`}>
                <Icon size={16} className={iconCls} strokeWidth={1.75} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-sm font-semibold text-slate-800">{label}</span>
                  <span className={`badge ${modCfg.badge}`}>{modCfg.label}</span>
                </div>
                <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                  <div className="h-full rounded-full transition-all duration-700"
                    style={{ width: `${r.risk * 100}%`, backgroundColor: modCfg.color }} />
                </div>
              </div>
              <div className="text-right shrink-0">
                <span className="text-xl font-display font-700" style={{ color: modCfg.color }}>
                  {Math.round(r.risk * 100)}%
                </span>
                <p className="text-[10px] text-slate-400 font-mono">{r.label.replace(/_/g, ' ')}</p>
              </div>
            </div>
          );
        })}
      </div>

      {/* Disclaimer */}
      <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl">
        <p className="text-xs text-slate-500 leading-relaxed text-center">
          <strong className="text-slate-700">Important:</strong> This screening tool is intended for research purposes only.
          Results should not be used as a substitute for professional medical evaluation.
          If you have concerns, please consult a qualified speech therapist or educational psychologist.
        </p>
      </div>

      {/* Actions */}
      <div className="flex gap-3 justify-center">
        <button onClick={() => { onReset(); navigate('/'); }} className="btn-secondary">
          <Home size={14} /> Back to Home
        </button>
        <button
          onClick={() => { onReset(); navigate('/screening'); }}
          className="btn-primary"
        >
          <RotateCcw size={14} /> Start New Screening
        </button>
      </div>

    </div>
  );
}

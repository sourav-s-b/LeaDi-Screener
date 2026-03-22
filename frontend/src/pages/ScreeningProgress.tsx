import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Mic, Eye, PenLine, CheckCircle2, ArrowRight, Lock } from 'lucide-react';
import { getRiskConfig } from '../components/ui/RiskMeter';

export type StepStatus = 'pending' | 'active' | 'done';

export interface ScreeningStep {
  id:    'handwriting' | 'dysarthria' | 'dyslexia';
  label: string;
  tag:   string;
  icon:  React.ElementType;
  route: string;
}

// ORDER: Handwriting → Speech → Eye Tracking
export const STEPS: ScreeningStep[] = [
  { id: 'handwriting', label: 'Handwriting', tag: 'Vision',       icon: PenLine, route: '/screening/handwriting' },
  { id: 'dysarthria',  label: 'Speech',      tag: 'Audio',        icon: Mic,     route: '/screening/dysarthria'  },
  { id: 'dyslexia',   label: 'Eye Tracking', tag: 'Gaze',        icon: Eye,     route: '/screening/dyslexia'    },
];

interface Props {
  results:    Record<string, { risk: number; label: string }>;
  activeStep: number;
  onNext:     () => void;
}

export default function ScreeningProgress({ results, activeStep, onNext }: Props) {
  const navigate = useNavigate();
  const allDone  = Object.keys(results).length === 3;

  const getStatus = (idx: number): StepStatus => {
    const step = STEPS[idx];
    if (results[step.id]) return 'done';
    if (idx === activeStep) return 'active';
    return 'pending';
  };

  return (
    <div className="max-w-xl mx-auto py-8 space-y-8 animate-fade-up">
      <div className="text-center space-y-1">
        <h2 className="text-xl font-display font-700 text-slate-900">
          {allDone ? 'Screening Complete' : 'Screening in Progress'}
        </h2>
        <p className="text-sm text-slate-400">
          {allDone
            ? 'All three modules completed.'
            : `Step ${Math.min(activeStep + 1, 3)} of 3 — ${STEPS[activeStep]?.label ?? ''}`}
        </p>
      </div>

      {/* 4-circle stepper */}
      <div className="flex items-center justify-center">
        {STEPS.map((step, i) => {
          const status  = getStatus(i);
          const isDone  = status === 'done';
          const isActive = status === 'active';
          const risk    = results[step.id];
          const riskCfg = risk ? getRiskConfig(risk.risk) : null;

          return (
            <React.Fragment key={step.id}>
              <div className="flex flex-col items-center gap-2">
                <button
                  onClick={() => isDone && navigate(step.route)}
                  disabled={!isDone && !isActive}
                  className={[
                    'w-16 h-16 rounded-full flex items-center justify-center transition-all duration-300 relative',
                    isDone   ? 'shadow-md cursor-pointer hover:scale-105' : '',
                    isActive ? 'bg-gradient-to-br from-brand-500 to-brand-700 shadow-lg ring-4 ring-brand-200 scale-110' : '',
                    !isDone && !isActive ? 'bg-slate-100 cursor-not-allowed' : '',
                  ].join(' ')}
                  style={isDone && riskCfg ? {
                    background: `linear-gradient(135deg, ${riskCfg.color}99, ${riskCfg.color})`
                  } : {}}
                >
                  {isDone ? (
                    <span className="text-white text-sm font-bold">{Math.round(risk!.risk * 100)}%</span>
                  ) : isActive ? (
                    <step.icon size={22} className="text-white" strokeWidth={1.75} />
                  ) : (
                    <Lock size={16} className="text-slate-300" />
                  )}
                  {isActive && (
                    <span className="absolute inset-0 rounded-full ring-2 ring-brand-400 animate-ping opacity-30" />
                  )}
                </button>
                <div className="text-center">
                  <p className={`text-xs font-semibold ${isActive ? 'text-brand-700' : isDone ? 'text-slate-700' : 'text-slate-300'}`}>
                    {step.label}
                  </p>
                  {isDone && riskCfg && (
                    <p className="text-[10px]" style={{ color: riskCfg.color }}>{riskCfg.label}</p>
                  )}
                  {isActive && <p className="text-[10px] text-brand-500 animate-pulse">Active</p>}
                </div>
              </div>

              {/* Connector */}
              {i < STEPS.length - 1 && (
                <div className={`w-10 h-0.5 mb-6 transition-colors duration-500 ${isDone ? 'bg-emerald-300' : 'bg-slate-200'}`} />
              )}
            </React.Fragment>
          );
        })}

        {/* → Final result circle */}
        <div className={`w-10 h-0.5 mb-6 transition-colors duration-500 ${allDone ? 'bg-emerald-300' : 'bg-slate-200'}`} />
        <div className="flex flex-col items-center gap-2">
          <button
            onClick={() => allDone && navigate('/screening/result')}
            disabled={!allDone}
            className={[
              'w-16 h-16 rounded-full flex items-center justify-center transition-all duration-300',
              allDone ? 'bg-gradient-to-br from-slate-700 to-slate-900 shadow-lg cursor-pointer hover:scale-105' : 'bg-slate-100 cursor-not-allowed',
            ].join(' ')}
          >
            <CheckCircle2 size={22} className={allDone ? 'text-white' : 'text-slate-300'} strokeWidth={1.75} />
          </button>
          <div className="text-center">
            <p className={`text-xs font-semibold ${allDone ? 'text-slate-700' : 'text-slate-300'}`}>Result</p>
            {allDone && <p className="text-[10px] text-emerald-600">Ready</p>}
          </div>
        </div>
      </div>

      {/* Action button */}
      <div className="flex justify-center">
        {allDone ? (
          <button onClick={() => navigate('/screening/result')} className="btn-primary px-6 py-2.5">
            View Final Report <ArrowRight size={14} />
          </button>
        ) : (
          <button onClick={onNext} className="btn-primary px-6 py-2.5">
            {activeStep === 0 ? 'Begin' : 'Continue'} — {STEPS[activeStep]?.label}
            <ArrowRight size={14} />
          </button>
        )}
      </div>

      {/* Mini results so far */}
      {Object.keys(results).length > 0 && (
        <div className="card p-4 space-y-2">
          <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Results so far</p>
          {STEPS.filter(s => results[s.id]).map(s => {
            const r = results[s.id];
            const cfg = getRiskConfig(r.risk);
            return (
              <div key={s.id} className="flex items-center gap-3">
                <s.icon size={13} className="text-slate-400 shrink-0" />
                <span className="text-xs text-slate-600 w-24">{s.label}</span>
                <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: `${r.risk * 100}%`, backgroundColor: cfg.color }} />
                </div>
                <span className="text-xs font-mono font-medium" style={{ color: cfg.color }}>
                  {Math.round(r.risk * 100)}%
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

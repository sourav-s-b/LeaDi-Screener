import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Mic, Eye, PenLine, ArrowRight, ChevronRight,
  Activity, Clock, CheckCircle2, AlertTriangle, Sparkles,
} from 'lucide-react';
import { apiEndpoints } from '../lib/api';
import { SessionSummary } from '../types';
import { getRiskConfig } from '../components/ui/RiskMeter';

const TESTS = [
  {
    icon: PenLine,
    label: 'Handwriting Analysis',
    tag: 'Vision',
    tagCls: 'badge-green',
    accent: 'from-emerald-500 to-teal-600',
    iconBg: 'bg-emerald-50 border-emerald-100 text-emerald-600',
    desc: 'Upload a photo of handwritten text. YOLOv8 detects letter reversals, mirror-writing, and orientation errors associated with dyslexia.',
    details: ['Per-letter segmentation grid', 'Polarity normalisation', 'Normal / Reversal / Corrected'],
  },
  {
    icon: Mic,
    label: 'Speech Analyses',
    tag: 'Voice',
    tagCls: 'badge-blue',
    accent: 'from-violet-500 to-purple-600',
    iconBg: 'bg-violet-50 border-violet-100 text-violet-600',
    desc: 'Record speech via the python app. CNN+BiLSTM with pitch normalisation analyses MFCCfeatures to detect motor speech disorder patterns.',
    details: ['Overlapping 6.79s windows', 'Pitch-normalised MFCC', 'Gender-conditioned model'],
  },
  {
    icon: Eye,
    label: 'Eye-Tracking Analysis',
    tag: 'Gaze',
    tagCls: 'badge-blue',
    accent: 'from-sky-500 to-cyan-600',
    iconBg: 'bg-sky-50 border-sky-100 text-sky-600',
    desc: 'Live webcam session launched from this page. Displacement-based calibration + ensemble model (RF+SVM+XGBoost) classifies 18 gaze features.',
    details: ['Range-detection calibration', 'Kalman-smoothed iris tracking', 'RF+SVM+XGBoost ensemble'],
  },
  
];

const TOOL_ICON: Record<string, React.ElementType> = { dysarthria: Mic, dyslexia: Eye, handwriting: PenLine };

export default function Home() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);

  useEffect(() => {
    apiEndpoints.sessions.list().then(r => setSessions(r.data)).catch(() => {});
  }, []);

  // Group sessions into screening runs (sets of up to 3)
  const runs = sessions.reduce<SessionSummary[][]>((acc, s, i) => {
    if (i % 3 === 0) acc.push([]);
    acc[acc.length - 1].push(s);
    return acc;
  }, []);

  return (
    <div className="max-w-4xl mx-auto space-y-16 py-4">

      {/* ── Hero ── */}
      <section className="text-center space-y-5 pt-4">
        <h1 className="text-4xl font-display font-700 text-slate-900 leading-tight tracking-tight">
          Learning Disablity<br />
          <span className="text-brand-600">Screening Dashboard</span>
        </h1>
        <p className="text-base text-slate-500 max-w-xl mx-auto leading-relaxed">
          A three-module AI system that screens for speech and reading disorders
          using audio analysis, live eye-tracking, and handwriting recognition.
        </p>
        <button
          onClick={() => navigate('/screening')}
          className="btn-primary text-base px-6 py-3 rounded-xl shadow-md hover:shadow-lg hover:-translate-y-0.5 transition-all"
        >
          Start Full Screening
          <ArrowRight size={16} />
        </button>
      </section>

      {/* ── How it works ── */}
      <section className="space-y-4">
        <div className="text-center mb-6">
          <h2 className="text-lg font-display font-700 text-slate-800 mb-1">Three-Module Screening</h2>
          <p className="text-sm text-slate-400">Each module runs independently and contributes to the final result</p>
        </div>

        {/* Progress indicator */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {TESTS.map((t, i) => (
            <React.Fragment key={t.label}>
              <div className="flex flex-col items-center gap-1.5">
                <div className={`w-10 h-10 rounded-full bg-gradient-to-br ${t.accent} flex items-center justify-center shadow-sm`}>
                  <t.icon size={16} className="text-white" strokeWidth={2} />
                </div>
                <span className="text-[10px] font-semibold text-slate-500">{i + 1}</span>
              </div>
              {i < TESTS.length - 1 && (
                <div className="w-12 h-px bg-slate-200 mb-3" />
              )}
            </React.Fragment>
          ))}
          <div className="w-12 h-px bg-slate-200 mb-3" />
          <div className="flex flex-col items-center gap-1.5">
            <div className="w-10 h-10 rounded-full bg-gradient-to-br from-slate-600 to-slate-800 flex items-center justify-center shadow-sm">
              <CheckCircle2 size={16} className="text-white" strokeWidth={2} />
            </div>
            <span className="text-[10px] font-semibold text-slate-500">Result</span>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {TESTS.map((t, i) => (
            <div key={t.label} className="card p-5 space-y-4 hover:shadow-card-hover transition-all duration-200">
              <div className="flex items-start justify-between">
                <div className={`w-9 h-9 rounded-xl border flex items-center justify-center ${t.iconBg}`}>
                  <t.icon size={16} strokeWidth={1.75} />
                </div>
                <span className="text-[10px] font-bold text-slate-400 font-mono">STEP {i + 1}</span>
              </div>
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <h3 className="text-sm font-semibold text-slate-800">{t.label}</h3>
                  <span className={t.tagCls}>{t.tag}</span>
                </div>
                <p className="text-xs text-slate-500 leading-relaxed">{t.desc}</p>
              </div>
              <ul className="space-y-1">
                {t.details.map(d => (
                  <li key={d} className="flex items-center gap-2 text-[11px] text-slate-400">
                    <span className="w-1 h-1 rounded-full bg-slate-300 shrink-0" />
                    {d}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      {/* ── CTA ── */}
      <section className="card p-8 bg-gradient-to-br from-brand-600 to-brand-800 border-0 text-white text-center relative overflow-hidden">
        <div className="absolute inset-0 opacity-10"
          style={{ backgroundImage: 'radial-gradient(circle, white 1px, transparent 1px)', backgroundSize: '20px 20px' }} />
        <div className="relative z-10 space-y-4">
          <h2 className="text-xl font-display font-700">Ready to begin?</h2>
          <p className="text-sm text-brand-100 max-w-md mx-auto">
            The full screening takes approximately 5-10 minutes across all three modules.
            Results are stored locally and never leave your device.
          </p>
          <button
            onClick={() => navigate('/screening')}
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-white text-brand-700 font-semibold text-sm rounded-xl hover:bg-brand-50 transition-colors shadow-sm"
          >
            Start Screening <ArrowRight size={14} />
          </button>
        </div>
      </section>

      {/* ── Session history ── */}
      {sessions.length > 0 && (
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-slate-800">Screening History</h2>
              <p className="text-xs text-slate-400 mt-0.5">{sessions.length} test{sessions.length !== 1 ? 's' : ''} completed</p>
            </div>
            <button onClick={() => navigate('/sessions')} className="btn-ghost text-xs">
              View all <ChevronRight size={12} />
            </button>
          </div>

          <div className="space-y-2">
            {sessions.slice(0, 6).map((s, i) => {
              const Icon = TOOL_ICON[s.tool] ?? Activity;
              const risk = getRiskConfig(s.risk);
              return (
                <div key={s.id}
                  className="card px-4 py-3 flex items-center gap-3 animate-fade-up"
                  style={{ animationDelay: `${i * 40}ms`, animationFillMode: 'both' }}
                >
                  <Icon size={14} className="text-slate-400 shrink-0" strokeWidth={1.75} />
                  <span className="text-xs font-medium text-slate-700 capitalize w-20 shrink-0">{s.tool}</span>
                  <span className={`${risk.badge} shrink-0`}>{Math.round(s.risk * 100)}%</span>
                  <div className="flex-1 h-1 bg-slate-100 rounded-full overflow-hidden hidden sm:block">
                    <div className="h-full rounded-full transition-all duration-500"
                      style={{ width: `${s.risk * 100}%`, backgroundColor: risk.color }} />
                  </div>
                  <span className="text-[10px] text-slate-400 font-mono shrink-0">
                    {new Date(s.timestamp).toLocaleDateString()}
                  </span>
                </div>
              );
            })}
          </div>
        </section>
      )}

    </div>
  );
}

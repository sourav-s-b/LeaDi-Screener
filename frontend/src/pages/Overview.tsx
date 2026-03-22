import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Mic, Eye, PenLine, ArrowRight, Activity, CheckCircle2, Clock, AlertTriangle } from 'lucide-react';
import StatCard from '../components/ui/StatCard';
import { apiEndpoints } from '../lib/api';
import { SessionSummary } from '../types';

const MODULES = [
  {
    id:          'dysarthria',
    icon:        Mic,
    label:       'Dysarthria',
    description: 'Upload a WAV recording to detect speech motor disorder indicators using CNN+BiLSTM with attention pooling.',
    accent:      'bg-violet-50 text-violet-600 border-violet-100',
    tagClass:    'badge-blue',
    tag:         'Speech',
    path:        '/dysarthria',
  },
  {
    id:          'dyslexia',
    icon:        Eye,
    label:       'Dyslexia',
    description: 'Run live eye-tracking via webcam to capture fixation and regression patterns for dyslexia screening.',
    accent:      'bg-sky-50 text-sky-600 border-sky-100',
    tagClass:    'badge-blue',
    tag:         'Eye Tracking',
    path:        '/dyslexia',
  },
  {
    id:          'handwriting',
    icon:        PenLine,
    label:       'Handwriting',
    description: 'Analyse a handwriting photo with YOLO-based detection to score reversal and mirror-writing errors.',
    accent:      'bg-emerald-50 text-emerald-600 border-emerald-100',
    tagClass:    'badge-green',
    tag:         'Vision',
    path:        '/handwriting',
  },
];

export default function Overview() {
  const navigate  = useNavigate();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loaded,   setLoaded]   = useState(false);

  useEffect(() => {
    apiEndpoints.sessions.list()
      .then((r) => setSessions(r.data))
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  // Derived stats
  const totalSessions  = sessions.length;
  const highRiskCount  = sessions.filter((s) => s.risk >= 0.65).length;
  const avgRisk        = sessions.length
    ? (sessions.reduce((acc, s) => acc + s.risk, 0) / sessions.length * 100).toFixed(0)
    : '—';
  const lastTool       = sessions[0]?.tool ?? '—';
  const recentSessions = sessions.slice(0, 4);

  const TOOL_ICON: Record<string, React.ElementType> = {
    dysarthria: Mic, dyslexia: Eye, handwriting: PenLine,
  };

  return (
    <div className="space-y-8 animate-fade-up">

      {/* Hero */}
      <div className="card p-8 bg-gradient-to-br from-brand-600 to-brand-800 border-0 text-white overflow-hidden relative">
        <div
          className="absolute inset-0 opacity-10"
          style={{ backgroundImage: 'radial-gradient(circle at 70% 50%, white 1px, transparent 1px)', backgroundSize: '24px 24px' }}
        />
        <div className="relative z-10 max-w-lg">
          <div className="flex items-center gap-2 mb-3">
            <span className="badge bg-white/20 text-white border-white/10 text-[11px]">
              <Activity size={10} /> Research Dashboard
            </span>
          </div>
          <h2 className="text-2xl font-display font-700 mb-2 leading-tight">
            Multimodal Dyslexia &amp; Dysarthria<br />Screening System
          </h2>
          <p className="text-sm text-brand-100 leading-relaxed max-w-sm">
            Three independent AI modules — speech, eye tracking, and handwriting — unified
            for clinical-grade screening and IEEE-targeted evaluation.
          </p>
        </div>
      </div>

      {/* Live stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <StatCard
          label="Total Sessions" value={loaded ? totalSessions : '…'}
          icon={Activity} delay={0}
        />
        <StatCard
          label="Avg Risk Score" value={loaded ? avgRisk : '…'} unit={loaded && avgRisk !== '—' ? '%' : ''}
          icon={CheckCircle2} iconColor="text-emerald-600" delay={80}
        />
        <StatCard
          label="High Risk" value={loaded ? highRiskCount : '…'}
          icon={AlertTriangle} iconColor="text-red-500"
          trendText={highRiskCount > 0 ? `${highRiskCount} need review` : undefined}
          trend={highRiskCount > 0 ? 'up' : 'flat'} delay={160}
        />
        <StatCard
          label="Last Module" value={loaded ? lastTool : '…'}
          icon={Clock} delay={240}
        />
      </div>

      {/* Module cards */}
      <div>
        <h2 className="text-[13px] font-semibold text-slate-500 uppercase tracking-wider mb-4">
          Analysis Modules
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {MODULES.map(({ id, icon: Icon, label, description, accent, tag, tagClass, path }, i) => (
            <button
              key={id}
              onClick={() => navigate(path)}
              className="card p-6 text-left group hover:shadow-card-hover transition-all duration-200 animate-fade-up cursor-pointer"
              style={{ animationDelay: `${i * 80}ms`, animationFillMode: 'both' }}
            >
              <div className={`w-10 h-10 rounded-xl border flex items-center justify-center mb-4 ${accent}`}>
                <Icon size={18} strokeWidth={1.75} />
              </div>
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-semibold text-slate-900">{label}</h3>
                <span className={tagClass}>{tag}</span>
              </div>
              <p className="text-xs text-slate-500 leading-relaxed mb-4">{description}</p>
              <div className="flex items-center gap-1 text-xs font-semibold text-brand-600 group-hover:gap-2 transition-all">
                Open module <ArrowRight size={12} />
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Recent sessions inline */}
      {recentSessions.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-[13px] font-semibold text-slate-500 uppercase tracking-wider">
              Recent Activity
            </h2>
            <button onClick={() => navigate('/sessions')} className="btn-ghost text-xs">
              View all <ArrowRight size={11} />
            </button>
          </div>
          <div className="space-y-2">
            {recentSessions.map((s, i) => {
              const Icon      = TOOL_ICON[s.tool] ?? Activity;
              const riskPct   = Math.round(s.risk * 100);
              const riskColor = s.risk < 0.35 ? '#10b981' : s.risk < 0.65 ? '#f59e0b' : '#ef4444';
              const badgeCls  = s.risk < 0.35 ? 'badge-green' : s.risk < 0.65 ? 'badge-amber' : 'badge-red';

              return (
                <div
                  key={s.id}
                  className="card px-5 py-3.5 flex items-center gap-4 animate-fade-up"
                  style={{ animationDelay: `${i * 40}ms`, animationFillMode: 'both' }}
                >
                  <Icon size={15} className="text-slate-400 shrink-0" strokeWidth={1.75} />
                  <span className="text-sm font-medium text-slate-700 capitalize w-24 shrink-0">{s.tool}</span>
                  <span className={`${badgeCls} shrink-0`}>{riskPct}% risk</span>
                  <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden hidden sm:block">
                    <div className="h-full rounded-full" style={{ width: `${riskPct}%`, backgroundColor: riskColor }} />
                  </div>
                  <span className="text-[11px] text-slate-400 shrink-0">
                    {new Date(s.timestamp).toLocaleDateString()}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

    </div>
  );
}

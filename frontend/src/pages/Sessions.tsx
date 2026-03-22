import React, { useEffect, useState } from 'react';
import { Activity, Mic, Eye, PenLine, Trash2 } from 'lucide-react';
import { LoadingSpinner, EmptyState } from '../components/ui/Feedback';
import { apiEndpoints } from '../lib/api';
import { SessionSummary } from '../types';
import { getRiskConfig } from '../components/ui/RiskMeter';

const TOOL_META: Record<string, { icon: React.ElementType; label: string; color: string }> = {
  dysarthria:  { icon: Mic,     label: 'Dysarthria',  color: 'bg-violet-50 text-violet-600 border-violet-100'   },
  dyslexia:    { icon: Eye,     label: 'Dyslexia',    color: 'bg-sky-50 text-sky-600 border-sky-100'             },
  handwriting: { icon: PenLine, label: 'Handwriting', color: 'bg-emerald-50 text-emerald-600 border-emerald-100' },
};

export default function SessionsPage() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading,  setLoading]  = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const res = await apiEndpoints.sessions.list();
      setSessions(res.data);
    } catch {}
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const del = async (id: string) => {
    try {
      await apiEndpoints.sessions.delete(id);
      setSessions(s => s.filter(x => x.id !== id));
    } catch {}
  };

  return (
    <div className="max-w-3xl mx-auto space-y-5 animate-fade-up">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-800">All Sessions</h2>
          <p className="text-xs text-slate-400 mt-0.5">{sessions.length} total</p>
        </div>
        <button onClick={load} className="btn-secondary">Refresh</button>
      </div>

      {loading && <div className="flex justify-center py-16"><LoadingSpinner size={24} /></div>}

      {!loading && sessions.length === 0 && (
        <EmptyState icon={Activity} title="No sessions yet"
          body="Complete a screening to see results here." />
      )}

      {!loading && sessions.length > 0 && (
        <div className="space-y-3">
          {sessions.map((s, i) => {
            const meta = TOOL_META[s.tool] ?? TOOL_META.dysarthria;
            const risk = getRiskConfig(s.risk);
            const Icon = meta.icon;
            return (
              <div key={s.id}
                className="card px-5 py-4 flex items-center gap-4 hover:shadow-card-hover transition-all duration-150 animate-fade-up"
                style={{ animationDelay: `${i * 40}ms`, animationFillMode: 'both' }}>
                <div className={`w-9 h-9 rounded-xl border shrink-0 flex items-center justify-center ${meta.color}`}>
                  <Icon size={15} strokeWidth={1.75} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-sm font-medium text-slate-800">{meta.label}</span>
                    <span className={`badge ${risk.badge}`}>{Math.round(s.risk * 100)}% risk</span>
                  </div>
                  <p className="text-xs text-slate-400">
                    {new Date(s.timestamp).toLocaleString()} · {s.label.replace(/_/g, ' ')}
                  </p>
                </div>
                <div className="hidden sm:flex flex-col items-end gap-1 w-24 shrink-0">
                  <div className="w-full h-1.5 bg-slate-100 rounded-full overflow-hidden">
                    <div className="h-full rounded-full"
                      style={{ width: `${s.risk * 100}%`, backgroundColor: risk.color }} />
                  </div>
                </div>
                <button onClick={() => del(s.id)}
                  className="btn-ghost p-2 text-slate-300 hover:text-red-400">
                  <Trash2 size={13} />
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

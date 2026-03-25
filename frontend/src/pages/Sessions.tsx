import React, { useEffect, useState } from 'react';
<<<<<<< HEAD
import { Activity, Mic, Eye, PenLine, Trash2, ChevronDown, ChevronUp } from 'lucide-react';
=======
import { Activity, Mic, Eye, PenLine, Trash2 } from 'lucide-react';
>>>>>>> 33f15c0dc22504283b346af414bc23b2dc1340c0
import { LoadingSpinner, EmptyState } from '../components/ui/Feedback';
import { apiEndpoints } from '../lib/api';
import { SessionSummary } from '../types';
import { getRiskConfig } from '../components/ui/RiskMeter';

<<<<<<< HEAD
const TOOL_META: Record<string, { icon: React.ElementType; label: string; color: string; order: number }> = {
  handwriting: { icon: PenLine, label: 'Handwriting', color: 'bg-emerald-50 text-emerald-600 border-emerald-100', order: 0 },
  dysarthria:  { icon: Mic,     label: 'Speech',      color: 'bg-violet-50 text-violet-600 border-violet-100',   order: 1 },
  dyslexia:    { icon: Eye,     label: 'Eye Tracking', color: 'bg-sky-50 text-sky-600 border-sky-100',           order: 2 },
};

interface SessionGroup {
  id:        string;          // first session id used as group key
  sessions:  SessionSummary[];
  startedAt: string;
  tools:     string[];
  avgRisk:   number;
}

/** Group sessions into screening runs.
 *  Sessions within 30 minutes of each other are considered the same run. */
function groupSessions(sessions: SessionSummary[]): SessionGroup[] {
  if (!sessions.length) return [];

  // Sort oldest-first for grouping, then reverse display
  const sorted = [...sessions].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  );

  const groups: SessionGroup[] = [];
  let current: SessionSummary[] = [sorted[0]];

  for (let i = 1; i < sorted.length; i++) {
    const prev = new Date(sorted[i - 1].timestamp).getTime();
    const curr = new Date(sorted[i].timestamp).getTime();
    const gap  = (curr - prev) / 60000; // minutes

    if (gap <= 30) {
      current.push(sorted[i]);
    } else {
      groups.push(makeGroup(current));
      current = [sorted[i]];
    }
  }
  groups.push(makeGroup(current));

  // Latest first
  return groups.reverse();
}

function makeGroup(sessions: SessionSummary[]): SessionGroup {
  const tools   = sessions.map(s => s.tool);
  const avgRisk = sessions.reduce((a, s) => a + s.risk, 0) / sessions.length;
  return {
    id:        sessions[0].id,
    sessions:  sessions.sort((a, b) =>
      (TOOL_META[a.tool]?.order ?? 9) - (TOOL_META[b.tool]?.order ?? 9)),
    startedAt: sessions[0].timestamp,
    tools,
    avgRisk,
  };
}

function groupLabel(tools: string[]): string {
  const all = ['handwriting', 'dysarthria', 'dyslexia'];
  if (all.every(t => tools.includes(t))) return 'Full Screening';
  return tools.map(t => TOOL_META[t]?.label ?? t).join(' + ');
}

export default function SessionsPage() {
  const [sessions,  setSessions]  = useState<SessionSummary[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [expanded,  setExpanded]  = useState<Set<string>>(new Set());
=======
const TOOL_META: Record<string, { icon: React.ElementType; label: string; color: string }> = {
  dysarthria:  { icon: Mic,     label: 'Dysarthria',  color: 'bg-violet-50 text-violet-600 border-violet-100'   },
  dyslexia:    { icon: Eye,     label: 'Dyslexia',    color: 'bg-sky-50 text-sky-600 border-sky-100'             },
  handwriting: { icon: PenLine, label: 'Handwriting', color: 'bg-emerald-50 text-emerald-600 border-emerald-100' },
};

export default function SessionsPage() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading,  setLoading]  = useState(true);
>>>>>>> 33f15c0dc22504283b346af414bc23b2dc1340c0

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

<<<<<<< HEAD
  const delGroup = async (group: SessionGroup) => {
    for (const s of group.sessions) {
      try { await apiEndpoints.sessions.delete(s.id); } catch {}
    }
    setSessions(prev => prev.filter(s => !group.sessions.some(g => g.id === s.id)));
  };

  const toggle = (id: string) =>
    setExpanded(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const groups = groupSessions(sessions);

=======
>>>>>>> 33f15c0dc22504283b346af414bc23b2dc1340c0
  return (
    <div className="max-w-3xl mx-auto space-y-5 animate-fade-up">
      <div className="flex items-center justify-between">
        <div>
<<<<<<< HEAD
          <h2 className="text-sm font-semibold text-slate-800">Screening History</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            {groups.length} session{groups.length !== 1 ? 's' : ''} · {sessions.length} test{sessions.length !== 1 ? 's' : ''}
          </p>
=======
          <h2 className="text-sm font-semibold text-slate-800">All Sessions</h2>
          <p className="text-xs text-slate-400 mt-0.5">{sessions.length} total</p>
>>>>>>> 33f15c0dc22504283b346af414bc23b2dc1340c0
        </div>
        <button onClick={load} className="btn-secondary">Refresh</button>
      </div>

      {loading && <div className="flex justify-center py-16"><LoadingSpinner size={24} /></div>}

<<<<<<< HEAD
      {!loading && groups.length === 0 && (
=======
      {!loading && sessions.length === 0 && (
>>>>>>> 33f15c0dc22504283b346af414bc23b2dc1340c0
        <EmptyState icon={Activity} title="No sessions yet"
          body="Complete a screening to see results here." />
      )}

<<<<<<< HEAD
      {!loading && groups.map((group, gi) => {
        const isOpen = expanded.has(group.id);
        const cfg    = getRiskConfig(group.avgRisk);
        const label  = groupLabel(group.tools);
        const isFull = group.tools.length === 3;

        return (
          <div key={group.id}
            className="card overflow-hidden animate-fade-up"
            style={{ animationDelay: `${gi * 60}ms`, animationFillMode: 'both' }}>

            {/* Group header */}
            <div
              className="px-5 py-4 flex items-center gap-4 cursor-pointer hover:bg-slate-50 transition-colors"
              onClick={() => toggle(group.id)}
            >
              {/* Module icons */}
              <div className="flex -space-x-1.5 shrink-0">
                {group.sessions.map(s => {
                  const m = TOOL_META[s.tool] ?? TOOL_META.handwriting;
                  return (
                    <div key={s.id}
                      className={`w-7 h-7 rounded-full border-2 border-white flex items-center justify-center ${m.color}`}>
                      <m.icon size={11} strokeWidth={2} />
                    </div>
                  );
                })}
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-semibold text-slate-800">{label}</span>
                  {isFull && <span className="badge badge-green text-[10px]">Full</span>}
                  <span className={`badge ${cfg.badge}`}>
                    {Math.round(group.avgRisk * 100)}% avg risk
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-0.5">
                  {new Date(group.startedAt).toLocaleString()}
                  {group.sessions.length > 1 && ` · ${group.sessions.length} tests`}
                </p>
              </div>

              {/* Risk bar */}
              <div className="hidden sm:block w-20 shrink-0">
                <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                  <div className="h-full rounded-full transition-all"
                    style={{ width: `${group.avgRisk * 100}%`, backgroundColor: cfg.color }} />
                </div>
              </div>

              {/* Delete group */}
              <button
                onClick={e => { e.stopPropagation(); delGroup(group); }}
                className="btn-ghost p-1.5 text-slate-300 hover:text-red-400 shrink-0">
                <Trash2 size={13} />
              </button>

              {isOpen
                ? <ChevronUp size={14} className="text-slate-400 shrink-0" />
                : <ChevronDown size={14} className="text-slate-400 shrink-0" />}
            </div>

            {/* Expanded: individual tests */}
            {isOpen && (
              <div className="border-t border-slate-100">
                {group.sessions.map((s, si) => {
                  const meta = TOOL_META[s.tool] ?? TOOL_META.handwriting;
                  const risk = getRiskConfig(s.risk);
                  return (
                    <div key={s.id}
                      className="flex items-center gap-3 px-5 py-3 border-b border-slate-50 last:border-0 hover:bg-slate-50/50 transition-colors">
                      <div className={`w-7 h-7 rounded-lg border flex items-center justify-center shrink-0 ${meta.color}`}>
                        <meta.icon size={12} strokeWidth={1.75} />
                      </div>
                      <span className="text-xs font-medium text-slate-700 w-24 shrink-0">{meta.label}</span>
                      <span className={`badge ${risk.badge} shrink-0`}>{Math.round(s.risk * 100)}%</span>
                      <div className="flex-1 h-1 bg-slate-100 rounded-full overflow-hidden hidden sm:block">
                        <div className="h-full rounded-full"
                          style={{ width: `${s.risk * 100}%`, backgroundColor: risk.color }} />
                      </div>
                      <span className="text-[11px] text-slate-400 shrink-0">
                        {s.label.replace(/_/g, ' ')}
                      </span>
                      <button onClick={() => del(s.id)}
                        className="btn-ghost p-1 text-slate-300 hover:text-red-400 shrink-0">
                        <Trash2 size={11} />
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      })}
=======
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
>>>>>>> 33f15c0dc22504283b346af414bc23b2dc1340c0
    </div>
  );
}

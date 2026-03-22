import React, { useState, useRef, useCallback, useEffect } from 'react';
import { Eye, CheckCircle2, AlertCircle, RotateCcw, XCircle } from 'lucide-react';
import ResultCard from '../components/ui/ResultCard';
import { LoadingSpinner, ErrorBanner } from '../components/ui/Feedback';
import { api } from '../lib/api';
import { DyslexiaResult } from '../types';

interface Props {
  onComplete: (risk: number, label: string, result: DyslexiaResult) => void;
}

type Phase = 'idle' | 'launching' | 'calibrating' | 'recording' | 'done' | 'error';

const PHASE_LABELS: Record<Phase, string> = {
  idle:        '',
  launching:   'Opening eye-tracking window…',
  calibrating: 'Calibrating — follow the on-screen instructions',
  recording:   'Reading session in progress…',
  done:        'Analysis complete',
  error:       'An error occurred',
};

export default function DyslexiaTest({ onComplete }: Props) {
  const [phase,    setPhase]   = useState<Phase>('idle');
  const [result,   setResult]  = useState<DyslexiaResult | null>(null);
  const [error,    setError]   = useState<string | null>(null);
  const [elapsed,  setElapsed] = useState(0);
  const [duration, setDuration]= useState(30);
  const [runSt,    setRunSt]   = useState('idle');

  const pollRef  = useRef<NodeJS.Timeout | null>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const sessionCountRef = useRef(0);

  const stopAll = useCallback(() => {
    if (pollRef.current)  clearInterval(pollRef.current);
    if (timerRef.current) clearInterval(timerRef.current);
  }, []);

  useEffect(() => () => stopAll(), [stopAll]);

  const startPolling = useCallback(() => {
    // Rough phase estimation from elapsed time
    timerRef.current = setInterval(() => {
      setElapsed(n => {
        // Calibration ≈ 10s, then recording
        if (n < 12)  setPhase(p => p === 'launching' || p === 'calibrating' ? 'calibrating' : p);
        else         setPhase(p => p === 'calibrating' ? 'recording' : p);
        return n + 1;
      });
    }, 1000);

    pollRef.current = setInterval(async () => {
      try {
        // Runner status
        const st = (await api.get('/launch/status')).data.dyslexia as string;
        setRunSt(st);

        if (st.startsWith('error')) {
          stopAll();
          setPhase('error');
          setError('Eye-tracking runner exited with an error. Check the terminal window for details.');
          return;
        }

        // New session?
        const sessions = ((await api.get('/sessions')).data as any[]).filter(s => s.tool === 'dyslexia');
        if (sessions.length > sessionCountRef.current) {
          const full = await api.get(`/sessions/${sessions[0].id}`);
          stopAll();
          setResult(full.data.result as DyslexiaResult);
          setPhase('done');
        }
      } catch {}
    }, 2500);

    setTimeout(() => {
      stopAll();
      setPhase(p => (p === 'error' || p === 'done') ? p : 'error');
      setError(e => e ?? 'Timed out after 10 minutes.');
    }, 10 * 60 * 1000);
  }, [stopAll]);

  const launch = async () => {
    try {
      const r = await api.get('/sessions');
      sessionCountRef.current = (r.data as any[]).filter(s => s.tool === 'dyslexia').length;
    } catch { sessionCountRef.current = 0; }

    setPhase('launching'); setError(null); setResult(null); setElapsed(0);

    try {
      await api.post('/launch/dyslexia', { duration, camera: 0 });
      setPhase('calibrating');
      startPolling();
    } catch (e: any) {
      setPhase('error');
      setError(e.response?.data?.detail ?? e.message);
    }
  };

  const cancel = async () => {
    stopAll(); setPhase('idle');
    try { await api.post('/launch/cancel/dyslexia', {}); } catch {}
  };

  const reset = () => { stopAll(); setPhase('idle'); setResult(null); setError(null); setElapsed(0); };

  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;

  const progressPct = () => {
    if (phase === 'calibrating') return Math.min(elapsed / 12 * 30, 30);
    if (phase === 'recording')   return 30 + Math.min((elapsed - 12) / duration * 70, 70);
    if (phase === 'done')        return 100;
    return 0;
  };

  return (
    <div className="max-w-xl mx-auto space-y-5 animate-fade-up">

      {/* Info */}
      <div className="card p-5 flex gap-4 items-start">
        <div className="w-9 h-9 rounded-xl bg-sky-50 border border-sky-100 flex items-center justify-center shrink-0">
          <Eye size={16} className="text-sky-600" />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-slate-800 mb-1">Eye-Tracking Dyslexia Test</h2>
          <p className="text-xs text-slate-500 leading-relaxed">
            Calibration and reading session run in a separate OpenCV window on your desktop,
            launched automatically. The result posts back here when the session ends.
          </p>
        </div>
      </div>

      {/* Requirements */}
      <div className="flex items-start gap-3 p-3 bg-sky-50 border border-sky-100 rounded-xl">
        <AlertCircle size={14} className="text-sky-500 shrink-0 mt-0.5" />
        <div className="text-xs text-sky-700 space-y-0.5">
          <p><strong>Requires:</strong> <code className="bg-sky-100 px-1 rounded font-mono">pip install mediapipe opencv-python</code></p>
          <p><strong>Model file:</strong> <code className="bg-sky-100 px-1 rounded font-mono">face_landmarker.task</code> in the backend folder</p>
          <p>Sit 50–70 cm from screen · good lighting · head still during calibration</p>
        </div>
      </div>

      {/* Duration setting */}
      {phase === 'idle' && (
        <div className="flex items-center gap-3 card p-4">
          <span className="text-xs text-slate-600 shrink-0">Recording duration:</span>
          {[20, 30, 45].map(d => (
            <button key={d} onClick={() => setDuration(d)}
              className={['px-3 py-1.5 text-xs font-medium rounded-lg border transition-all',
                duration === d ? 'bg-brand-50 border-brand-300 text-brand-700' : 'bg-white border-slate-200 text-slate-500',
              ].join(' ')}>
              {d}s
            </button>
          ))}
        </div>
      )}

      {/* ── IDLE ── */}
      {phase === 'idle' && (
        <div className="card p-8 flex flex-col items-center gap-5 text-center">
          <div className="w-16 h-16 rounded-2xl bg-sky-50 border border-sky-100 flex items-center justify-center">
            <Eye size={28} className="text-sky-400" strokeWidth={1.5} />
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-900">Start Eye-Tracking Session</p>
            <p className="text-xs text-slate-400 mt-1 max-w-xs">
              Clicking below will open a calibration + reading window on your desktop.
              Follow the on-screen instructions — takes about {10 + duration} seconds total.
            </p>
          </div>
          <div className="grid grid-cols-3 gap-2 w-full text-center">
            {[['~10s', 'Calibration', 'Follow range-detection prompts'],
              [`${duration}s`, 'Read passage', 'Natural reading pace'],
              ['Auto', 'Result', 'Posted here instantly'],
            ].map(([t, h, d]) => (
              <div key={h} className="p-3 bg-slate-50 rounded-xl">
                <p className="text-xs font-bold text-brand-600 mb-0.5">{t}</p>
                <p className="text-xs font-semibold text-slate-700">{h}</p>
                <p className="text-[10px] text-slate-400">{d}</p>
              </div>
            ))}
          </div>
          <button onClick={launch} className="btn-primary px-6 py-2.5">
            <Eye size={15} /> Launch Eye-Tracking Window
          </button>
        </div>
      )}

      {/* ── IN PROGRESS ── */}
      {(phase === 'launching' || phase === 'calibrating' || phase === 'recording') && (
        <div className="card p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <LoadingSpinner size={16} />
              <p className="text-sm font-semibold text-slate-700">{PHASE_LABELS[phase]}</p>
            </div>
            <span className="text-xs font-mono text-slate-400">{fmt(elapsed)}</span>
          </div>

          {/* Steps */}
          <div className="flex items-center gap-2">
            {[['Cal', 'calibrating'], ['Read', 'recording'], ['Done', 'done']].map(([label, p], i) => {
              const states = ['calibrating', 'recording', 'done'] as string[];
              const idx    = states.indexOf(phase);
              const done   = i < idx;
              const active = i === idx;
              return (
                <React.Fragment key={label}>
                  <div className={['flex flex-col items-center gap-1',
                    active ? 'opacity-100' : done ? 'opacity-60' : 'opacity-30'].join(' ')}>
                    <div className={['w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold',
                      active ? 'bg-brand-500 text-white ring-2 ring-brand-200' :
                      done   ? 'bg-emerald-500 text-white' : 'bg-slate-200 text-slate-400',
                    ].join(' ')}>
                      {done && !active ? '✓' : i + 1}
                    </div>
                    <span className="text-[10px] text-slate-500">{label}</span>
                  </div>
                  {i < 2 && (
                    <div className={`flex-1 h-0.5 mb-4 ${done ? 'bg-emerald-300' : 'bg-slate-200'}`} />
                  )}
                </React.Fragment>
              );
            })}
          </div>

          {/* Overall progress bar */}
          <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
            <div className="h-full bg-brand-500 rounded-full transition-all duration-1000"
              style={{ width: `${progressPct()}%` }} />
          </div>

          <div className="flex items-center justify-between text-[11px] text-slate-400">
            <span>Desktop window is active — complete the session there</span>
            <button onClick={cancel} className="flex items-center gap-1 hover:text-red-500 transition-colors">
              <XCircle size={12} /> Cancel
            </button>
          </div>
        </div>
      )}

      {/* ── ERROR ── */}
      {phase === 'error' && error && (
        <div className="space-y-3">
          <ErrorBanner message={error} />
          <button onClick={reset} className="btn-secondary w-full justify-center">
            <RotateCcw size={13} /> Try again
          </button>
        </div>
      )}

      {/* ── DONE ── */}
      {phase === 'done' && result && (
        <div className="space-y-4 animate-fade-up">
          <div className="flex items-center gap-2 p-3 bg-emerald-50 border border-emerald-100 rounded-xl">
            <CheckCircle2 size={14} className="text-emerald-500" />
            <p className="text-xs font-medium text-emerald-700">Eye-tracking session complete — result received</p>
          </div>
          <ResultCard
            risk={result.risk}
            label={result.label === 'dyslexic' ? 'Dyslexia indicators present' : 'No dyslexia indicators'}
            confidence={result.confidence}
            meta={[
              { key: 'Fixations',       value: result.n_fixations },
              { key: 'Regressions',     value: result.n_regressions },
              { key: 'Regression rate', value: `${(result.regression_rate * 100).toFixed(1)}%` },
              { key: 'Duration',        value: `${result.recording_duration.toFixed(1)}s` },
            ]}
            timestamp={new Date().toISOString()}
          />
          <button onClick={() => onComplete(result.risk, result.label, result)}
            className="btn-primary w-full justify-center py-2.5">
            Continue to Final Report →
          </button>
        </div>
      )}
    </div>
  );
}

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Mic, CheckCircle2, AlertCircle, RotateCcw, Upload, XCircle } from 'lucide-react';
import ResultCard from '../components/ui/ResultCard';
import { LoadingSpinner, ErrorBanner } from '../components/ui/Feedback';
import { api, apiEndpoints } from '../lib/api';
import { DysarthriaResult, Status } from '../types';

interface Props {
  onComplete: (risk: number, label: string, result: DysarthriaResult) => void;
}

type Mode  = 'desktop' | 'file';
type Phase = 'idle' | 'launching' | 'recording' | 'done' | 'error';

export default function DysarthriaTest({ onComplete }: Props) {
  const [mode,     setMode]    = useState<Mode>('desktop');
  const [phase,    setPhase]   = useState<Phase>('idle');
  const [gender,   setGender]  = useState<'male' | 'female'>('male');
  const [result,   setResult]  = useState<DysarthriaResult | null>(null);
  const [error,    setError]   = useState<string | null>(null);
  const [elapsed,  setElapsed] = useState(0);
  const [runnerStatus, setRunnerStatus] = useState('idle');

  // File upload
  const [fileStatus, setFileStatus] = useState<Status>('idle');
  const [fileResult, setFileResult] = useState<DysarthriaResult | null>(null);
  const [fileError,  setFileError]  = useState<string | null>(null);

  const pollRef  = useRef<NodeJS.Timeout | null>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const sessionCountRef = useRef(0);

  const stopAll = useCallback(() => {
    if (pollRef.current)  clearInterval(pollRef.current);
    if (timerRef.current) clearInterval(timerRef.current);
  }, []);

  useEffect(() => () => stopAll(), [stopAll]);

  // Poll /launch/status to show runner state, and /sessions for result
  const startPolling = useCallback(() => {
    timerRef.current = setInterval(() => setElapsed(n => n + 1), 1000);

    pollRef.current = setInterval(async () => {
      try {
        // Check runner status
        const statusRes = await api.get('/launch/status');
        const st = statusRes.data.dysarthria as string;
        setRunnerStatus(st);

        if (st.startsWith('error')) {
          stopAll();
          setPhase('error');
          setError(`Runner exited with an error. Check the terminal window for details.`);
          return;
        }

        // Check for new session result
        const sessRes = await api.get('/sessions');
        const sessions = (sessRes.data as any[]).filter(s => s.tool === 'dysarthria');
        if (sessions.length > sessionCountRef.current) {
          const latest = sessions[0];
          const full   = await api.get(`/sessions/${latest.id}`);
          stopAll();
          setResult(full.data.result as DysarthriaResult);
          setPhase('done');
        }
      } catch {}
    }, 2000);

    setTimeout(() => {
      stopAll();
      setPhase(p => p === 'recording' ? 'error' : p);
      setError(e => e ?? 'Timed out after 5 minutes.');
    }, 5 * 60 * 1000);
  }, [stopAll]);

  const launch = async () => {
    // Snapshot session count
    try {
      const r = await api.get('/sessions');
      sessionCountRef.current = (r.data as any[]).filter(s => s.tool === 'dysarthria').length;
    } catch { sessionCountRef.current = 0; }

    setPhase('launching');
    setError(null);
    setResult(null);
    setElapsed(0);

    try {
      await api.post('/launch/dysarthria', { gender });
      setPhase('recording');
      startPolling();
    } catch (e: any) {
      setPhase('error');
      setError(e.response?.data?.detail ?? e.message);
    }
  };

  const cancel = async () => {
    stopAll();
    setPhase('idle');
    try { await api.post('/launch/cancel/dysarthria', {}); } catch {}
  };

  const reset = () => {
    stopAll();
    setPhase('idle'); setResult(null); setError(null); setElapsed(0);
  };

  const handleFileUpload = async (file: File) => {
    setFileStatus('loading'); setFileResult(null); setFileError(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('gender', gender);
      const res = await apiEndpoints.dysarthria.predict_file(fd);
      setFileResult(res.data); setFileStatus('success');
    } catch (e: any) {
      setFileError(e.response?.data?.detail ?? e.message);
      setFileStatus('error');
    }
  };

  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;

  const statusDot = (s: string) =>
    s === 'running' ? 'bg-emerald-400 animate-pulse' :
    s === 'idle'    ? 'bg-slate-300' :
    s.startsWith('error') ? 'bg-red-400' : 'bg-emerald-500';

  return (
    <div className="max-w-xl mx-auto space-y-5 animate-fade-up">

      {/* Header */}
      <div className="card p-5 flex gap-4 items-start">
        <div className="w-9 h-9 rounded-xl bg-violet-50 border border-violet-100 flex items-center justify-center shrink-0">
          <Mic size={16} className="text-violet-600" />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-slate-800 mb-1">Speech Dysarthria Test</h2>
          <p className="text-xs text-slate-500 leading-relaxed">
            Records via your system microphone at 16kHz PCM — identical to the TORGO training format.
            A small recording window will open on your desktop automatically.
          </p>
        </div>
      </div>

      {/* Mode tabs */}
      <div className="flex gap-1 p-1 bg-slate-100 rounded-xl">
        {(['desktop', 'file'] as Mode[]).map(m => (
          <button key={m} onClick={() => { setMode(m); reset(); setFileStatus('idle'); }}
            className={['flex-1 py-2 text-sm font-medium rounded-lg transition-all',
              mode === m ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-700',
            ].join(' ')}>
            {m === 'desktop' ? '🖥  Record via Desktop' : '📁  Upload WAV File'}
          </button>
        ))}
      </div>

      {/* Gender selector */}
      <div className="flex gap-2 items-center">
        <span className="text-xs text-slate-500">Speaker gender:</span>
        {(['male','female'] as const).map(g => (
          <button key={g} onClick={() => setGender(g)}
            className={['flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all',
              gender === g ? 'bg-brand-50 border-brand-300 text-brand-700' : 'bg-white border-slate-200 text-slate-500 hover:border-slate-300',
            ].join(' ')}>
            {g.charAt(0).toUpperCase() + g.slice(1)}
          </button>
        ))}
      </div>

      {/* ── DESKTOP MODE ── */}
      {mode === 'desktop' && (
        <>
          {phase === 'idle' && (
            <div className="card p-8 flex flex-col items-center gap-4 text-center">
              <div className="w-14 h-14 rounded-2xl bg-violet-50 border border-violet-100 flex items-center justify-center">
                <Mic size={26} className="text-violet-400" strokeWidth={1.5} />
              </div>
              <div>
                <p className="text-sm font-semibold text-slate-800">Ready to record</p>
                <p className="text-xs text-slate-400 mt-1 max-w-xs">
                  A small recording window will open on your desktop. Record for up to 12 seconds,
                  then the result appears here automatically.
                </p>
              </div>
              <button onClick={launch} className="btn-primary px-6 py-2.5">
                <Mic size={15} /> Launch Recording Window
              </button>
            </div>
          )}

          {phase === 'launching' && (
            <div className="card p-8 flex flex-col items-center gap-3">
              <LoadingSpinner size={26} />
              <p className="text-sm font-medium text-slate-600">Opening recording window…</p>
            </div>
          )}

          {phase === 'recording' && (
            <div className="card p-6 space-y-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${statusDot(runnerStatus)}`} />
                  <p className="text-sm font-semibold text-slate-700">
                    {runnerStatus === 'running' ? 'Recording window is open' : 'Runner ' + runnerStatus}
                  </p>
                </div>
                <span className="text-xs font-mono text-slate-400">{fmt(elapsed)}</span>
              </div>
              <p className="text-xs text-slate-500">
                Use the recording window on your desktop. When you stop and the analysis finishes,
                the result will appear here automatically.
              </p>
              <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                <div className="h-full bg-brand-400 rounded-full animate-pulse-slow" style={{ width: '60%' }} />
              </div>
              <button onClick={cancel} className="btn-secondary text-xs w-full justify-center">
                <XCircle size={13} /> Cancel
              </button>
            </div>
          )}

          {phase === 'error' && error && (
            <div className="space-y-3">
              <ErrorBanner message={error} />
              <button onClick={reset} className="btn-secondary w-full justify-center">
                <RotateCcw size={13} /> Try again
              </button>
            </div>
          )}

          {phase === 'done' && result && (
            <div className="space-y-4 animate-fade-up">
              <div className="flex items-center gap-2 p-3 bg-emerald-50 border border-emerald-100 rounded-xl">
                <CheckCircle2 size={14} className="text-emerald-500" />
                <p className="text-xs font-medium text-emerald-700">Recording analysed and received</p>
              </div>
              <ResultCard
                risk={result.risk}
                label={result.label === 'dysarthria' ? 'Dysarthria detected' : 'No dysarthria detected'}
                confidence={result.confidence}
                meta={[
                  { key: 'Windows', value: result.n_chunks },
                  { key: 'Avg risk', value: `${(result.risk * 100).toFixed(1)}%` },
                ]}
                timestamp={new Date().toISOString()}
              />
              {result.chunk_risks?.length > 1 && (
                <div className="card p-4">
                  <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-3">Per-window risk</p>
                  <div className="space-y-2">
                    {result.chunk_risks.map((r, i) => (
                      <div key={i} className="flex items-center gap-3">
                        <span className="text-[11px] font-mono text-slate-400 w-8">W{i+1}</span>
                        <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                          <div className="h-full rounded-full transition-all duration-700"
                            style={{ width:`${r*100}%`, backgroundColor:r<0.35?'#10b981':r<0.65?'#f59e0b':'#ef4444', transitionDelay:`${i*60}ms`}} />
                        </div>
                        <span className="text-[11px] font-mono text-slate-500 w-9 text-right">{(r*100).toFixed(0)}%</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <button onClick={() => onComplete(result.risk, result.label, result)}
                className="btn-primary w-full justify-center py-2.5">
                Continue to Eye Tracking →
              </button>
            </div>
          )}
        </>
      )}

      {/* ── FILE UPLOAD MODE ── */}
      {mode === 'file' && (
        <div className="space-y-4">
          <div className="flex items-start gap-3 p-3 bg-amber-50 border border-amber-100 rounded-xl">
            <AlertCircle size={14} className="text-amber-500 shrink-0 mt-0.5" />
            <p className="text-xs text-amber-700">
              <strong>WAV / FLAC / OGG only.</strong> 16kHz PCM recommended for best accuracy.
            </p>
          </div>

          <label className={['flex flex-col items-center gap-3 border-2 border-dashed rounded-xl py-8 px-6 cursor-pointer transition-all',
            fileStatus==='success'?'border-brand-200 bg-brand-50/30':'border-slate-200 hover:border-brand-300 hover:bg-brand-50/20',
          ].join(' ')}>
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${fileStatus==='success'?'bg-brand-100':'bg-slate-100'}`}>
              <Upload size={17} className={fileStatus==='success'?'text-brand-600':'text-slate-400'} />
            </div>
            <div className="text-center">
              <p className="text-sm font-medium text-slate-700">Drop a WAV / FLAC / OGG file</p>
              <p className="text-xs text-slate-400 mt-0.5">16kHz PCM · max 50 MB</p>
            </div>
            <input type="file" accept=".wav,.flac,.ogg" className="hidden"
              onChange={e => { const f = e.target.files?.[0]; if (f) handleFileUpload(f); }} />
          </label>

          {fileStatus === 'loading' && (
            <div className="card p-5 flex items-center gap-3">
              <LoadingSpinner size={20} />
              <p className="text-sm text-slate-600">Analysing…</p>
            </div>
          )}
          {fileStatus === 'error' && fileError && <ErrorBanner message={fileError} />}
          {fileStatus === 'success' && fileResult && (
            <div className="space-y-4 animate-fade-up">
              <ResultCard
                risk={fileResult.risk}
                label={fileResult.label === 'dysarthria' ? 'Dysarthria detected' : 'No dysarthria detected'}
                confidence={fileResult.confidence}
                meta={[{ key: 'Windows', value: fileResult.n_chunks }]}
                timestamp={new Date().toISOString()}
              />
              <button onClick={() => onComplete(fileResult.risk, fileResult.label, fileResult)}
                className="btn-primary w-full justify-center py-2.5">
                Continue to Eye Tracking →
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

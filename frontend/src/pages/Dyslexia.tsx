import React, { useState } from 'react';
import { Eye, Camera, AlertCircle } from 'lucide-react';
import ResultCard from '../components/ui/ResultCard';
import { LoadingSpinner, ErrorBanner } from '../components/ui/Feedback';
import { apiEndpoints } from '../lib/api';
import { DyslexiaResult, Status } from '../types';

type Mode = 'idle' | 'calibrating' | 'recording' | 'done';

export default function DyslexiaPage() {
  const [mode, setMode]     = useState<Mode>('idle');
  const [status, setStatus] = useState<Status>('idle');
  const [result, setResult] = useState<DyslexiaResult | null>(null);
  const [error, setError]   = useState<string | null>(null);

  const startSession = async () => {
    setMode('calibrating');
    setStatus('loading');
    setResult(null);
    setError(null);
    try {
      const fd = new FormData();
      fd.append('trigger', 'start');
      const res = await apiEndpoints.dyslexia.predict(fd);
      setResult(res.data);
      setStatus('success');
      setMode('done');
    } catch (e: any) {
      setError(e.message);
      setStatus('error');
      setMode('idle');
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6 animate-fade-up">

      {/* Info */}
      <div className="card p-5 flex gap-4 items-start">
        <div className="w-9 h-9 rounded-xl bg-sky-50 border border-sky-100 flex items-center justify-center shrink-0">
          <Eye size={16} className="text-sky-600" />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-slate-800 mb-1">Eye-Tracking Analysis</h2>
          <p className="text-xs text-slate-500 leading-relaxed">
            Uses <span className="font-medium text-slate-700">MediaPipe FaceMesh</span> + Kalman smoothing with
            a 9-point calibration grid. A <span className="font-medium text-slate-700">VotingClassifier</span> trained
            on the Benfatto dataset classifies fixation/regression patterns.
          </p>
        </div>
      </div>

      {/* Hardware warning */}
      <div className="flex items-start gap-3 p-4 bg-amber-50 border border-amber-100 rounded-xl">
        <AlertCircle size={15} className="text-amber-500 shrink-0 mt-0.5" />
        <p className="text-xs text-amber-700 leading-relaxed">
          <span className="font-semibold">Note:</span> Webcam iris pixel span (~10px at normal distance) limits
          raw gaze precision. Ensure good lighting and maintain 50–70 cm from screen.
        </p>
      </div>

      {/* Session launcher */}
      <div className="card p-8 flex flex-col items-center gap-5 text-center">
        <div className="w-16 h-16 rounded-2xl bg-sky-50 border border-sky-100 flex items-center justify-center">
          <Camera size={24} className="text-sky-500" />
        </div>

        <div>
          <h3 className="font-semibold text-slate-900 mb-1">Live Eye-Tracking Session</h3>
          <p className="text-xs text-slate-400 leading-relaxed max-w-sm">
            Starts a calibration + reading session using your webcam.
            Keep your head still and follow the on-screen prompts.
          </p>
        </div>

        <div className="flex gap-3">
          {status === 'loading' ? (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <LoadingSpinner size={18} />
              <span>{mode === 'calibrating' ? 'Calibrating…' : 'Recording…'}</span>
            </div>
          ) : (
            <button onClick={startSession} className="btn-primary">
              <Camera size={14} />
              Start Session
            </button>
          )}
        </div>

        {/* Steps */}
        <div className="w-full grid grid-cols-3 gap-2 mt-2">
          {[
            { n: 1, label: '9-point calibration', active: mode === 'calibrating' },
            { n: 2, label: 'Reading passage',      active: mode === 'recording'   },
            { n: 3, label: 'Analysis result',      active: mode === 'done'        },
          ].map(({ n, label, active }) => (
            <div key={n} className={`flex flex-col items-center gap-1 p-3 rounded-lg transition-all
              ${active ? 'bg-brand-50 border border-brand-100' : 'bg-slate-50'}`}>
              <span className={`w-5 h-5 rounded-full text-[11px] font-bold flex items-center justify-center
                ${active ? 'bg-brand-500 text-white' : 'bg-slate-200 text-slate-400'}`}>{n}</span>
              <span className="text-[11px] text-slate-500 text-center leading-tight">{label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Error */}
      {status === 'error' && error && <ErrorBanner message={error} />}

      {/* Result */}
      {status === 'success' && result && (
        <ResultCard
          risk={result.risk}
          label={result.label === 'dyslexia' ? 'Dyslexia indicators present' : 'No dyslexia indicators'}
          confidence={result.confidence}
          meta={[
            { key: 'Fixations',       value: result.n_fixations                              },
            { key: 'Regressions',     value: result.n_regressions                            },
            { key: 'Regression rate', value: `${(result.regression_rate * 100).toFixed(1)}%` },
            { key: 'Duration',        value: `${result.recording_duration.toFixed(1)} s`     },
          ]}
          timestamp={new Date().toISOString()}
        />
      )}
    </div>
  );
}

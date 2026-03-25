<<<<<<< HEAD
import React, { useState, useEffect } from 'react';
import { Eye, Camera, AlertCircle, CheckCircle2, RotateCcw } from 'lucide-react';
import ResultCard from '../components/ui/ResultCard';
import { DyslexiaResult } from '../types';
import { api } from '../lib/api';

type Mode = 'idle' | 'done';

interface DyslexiaPageProps {
  onComplete: (risk: number, label: string, result: DyslexiaResult) => void;
  isRetry?: boolean;
}

// Define shape of stored fixation data
interface StoredFixation {
  x: number;
  y: number;
  duration: number;
}

export default function DyslexiaPage({ onComplete, isRetry }: DyslexiaPageProps) {
  const [mode, setMode] = useState<Mode>('idle');
  const [result, setResult] = useState<DyslexiaResult | null>(null);
  const [duration, setDuration] = useState(30);

  useEffect(() => {
    const stored = sessionStorage.getItem('dyslexiaTestResult');
    if (stored) {
      processTestData(JSON.parse(stored));
    }
  }, []);

  async function processTestData(data: any) {
    // data = { raw, fixations, duration }
    const fixations: StoredFixation[] = data.fixations;
    const elapsed = data.duration;

    // Compute regressions
    let nReg = 0;
    for (let i = 1; i < fixations.length; i++) {
      if (fixations[i].x < fixations[i-1].x - 30) nReg++;
    }

    const fixDurs = fixations.map(f => f.duration / 1000);
    const meanFix = fixDurs.length ? fixDurs.reduce((a: number, b: number) => a + b) / fixDurs.length : 0.2;
    const sacc: number[] = [];
    for (let i = 1; i < fixations.length; i++) {
      sacc.push(Math.abs(fixations[i].x - fixations[i-1].x));
    }
    const sacc_mean = sacc.length ? sacc.reduce((a, b) => a + b) / sacc.length : 18;
    const sacc_std = sacc.length > 1
      ? Math.sqrt(sacc.map(v => (v - sacc_mean) ** 2).reduce((a, b) => a + b) / sacc.length)
      : 13;

    const features: Record<string, number> = {
      fix_dur_mean: meanFix,
      fix_dur_skew: 0,
      fix_disp_mean: 0.6,
      sacc_amp_mean: sacc_mean,
      sacc_amp_std: sacc_std,
      sacc_amp_skew: 0,
      progressive_amp_mean: sacc_mean * 0.8,
      stft_dom_freq_mean: 0.19,
      stft_dom_freq_std: 0.19,
      stft_entropy_mean: 1.25,
      stft_low_power_mean: 0.95,
      binocular_disparity_x: 2.6,
      binocular_correlation: 0.99,
      reading_drift: 5.0,
      fatigue_slope: 6.8,
      reading_rhythm_power: 0.22,
      mid_freq_ratio: 0.027,
      high_freq_ratio: 0.015,
      fix_count: fixations.length,
      regression_count: nReg,
      regression_rate: fixations.length > 0 ? nReg / fixations.length : 0,
      recording_duration: elapsed,
    };

    try {
      const res = await api.post('/dyslexia/predict_features', features);
      setResult(res.data as DyslexiaResult);
      setMode('done');
      sessionStorage.removeItem('dyslexiaTestResult');
    } catch (e) {
      console.error('Analysis failed', e);
      setMode('idle');
    }
  }

  const startSession = () => {
    window.location.href = `/dyslexia-index.html?duration=${duration}`;
  };

  const handleRetry = () => {
    setResult(null);
    setMode('idle');
=======
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
>>>>>>> 33f15c0dc22504283b346af414bc23b2dc1340c0
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6 animate-fade-up">
<<<<<<< HEAD
      {/* Info panel */}
=======

      {/* Info */}
>>>>>>> 33f15c0dc22504283b346af414bc23b2dc1340c0
      <div className="card p-5 flex gap-4 items-start">
        <div className="w-9 h-9 rounded-xl bg-sky-50 border border-sky-100 flex items-center justify-center shrink-0">
          <Eye size={16} className="text-sky-600" />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-slate-800 mb-1">Eye-Tracking Analysis</h2>
          <p className="text-xs text-slate-500 leading-relaxed">
<<<<<<< HEAD
            Uses <span className="font-medium text-slate-700">WebGazer</span> + Kalman smoothing with
            a 9‑point calibration grid. A <span className="font-medium text-slate-700">VotingClassifier</span> trained
=======
            Uses <span className="font-medium text-slate-700">MediaPipe FaceMesh</span> + Kalman smoothing with
            a 9-point calibration grid. A <span className="font-medium text-slate-700">VotingClassifier</span> trained
>>>>>>> 33f15c0dc22504283b346af414bc23b2dc1340c0
            on the Benfatto dataset classifies fixation/regression patterns.
          </p>
        </div>
      </div>

<<<<<<< HEAD
      {/* Warning */}
=======
      {/* Hardware warning */}
>>>>>>> 33f15c0dc22504283b346af414bc23b2dc1340c0
      <div className="flex items-start gap-3 p-4 bg-amber-50 border border-amber-100 rounded-xl">
        <AlertCircle size={15} className="text-amber-500 shrink-0 mt-0.5" />
        <p className="text-xs text-amber-700 leading-relaxed">
          <span className="font-semibold">Note:</span> Webcam iris pixel span (~10px at normal distance) limits
          raw gaze precision. Ensure good lighting and maintain 50–70 cm from screen.
        </p>
      </div>

<<<<<<< HEAD
      {/* Idle state */}
      {mode === 'idle' && (
        <div className="card p-8 flex flex-col items-center gap-5 text-center">
          <div className="w-16 h-16 rounded-2xl bg-sky-50 border border-sky-100 flex items-center justify-center">
            <Camera size={24} className="text-sky-500" />
          </div>
          <div>
            <h3 className="font-semibold text-slate-900 mb-1">Live Eye-Tracking Session</h3>
            <p className="text-xs text-slate-400 leading-relaxed max-w-sm">
              Starts a full-screen calibration and reading session using your webcam.
              Keep your head still and follow the on-screen prompts.
            </p>
          </div>
          <div className="w-full max-w-xs space-y-2 mt-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-600">Reading duration</span>
              <span className="text-sm font-bold text-sky-600">{duration}s</span>
            </div>
            <input type="range" min={15} max={60} step={5} value={duration}
              onChange={e => setDuration(Number(e.target.value))}
              className="w-full h-1.5 bg-slate-200 rounded-full appearance-none cursor-pointer accent-sky-500" />
            <div className="flex justify-between text-[10px] text-slate-400">
              <span>15s (quick)</span><span>30s (standard)</span><span>60s (extended)</span>
            </div>
          </div>
          <button onClick={startSession} className="btn-primary px-8 mt-2">
            <Camera size={14} /> Start Session
          </button>
        </div>
      )}

      {/* Done state – result */}
      {mode === 'done' && result && (
        <div className="space-y-4 animate-fade-up">
          <div className="flex items-center gap-2 p-3 bg-emerald-50 border border-emerald-100 rounded-xl">
            <CheckCircle2 size={14} className="text-emerald-500" />
            <p className="text-xs font-medium text-emerald-700">
              Eye-tracking complete — {result.n_fixations} fixations recorded
            </p>
          </div>
          <ResultCard
            risk={result.risk}
            label={result.label === 'dyslexic' ? 'Dyslexia indicators present' : 'No dyslexia indicators'}
            confidence={result.confidence}
            meta={[
              { key: 'Fixations', value: result.n_fixations },
              { key: 'Regressions', value: result.n_regressions },
              { key: 'Regression rate', value: `${(result.regression_rate * 100).toFixed(1)}%` },
              { key: 'Duration', value: `${result.recording_duration.toFixed(1)}s` },
            ]}
            timestamp={new Date().toISOString()}
          />
          <div className="flex gap-3 mt-8">
            <button onClick={handleRetry} className="btn-secondary flex-1 py-3 text-sm">
              <RotateCcw size={16} className="inline mr-2 mb-0.5" /> Start New Test
            </button>
            <button
              onClick={() => onComplete(result.risk, result.label, result)}
              className="btn-primary flex-1 py-3 text-sm font-semibold shadow-md"
            >
              Continue to Report →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
=======
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
>>>>>>> 33f15c0dc22504283b346af414bc23b2dc1340c0

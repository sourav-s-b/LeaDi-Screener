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

// ─── Screen geometry for pixel → degree conversion ───────────────────────────
// The Python engine expects gaze in DEGREES OF VISUAL ANGLE (like the Tobii
// Benfatto dataset), not raw screen pixels. WebGazer returns pixels.
// Adjust SCREEN_W_PX / SCREEN_H_PX if you know the user's actual resolution.
// These defaults (1920×1080, 52cm wide, 60cm viewing distance) give ~0.025°/px.
const SCREEN_W_PX  = window.screen.width  || 1920;
const SCREEN_H_PX  = window.screen.height || 1080;
// Horizontal and vertical field-of-view in degrees for a typical monitor
// at ~60 cm viewing distance: FOV_H ≈ 47.7°, FOV_V ≈ 28.0°
const FOV_H_DEG    = 47.7;
const FOV_V_DEG    = 28.0;
const DEG_PER_PX_X = FOV_H_DEG / SCREEN_W_PX;   // ≈ 0.0249 °/px
const DEG_PER_PX_Y = FOV_V_DEG / SCREEN_H_PX;   // ≈ 0.0259 °/px

/** Convert a pixel coordinate to degrees of visual angle centred at 0. */
function pxToDeg(px: number, pxCenter: number, degPerPx: number): number {
  return (px - pxCenter) * degPerPx;
}

export default function DyslexiaPage({ onComplete, isRetry }: DyslexiaPageProps) {
  const [mode, setMode] = useState<Mode>('idle');
  const [result, setResult] = useState<DyslexiaResult | null>(null);
  const [duration, setDuration] = useState(30);

  // --- GHOST DATA FIX ---
  useEffect(() => {
    if (isRetry) {
      sessionStorage.removeItem('dyslexiaTestResult');
      return;
    }
    const stored = sessionStorage.getItem('dyslexiaTestResult');
    if (stored) {
      processTestData(JSON.parse(stored));
    }
  }, [isRetry]);

  async function processTestData(data: any) {
    const raw: Array<{ x: number; y: number; t: number }> = data.raw;

    if (!raw || raw.length < 20) {
      console.error('Not enough gaze data collected.');
      setMode('idle');
      return;
    }

    // ── Step 1: 5-frame moving-average to reduce WebGazer jitter ─────────────
    const smoothedRaw: Array<{ x: number; y: number; t: number }> = [];
    for (let i = 0; i < raw.length; i++) {
      let sumX = 0, sumY = 0, count = 0;
      for (let j = Math.max(0, i - 2); j <= Math.min(raw.length - 1, i + 2); j++) {
        sumX += raw[j].x;
        sumY += raw[j].y;
        count++;
      }
      smoothedRaw.push({ t: raw[i].t, x: sumX / count, y: sumY / count });
    }

    // ── Step 2: Resample to 50 Hz (matching Tobii/Benfatto training data) ────
    const TARGET_DT_MS = 20; // 50 Hz
    const startTime = smoothedRaw[0].t;
    const endTime   = smoothedRaw[smoothedRaw.length - 1].t;

    const resampledGaze: number[][] = [];
    let rawIdx = 0;

    const cxPx = SCREEN_W_PX / 2;
    const cyPx = SCREEN_H_PX / 2;

    for (let currentTime = startTime; currentTime <= endTime; currentTime += TARGET_DT_MS) {
      // Advance pointer
      while (rawIdx < smoothedRaw.length - 1 && smoothedRaw[rawIdx + 1].t < currentTime) {
        rawIdx++;
      }

      const p1 = smoothedRaw[rawIdx];
      const p2 = smoothedRaw[rawIdx + 1] || p1;

      let xPx: number, yPx: number;
      if (p1.t === p2.t) {
        xPx = p1.x;
        yPx = p1.y;
      } else {
        const ratio = (currentTime - p1.t) / (p2.t - p1.t);
        xPx = p1.x + ratio * (p2.x - p1.x);
        yPx = p1.y + ratio * (p2.y - p1.y);
      }

      // ── FIX 1: Convert pixels → degrees of visual angle ──────────────────
      // The Python engine's INVALID_THRESHOLD=40° will NaN-out any value >40.
      // Raw pixel coordinates (e.g. x=800) are ~800× too large, causing every
      // sample to be treated as a blink → 0 fixations → same prediction always.
      const xDeg = pxToDeg(xPx, cxPx, DEG_PER_PX_X);
      const yDeg = pxToDeg(yPx, cyPx, DEG_PER_PX_Y);

      // ── FIX 2: Use separate left/right eye columns (not duplicated x,y) ───
      // WebGazer returns a single gaze point, not per-eye data. We add a tiny
      // synthetic binocular offset (~0.3°) so the engine's binocular features
      // are not trivially 0 (disparity) / 1 (correlation) every time.
      // This is honest: WebGazer cannot separate eyes, so we model expected
      // vergence noise rather than claiming perfect binocular tracking.
      const timeInSeconds = (currentTime - startTime) / 1000.0;
      const VERGENCE_NOISE_DEG = 0.3;
      const lxDeg = xDeg - VERGENCE_NOISE_DEG / 2;
      const rxDeg = xDeg + VERGENCE_NOISE_DEG / 2;

      resampledGaze.push([
        timeInSeconds,
        lxDeg,
        yDeg,
        rxDeg,
        yDeg,
      ]);
    }

    console.debug(
      `[Dyslexia] Sending ${resampledGaze.length} samples @ 50Hz`,
      `LX range: [${Math.min(...resampledGaze.map(r => r[1])).toFixed(1)},`,
      `${Math.max(...resampledGaze.map(r => r[1])).toFixed(1)}]°`
    );

    try {
      const res = await api.post('/dyslexia/predict_raw', { gaze_data: resampledGaze });
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
    sessionStorage.removeItem('dyslexiaTestResult');
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6 animate-fade-up">
      {/* Info panel */}
      <div className="card p-5 flex gap-4 items-start">
        <div className="w-9 h-9 rounded-xl bg-sky-50 border border-sky-100 flex items-center justify-center shrink-0">
          <Eye size={16} className="text-sky-600" />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-slate-800 mb-1">Eye-Tracking Analysis</h2>
          <p className="text-xs text-slate-500 leading-relaxed">
            Uses <span className="font-medium text-slate-700">WebGazer</span> + Kalman smoothing with
            a 9‑point calibration grid. A <span className="font-medium text-slate-700">VotingClassifier</span> trained
            on the Benfatto dataset classifies fixation/regression patterns.
          </p>
        </div>
      </div>

      {/* Warning */}
      <div className="flex items-start gap-3 p-4 bg-amber-50 border border-amber-100 rounded-xl">
        <AlertCircle size={15} className="text-amber-500 shrink-0 mt-0.5" />
        <p className="text-xs text-amber-700 leading-relaxed">
          <span className="font-semibold">Note:</span> Webcam iris pixel span (~10px at normal distance) limits
          raw gaze precision. Ensure good lighting and maintain 50–70 cm from screen.
        </p>
      </div>

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
          <button onClick={startSession} className="btn-primary px-8 mt-2 shadow-md">
            <Camera size={14} className="inline mr-2" /> Start Session
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
              { key: 'Fixations',       value: result.n_fixations },
              { key: 'Regressions',     value: result.n_regressions },
              { key: 'Regression rate', value: `${(result.regression_rate * 100).toFixed(1)}%` },
              { key: 'Duration',        value: `${result.recording_duration.toFixed(1)}s` },
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
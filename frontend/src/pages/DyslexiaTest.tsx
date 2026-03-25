import React, { useState, useEffect, useRef, useCallback } from 'react';
import { XCircle, RotateCcw, CheckCircle2 } from 'lucide-react';
import ResultCard from '../components/ui/ResultCard';
import { LoadingSpinner, ErrorBanner } from '../components/ui/Feedback';
import { api } from '../lib/api';
import { DyslexiaResult } from '../types';

interface Props {
  duration?: number;
  onComplete: (risk: number, label: string, result: DyslexiaResult) => void;
  onCancel?: () => void;
  isRetry?: boolean;
}

type Phase = 'aligning' | 'calibrating' | 'reading' | 'analysing' | 'done' | 'error';

const PARAGRAPHS = [
  "The quick brown fox jumps over the lazy dog. Reading carefully is a skill that takes time to master. Eye tracking technology reveals where our attention flows on the page.",
  "She opened the old wooden door and stepped inside. The room smelled of dust and forgotten things. On the table lay a leather-bound book, its pages yellowed with age.",
  "The human brain contains approximately eighty-six billion neurons, each connected to thousands of others through synaptic junctions. Signals travel at remarkable speeds.",
  "Every morning I walk to the park near my house. The path is lined with tall oak trees that provide shade in summer. Children play on the grass while parents sit on benches.",
  "Machine learning models are trained on large datasets by adjusting internal parameters. Deep neural networks use multiple layers to extract increasingly abstract features.",
  "The Amazon rainforest covers more than five million square kilometres across nine countries. It is home to an estimated three million species of plants and animals."
];

const CAL_POINTS = [
  { x: 15, y: 15 }, { x: 50, y: 15 }, { x: 85, y: 15 },
  { x: 15, y: 50 }, { x: 50, y: 50 }, { x: 85, y: 50 },
  { x: 15, y: 85 }, { x: 50, y: 85 }, { x: 85, y: 85 },
];

const CLICKS_NEEDED = 5;

declare global {
  interface Window { webgazer: any; }
}

export default function DyslexiaTest({
  duration = 30,
  onComplete,
  onCancel,
  isRetry
}: Props) {
  const [phase, setPhase] = useState<Phase>('aligning');
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DyslexiaResult | null>(null);
  const [calClicks, setCalClicks] = useState<number[]>(Array(9).fill(0));
  const [elapsed, setElapsed] = useState(0);
  const [fixCount, setFixCount] = useState(0);
  const [gazeDot, setGazeDot] = useState<{ x: number; y: number } | null>(null);

  const [paragraphs] = useState(() => {
    const shuffled = [...PARAGRAPHS].sort(() => 0.5 - Math.random());
    return shuffled.slice(0, 3);
  });

  const recordingRef = useRef(false);
  const rawLogsRef = useRef<{ x: number; y: number; t: number }[]>([]);
  const fixationsRef = useRef<{ x: number; y: number; dur: number }[]>([]);
  const windowBufRef = useRef<{ x: number; y: number; t: number }[]>([]);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const wgInstanceRef = useRef<any>(null);
  const videoTrackStoppedRef = useRef(false);

  // Dynamic CSS body classes for WebGazer positioning
  useEffect(() => {
    document.body.classList.remove('wg-aligning', 'wg-calibrating', 'wg-reading', 'wg-hidden');
    if (phase === 'aligning') document.body.classList.add('wg-aligning');
    if (phase === 'calibrating') document.body.classList.add('wg-calibrating');
    if (phase === 'reading' || phase === 'analysing') document.body.classList.add('wg-reading');
    if (phase === 'done' || phase === 'error') document.body.classList.add('wg-hidden');

    return () => {
      document.body.classList.remove('wg-aligning', 'wg-calibrating', 'wg-reading', 'wg-hidden');
    };
  }, [phase]);

  const loadWebGazer = useCallback(() => {
    return new Promise<void>((resolve, reject) => {
      if (window.webgazer) {
        resolve();
        return;
      }
      if (document.getElementById('wg-script')) {
        const interval = setInterval(() => {
          if (window.webgazer) {
            clearInterval(interval);
            resolve();
          }
        }, 100);
        return;
      }
      const s = document.createElement('script');
      s.id = 'wg-script';
      s.src = 'https://cdn.jsdelivr.net/npm/webgazer@2.1.0/dist/webgazer.js';
      s.onload = () => {
        setTimeout(() => {
          if (window.webgazer) resolve();
          else reject(new Error('Missing WebGazer object'));
        }, 100);
      };
      s.onerror = () => reject(new Error('Failed to load WebGazer.'));
      document.head.appendChild(s);
    });
  }, []);

  const processFixation = useCallback((pt: { x: number; y: number; t: number }) => {
    const buf = windowBufRef.current;
    buf.push(pt);
    const xs = buf.map(p => p.x);
    const ys = buf.map(p => p.y);
    const spread = Math.max(...xs) - Math.min(...xs) + (Math.max(...ys) - Math.min(...ys));
    const dur = buf[buf.length - 1].t - buf[0].t;

    if (spread > 80) {
      if (dur >= 150) {
        const avgX = xs.reduce((a, b) => a + b, 0) / xs.length;
        const avgY = ys.reduce((a, b) => a + b, 0) / ys.length;
        fixationsRef.current.push({
          x: Math.round(avgX),
          y: Math.round(avgY),
          dur,
        });
        setFixCount(fixationsRef.current.length);
      }
      windowBufRef.current = [pt];
    }
  }, []);

  const startWebGazer = useCallback(async () => {
    try {
      await loadWebGazer();
      const wg = window.webgazer;
      wgInstanceRef.current = wg;

      // Critical: apply Kalman filter scaling from working example
      wg.params.commonModelFieldId = "https://cdn.jsdelivr.net/npm/webgazer@2.1.0/dist/";
      wg.params.stdevScaling = 0.05;

      await wg.setGazeListener((data: any, elapsed: number) => {
        if (!data) return;
        setGazeDot({ x: data.x, y: data.y });
        if (recordingRef.current) {
          const pt = { x: Math.round(data.x), y: Math.round(data.y), t: Math.round(elapsed) };
          rawLogsRef.current.push(pt);
          processFixation(pt);
        }
      }).begin();

      wg.showVideoPreview(true).showPredictionPoints(false).applyKalmanFilter(true);
    } catch (e: any) {
      setPhase('error');
      setError(e.message || "Failed to initialize eye tracking.");
    }
  }, [loadWebGazer, processFixation]);

  // Improved camera shutdown – ensures webcam light turns off immediately
  const stopWebGazer = useCallback(() => {
    if (videoTrackStoppedRef.current) return;
    videoTrackStoppedRef.current = true;

    try {
      if (window.webgazer) {
        // Stop video tracks
        const videoEl = document.getElementById('webgazerVideoFeed') as HTMLVideoElement;
        if (videoEl && videoEl.srcObject) {
          const stream = videoEl.srcObject as MediaStream;
          stream.getTracks().forEach(track => {
            track.stop();
          });
          videoEl.srcObject = null;
        }
        // Destroy WebGazer instance
        window.webgazer.pause();
        window.webgazer.showVideoPreview(false);
        window.webgazer.end();
        // Remove container to clean up
        const container = document.getElementById('webgazerVideoContainer');
        if (container) container.remove();
      }
    } catch (e) {
      console.error('Failed to cleanly stop WebGazer:', e);
    }
  }, []);

  useEffect(() => {
    startWebGazer();
    return () => stopWebGazer();
  }, [startWebGazer, stopWebGazer]);

  const handleCancelClick = () => {
    stopWebGazer();
    if (onCancel) onCancel();
  };

  const handleRetry = () => {
    videoTrackStoppedRef.current = false;
    setResult(null);
    setCalClicks(Array(9).fill(0));
    setElapsed(0);
    setFixCount(0);
    rawLogsRef.current = [];
    fixationsRef.current = [];
    windowBufRef.current = [];
    setPhase('aligning');
    startWebGazer();
  };

  const handleCalClick = useCallback((idx: number) => {
    setCalClicks(prev => {
      const next = [...prev];
      next[idx] = Math.min(next[idx] + 1, CLICKS_NEEDED);
      if (next.every(c => c >= CLICKS_NEEDED)) {
        setTimeout(() => setPhase('reading'), 800);
      }
      return next;
    });
  }, []);

  // Reading timer
  useEffect(() => {
    if (phase !== 'reading') return;
    recordingRef.current = true;
    rawLogsRef.current = [];
    fixationsRef.current = [];
    windowBufRef.current = [];

    timerRef.current = setInterval(() => {
      setElapsed(e => {
        if (e + 1 >= duration) {
          clearInterval(timerRef.current!);
          recordingRef.current = false;
          setPhase('analysing');
        }
        return e + 1;
      });
    }, 1000);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [phase, duration]);

  // Analytics pipeline
  useEffect(() => {
    if (phase !== 'analysing') return;

    stopWebGazer();

    const raw = rawLogsRef.current;
    const fixs = fixationsRef.current;

    if (raw.length < 20) {
      setPhase('error');
      setError('Not enough gaze data collected. Ensure your face is well-lit and visible to the camera.');
      return;
    }

    let nReg = 0;
    for (let i = 1; i < fixs.length; i++) {
      if (fixs[i].x < fixs[i - 1].x - 30) nReg++;
    }

    const fixDurs = fixs.map(f => f.dur / 1000);
    const meanFix = fixDurs.length ? fixDurs.reduce((a, b) => a + b) / fixDurs.length : 0.2;
    const sacc = [];
    for (let i = 1; i < fixs.length; i++) {
      sacc.push(Math.abs(fixs[i].x - fixs[i - 1].x));
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
      fix_count: fixs.length,
      regression_count: nReg,
      regression_rate: fixs.length > 0 ? nReg / fixs.length : 0,
      recording_duration: elapsed || duration,
    };

    api.post('/dyslexia/predict_features', features)
      .then(res => {
        setResult(res.data as DyslexiaResult);
        setPhase('done');
      })
      .catch(e => {
        setPhase('error');
        setError(e.response?.data?.detail ?? 'Analysis failed.');
      });
  }, [phase, duration, elapsed, stopWebGazer]);

  const pct = Math.round((elapsed / duration) * 100);
  const calPct = Math.round((calClicks.filter(c => c >= CLICKS_NEEDED).length / 9) * 100);

  return (
    <div className="fixed inset-0 z-[999999] bg-slate-50 flex flex-col overflow-y-auto">
      <style>{`
        /* Force WebGazer camera container positioning */
        #webgazerVideoContainer {
          z-index: 1000000 !important;
        }
        body.wg-aligning #webgazerVideoContainer {
          display: block !important;
          position: fixed !important;
          top: 45% !important;
          left: 50% !important;
          transform: translate(-50%, -50%) !important;
          width: 480px !important;
          height: 360px !important;
          border: 6px solid #0ea5e9 !important;
          border-radius: 16px !important;
          box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5) !important;
        }
        body.wg-calibrating #webgazerVideoContainer,
        body.wg-reading #webgazerVideoContainer {
          display: block !important;
          position: fixed !important;
          top: 20px !important;
          right: 20px !important;
          left: auto !important;
          transform: none !important;
          width: 160px !important;
          height: 120px !important;
          border: 2px solid #64748b !important;
          border-radius: 8px !important;
          opacity: 0.6 !important;
        }
        body.wg-reading #webgazerVideoContainer {
          opacity: 1.0 !important;
        }
        body.wg-hidden #webgazerVideoContainer {
          display: none !important;
        }
        /* Hide the face outline box */
        #webgazerFaceFeedbackBox {
          display: none !important;
        }
      `}</style>

      {/* Cancel button */}
      {phase !== 'done' && (
        <button
          onClick={handleCancelClick}
          className="absolute top-6 left-6 text-slate-400 hover:text-slate-800 flex items-center gap-1 z-[2000000]"
        >
          <XCircle size={18} /> Exit Test
        </button>
      )}

      {/* ALIGNING PHASE */}
      {phase === 'aligning' && (
        <div className="absolute top-12 left-0 right-0 flex flex-col items-center gap-3 z-[2000000]">
          <div className="flex items-center gap-3 text-slate-800">
            <LoadingSpinner size={24} />
            <h2 className="text-2xl font-bold">Initialising Camera…</h2>
          </div>
          <div className="absolute top-[75vh] w-full flex flex-col items-center gap-4 text-center px-4">
            <p className="text-sm text-slate-500 font-medium">
              Ensure your face is centred and well-lit inside the blue box.
            </p>
            <button
              onClick={() => setPhase('calibrating')}
              className="bg-sky-500 hover:bg-sky-600 text-white py-3 px-8 rounded-full font-semibold transition-all shadow-lg"
            >
              Face is centred → Start Calibration
            </button>
          </div>
        </div>
      )}

      {/* CALIBRATING PHASE */}
      {phase === 'calibrating' && (
        <div className="fixed inset-0 bg-slate-900" style={{ cursor: 'crosshair' }}>
          {gazeDot && (
            <div
              className="absolute pointer-events-none z-[2000001] transition-all duration-100"
              style={{ left: gazeDot.x - 6, top: gazeDot.y - 6 }}
            >
              <div className="w-3 h-3 rounded-full bg-sky-400 opacity-70 ring-2 ring-sky-300" />
            </div>
          )}
          <div className="absolute top-6 left-0 right-0 text-center text-white z-[2000000]">
            <p className="text-sm font-semibold">
              Calibration — click each dot {CLICKS_NEEDED} times
            </p>
            <div className="mt-3 mx-auto w-48 h-1.5 bg-slate-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-sky-500 rounded-full transition-all duration-300"
                style={{ width: `${calPct}%` }}
              />
            </div>
          </div>
          {CAL_POINTS.map((pt, i) => {
            const clicks = calClicks[i];
            const done = clicks >= CLICKS_NEEDED;
            const opacity = done ? 0 : Math.max(0.2, 1 - clicks * 0.18);
            return (
              <button
                key={i}
                onClick={() => handleCalClick(i)}
                className="absolute flex items-center justify-center transition-all duration-200 z-[2000000]"
                style={{
                  left: `${pt.x}%`,
                  top: `${pt.y}%`,
                  transform: 'translate(-50%,-50%)',
                  opacity,
                  pointerEvents: done ? 'none' : 'auto',
                }}
              >
                <div
                  className={[
                    'w-6 h-6 rounded-full transition-all',
                    done
                      ? 'bg-emerald-400 scale-75'
                      : 'bg-sky-500 hover:bg-sky-400 hover:scale-110',
                  ].join(' ')}
                />
                {!done && (
                  <div className="absolute inset-0 rounded-full bg-sky-400 opacity-30 animate-ping" />
                )}
                {clicks > 0 && !done && (
                  <span className="absolute -top-4 text-[10px] text-white font-mono">
                    {clicks}/{CLICKS_NEEDED}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* READING PHASE */}
      {phase === 'reading' && (
        <div className="fixed inset-0 bg-slate-950 flex flex-col items-center justify-start p-8 overflow-auto">
          {gazeDot && (
            <div
              className="fixed pointer-events-none z-[2000001] transition-all duration-80"
              style={{ left: gazeDot.x - 10, top: gazeDot.y - 10 }}
            >
              <div className="w-5 h-5 rounded-full border-2 border-sky-400 opacity-60" />
              <div className="absolute inset-0 m-auto w-2 h-2 rounded-full bg-sky-400 opacity-80" />
            </div>
          )}

          <div className="max-w-4xl w-full z-[100001] space-y-8 mt-10 pb-40">
            <p className="text-[12px] text-slate-500 uppercase tracking-wider mb-6 text-center">
              Read naturally at your own pace
            </p>
            {paragraphs.map((p, i) => (
              <p
                key={i}
                className="text-2xl text-slate-100 leading-[2.0] font-serif text-justify tracking-wide"
              >
                {p}
              </p>
            ))}
          </div>

          <div className="fixed bottom-12 flex justify-center w-full z-[100001]">
            <button
              onClick={() => {
                recordingRef.current = false;
                if (timerRef.current) clearInterval(timerRef.current);
                setPhase('analysing');
              }}
              className="bg-emerald-500 hover:bg-emerald-400 text-white px-8 py-3 rounded-full font-bold shadow-lg transition-all flex items-center gap-2"
            >
              <CheckCircle2 size={18} /> I'm Finished Reading
            </button>
          </div>

          <div className="fixed bottom-4 left-0 right-0 px-16 space-y-2 z-[100001]">
            <div className="flex justify-between text-xs text-slate-500 font-medium">
              <span>Fixations: {fixCount}</span>
              <span>
                {elapsed}s / {duration}s
              </span>
            </div>
            <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-sky-500 rounded-full transition-all duration-1000"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        </div>
      )}

      {/* ANALYSING PHASE */}
      {phase === 'analysing' && (
        <div className="w-full h-full flex flex-col items-center justify-center gap-4 z-[2000000] relative">
          <LoadingSpinner size={32} />
          <p className="text-lg font-semibold text-slate-800">Analysing gaze patterns…</p>
          <p className="text-sm text-slate-500">
            {fixCount} fixations collected over {elapsed || duration} seconds
          </p>
        </div>
      )}

      {/* DONE PHASE */}
      {phase === 'done' && result && (
        <div className="w-full h-full flex flex-col items-center justify-center bg-slate-50 p-6 z-[2000000] relative">
          <div className="max-w-xl w-full space-y-6 animate-fade-up">
            <div className="flex items-center gap-3 p-4 bg-emerald-50 border border-emerald-100 rounded-xl">
              <CheckCircle2 size={20} className="text-emerald-500" />
              <p className="text-sm font-medium text-emerald-800">
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
                <RotateCcw size={16} className="inline mr-2 mb-0.5" /> Retry Test
              </button>
              <button
                onClick={() => onComplete(result.risk, result.label, result)}
                className="btn-primary flex-1 py-3 text-sm font-semibold shadow-md"
              >
                Continue to Report →
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ERROR PHASE */}
      {phase === 'error' && error && (
        <div className="w-full h-full flex flex-col items-center justify-center gap-4 px-6 z-[2000000] relative">
          <ErrorBanner message={error} />
          <button
            onClick={handleCancelClick}
            className="bg-slate-200 text-slate-700 py-2 px-6 rounded-lg font-medium hover:bg-slate-300 mt-4"
          >
            <RotateCcw size={14} className="inline mr-2 mb-0.5" /> Go Back
          </button>
        </div>
      )}
    </div>
  );
}

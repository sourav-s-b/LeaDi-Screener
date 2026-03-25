import React, { useState, useRef, useEffect, useCallback } from 'react';
import { PenLine, Upload, RotateCcw, Eraser, Play } from 'lucide-react';
import ResultCard from '../components/ui/ResultCard';
import { LoadingSpinner, ErrorBanner } from '../components/ui/Feedback';
import { apiEndpoints } from '../lib/api';
import { HandwritingResult, Status } from '../types';

interface Props {
  onComplete: (risk: number, label: string, result: HandwritingResult) => void;
  isRetry?:  boolean;
}

type InputMode = 'canvas' | 'upload';

const CLASS_META: Record<string, { label: string; color: string }> = {
  Normal:    { label: 'Normal letters',     color: '#10b981' },
  Reversal:  { label: 'Reversals detected', color: '#ef4444' },
  Corrected: { label: 'Self-corrected',     color: '#f59e0b' },
};

const PROMPT = 'Write: "bad dog dip big"';

// ── Canvas drawing component ──────────────────────────────────────────────────
function DrawingCanvas({ onImageReady, disabled }: {
  onImageReady: (blob: Blob) => void;
  disabled: boolean;
}) {
  const canvasRef  = useRef<HTMLCanvasElement>(null);
  const drawing    = useRef(false);
  const lastPos    = useRef<{ x: number; y: number } | null>(null);
  const [strokeW, setStrokeW]   = useState(3);
  const [hasInk,  setHasInk]   = useState(false);

  // Init canvas
  useEffect(() => {
    const c = canvasRef.current;
    if (!c) return;
    const ctx = c.getContext('2d')!;
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, c.width, c.height);
    ctx.strokeStyle = '#1e1e2e';
    ctx.lineCap     = 'round';
    ctx.lineJoin    = 'round';
  }, []);

  const getPos = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const rect = canvasRef.current!.getBoundingClientRect();
    const scaleX = canvasRef.current!.width  / rect.width;
    const scaleY = canvasRef.current!.height / rect.height;
    return {
      x: (e.clientX - rect.left) * scaleX,
      y: (e.clientY - rect.top)  * scaleY,
    };
  };

  const onPointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (disabled) return;
    canvasRef.current!.setPointerCapture(e.pointerId);
    drawing.current = true;
    lastPos.current = getPos(e);
  };

  const onPointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawing.current || !lastPos.current || disabled) return;
    const c   = canvasRef.current!;
    const ctx = c.getContext('2d')!;
    const pos = getPos(e);

    // Use pointer pressure if available (stylus), else 1
    const pressure = e.pressure > 0 ? e.pressure : 1;
    const lw       = strokeW * (0.5 + pressure * 0.5);

    ctx.beginPath();
    ctx.lineWidth = lw;
    ctx.moveTo(lastPos.current.x, lastPos.current.y);
    ctx.lineTo(pos.x, pos.y);
    ctx.stroke();
    lastPos.current = pos;
    setHasInk(true);
  };

  const onPointerUp = () => {
    drawing.current = false;
    lastPos.current = null;
  };

  const clear = () => {
    const c   = canvasRef.current!;
    const ctx = c.getContext('2d')!;
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, c.width, c.height);
    setHasInk(false);
  };

  const submit = useCallback(() => {
    canvasRef.current!.toBlob(blob => {
      if (blob) onImageReady(blob);
    }, 'image/png');
  }, [onImageReady]);

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-xs text-slate-500">Stroke width:</span>
        {[1, 2, 3, 5, 8].map(w => (
          <button key={w} onClick={() => setStrokeW(w)}
            className={['w-7 h-7 rounded-full border-2 flex items-center justify-center transition-all',
              strokeW === w ? 'border-brand-500 bg-brand-50' : 'border-slate-200 bg-white hover:border-slate-300',
            ].join(' ')}>
            <div className="rounded-full bg-slate-700"
              style={{ width: `${Math.min(w * 2.5, 20)}px`, height: `${Math.min(w * 2.5, 20)}px` }} />
          </button>
        ))}
        <div className="ml-auto flex gap-2">
          <button onClick={clear} className="btn-ghost text-xs flex items-center gap-1">
            <Eraser size={12} /> Clear
          </button>
        </div>
      </div>

      {/* Canvas */}
      <div className={['rounded-xl overflow-hidden border-2 transition-colors',
        disabled ? 'border-slate-100 opacity-50' : 'border-slate-200 hover:border-brand-200',
      ].join(' ')}>
        <canvas
          ref={canvasRef}
          width={800}
          height={300}
          style={{ width: '100%', height: '240px', touchAction: 'none', cursor: disabled ? 'not-allowed' : 'crosshair' }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerLeave={onPointerUp}
        />
      </div>

      {/* Prompt */}
      <div className="flex items-center justify-between">
        <p className="text-xs text-slate-400 italic">{PROMPT}</p>
        <button
          onClick={submit}
          disabled={!hasInk || disabled}
          className="btn-primary text-xs disabled:opacity-40 disabled:cursor-not-allowed"
        >
          <Play size={12} /> Analyse Drawing
        </button>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function HandwritingTest({ onComplete, isRetry }: Props) {
  const [mode,    setMode]    = useState<InputMode>('canvas');
  const [preview, setPreview] = useState<string | null>(null);
  const [status,  setStatus]  = useState<Status>('idle');
  const [result,  setResult]  = useState<HandwritingResult | null>(null);
  const [error,   setError]   = useState<string | null>(null);

  const analyse = async (blob: Blob, filename: string) => {
    setPreview(URL.createObjectURL(blob));
    setStatus('loading'); setResult(null); setError(null);
    try {
      const fd = new FormData();
      fd.append('file', blob, filename);
      const res = await apiEndpoints.handwriting.score(fd);
      setResult(res.data); setStatus('success');
    } catch (e: any) {
      setError(e.message); setStatus('error');
    }
  };

  const handleUpload = (file: File) => analyse(file, file.name);
  const handleCanvas = async (blob: Blob) => {
    setPreview(URL.createObjectURL(blob));
    setStatus('loading'); setResult(null); setError(null);
    try {
      const fd = new FormData();
      fd.append('file', blob, 'canvas_drawing.png');
      const res = await apiEndpoints.handwriting.score_canvas(fd);
      setResult(res.data); setStatus('success');
    } catch (e: any) { setError(e.message); setStatus('error'); }
  };

  const reset = () => {
    setStatus('idle'); setResult(null); setError(null); setPreview(null);
  };

  return (
    <div className="max-w-2xl mx-auto space-y-5 animate-fade-up">

      {/* Header */}
      <div className="card p-5 flex gap-4 items-start">
        <div className="w-9 h-9 rounded-xl bg-emerald-50 border border-emerald-100 flex items-center justify-center shrink-0">
          <PenLine size={16} className="text-emerald-600" />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-slate-800 mb-1">
            Handwriting Analysis {isRetry && <span className="badge badge-amber ml-1">Retry</span>}
          </h2>
          <p className="text-xs text-slate-500 leading-relaxed">
            Draw directly on the canvas (stylus or mouse) or upload a photo. YOLOv8 segments
            each letter individually and classifies it as Normal, Reversal, or Corrected.
          </p>
        </div>
      </div>

      {/* Mode tabs */}
      <div className="flex gap-1 p-1 bg-slate-100 rounded-xl">
        {([['canvas', '✏️  Draw on Canvas'], ['upload', '📁  Upload Image']] as const).map(([m, label]) => (
          <button key={m} onClick={() => { setMode(m); reset(); }}
            className={['flex-1 py-2 text-sm font-medium rounded-lg transition-all',
              mode === m ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-700',
            ].join(' ')}>
            {label}
          </button>
        ))}
      </div>

      {/* ── CANVAS MODE ── */}
      {mode === 'canvas' && (
        <div className="card p-5 space-y-3">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Draw Handwriting Sample</p>
          <ul className="flex flex-wrap gap-3 text-[11px] text-slate-400">
            {['Works with stylus (pressure-sensitive)', 'Mouse also works', 'Write letters that include b, d, p, q'].map(t => (
              <li key={t} className="flex items-center gap-1">
                <span className="w-1 h-1 rounded-full bg-slate-300" />{t}
              </li>
            ))}
          </ul>
          <DrawingCanvas onImageReady={handleCanvas} disabled={status === 'loading'} />
        </div>
      )}

      {/* ── UPLOAD MODE ── */}
      {mode === 'upload' && (
        <div className="card p-5 space-y-4">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Upload Handwriting Image</p>
          <label className={['flex flex-col items-center gap-3 border-2 border-dashed rounded-xl py-8 px-6 cursor-pointer transition-all',
            status==='success' ? 'border-brand-200 bg-brand-50/30' : 'border-slate-200 hover:border-brand-300 hover:bg-brand-50/20',
          ].join(' ')}>
            <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${status==='success'?'bg-brand-100':'bg-slate-100'}`}>
              <Upload size={17} className={status==='success'?'text-brand-600':'text-slate-400'} />
            </div>
            <div className="text-center">
              <p className="text-sm font-medium text-slate-700">Drop a handwriting image</p>
              <p className="text-xs text-slate-400 mt-0.5">JPG / PNG — photo or scan · max 20 MB</p>
            </div>
            <input type="file" accept=".jpg,.jpeg,.png,.webp,.bmp" className="hidden"
              onChange={e => { const f = e.target.files?.[0]; if (f) handleUpload(f); }} />
          </label>
          {preview && (
            <div className="rounded-xl overflow-hidden border border-slate-200 bg-slate-50">
              <img src={preview} alt="preview" className="w-full max-h-48 object-contain" />
            </div>
          )}
        </div>
      )}

      {/* Loading */}
      {status === 'loading' && (
        <div className="card p-6 flex items-center gap-3">
          <LoadingSpinner size={22} />
          <div>
            <p className="text-sm font-medium text-slate-700">Running per-letter detection…</p>
            <p className="text-xs text-slate-400">Segment → grid → YOLO classify</p>
          </div>
        </div>
      )}

      {status === 'error' && error && (
        <div className="space-y-3">
          <ErrorBanner message={error} />
          <button onClick={reset} className="btn-secondary text-xs w-full justify-center">
            <RotateCcw size={12} /> Try again
          </button>
        </div>
      )}

      {/* Result */}
      {status === 'success' && result && (
        <div className="space-y-4 animate-fade-up">
          {preview && mode === 'canvas' && (
            <div className="rounded-xl overflow-hidden border border-slate-200 bg-slate-50">
              <img src={preview} alt="Drawing" className="w-full max-h-40 object-contain" />
            </div>
          )}
          <ResultCard
            risk={result.risk}
            label={result.risk >= 0.35 ? 'Reversal patterns detected' : 'No significant reversals'}
            meta={[
              { key: 'Letters detected', value: result.total },
              { key: 'Reversals',        value: result.counts['Reversal']  ?? 0 },
              { key: 'Corrected',        value: result.counts['Corrected'] ?? 0 },
            ]}
            timestamp={new Date().toISOString()}
          />

          {result.total > 0 && (
            <div className="card p-5">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4">Letter Classification</p>
              <div className="space-y-3">
                {Object.entries(result.counts).filter(([, v]) => v > 0).map(([key, count]) => {
                  const meta = CLASS_META[key] ?? { label: key, color: '#94a3b8' };
                  const max  = Math.max(1, ...Object.values(result.counts));
                  return (
                    <div key={key} className="flex items-center gap-3">
                      <span className="text-xs text-slate-600 w-36 shrink-0 font-medium">{meta.label}</span>
                      <div className="flex-1 h-2.5 bg-slate-100 rounded-full overflow-hidden">
                        <div className="h-full rounded-full transition-all duration-700"
                          style={{ width: `${(count / max) * 100}%`, backgroundColor: meta.color }} />
                      </div>
                      <span className="text-xs font-mono font-semibold w-6 text-right" style={{ color: meta.color }}>{count}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {result.letter_detail.length > 0 && (
            <div className="card p-5">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Per-letter Detail</p>
              <div className="flex flex-wrap gap-2">
                {result.letter_detail.map((d, i) => {
                  const meta = CLASS_META[d.orientation] ?? { label: d.orientation, color: '#94a3b8' };
                  return (
                    <div key={i} className="flex flex-col items-center gap-0.5 px-2.5 py-2 bg-slate-50 rounded-lg border border-slate-200 min-w-[52px]">
                      <span className="text-base font-display font-700 text-slate-800">{d.label}</span>
                      <span className="text-[9px] font-medium" style={{ color: meta.color }}>{d.orientation}</span>
                      <span className="text-[9px] font-mono text-slate-400">{(d.conf * 100).toFixed(0)}%</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <div className="flex gap-2">
            <button onClick={reset} className="btn-secondary flex-1 justify-center">
              <RotateCcw size={13} /> Retry
            </button>
            <button onClick={() => onComplete(result.risk, result.risk >= 0.35 ? 'reversal_detected' : 'no_reversal', result)}
              className="btn-primary flex-1 justify-center py-2.5">
              Continue to Speech Test →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

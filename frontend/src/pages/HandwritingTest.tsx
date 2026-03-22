import React, { useState } from 'react';
import { PenLine } from 'lucide-react';
import FileUpload from '../components/ui/FileUpload';
import ResultCard from '../components/ui/ResultCard';
import { LoadingSpinner, ErrorBanner } from '../components/ui/Feedback';
import { apiEndpoints } from '../lib/api';
import { HandwritingResult, Status } from '../types';

interface Props {
  onComplete: (risk: number, label: string, result: HandwritingResult) => void;
}

const CLASS_META: Record<string, { label: string; color: string }> = {
  Normal:    { label: 'Normal letters',     color: '#10b981' },
  Reversal:  { label: 'Reversals detected', color: '#ef4444' },
  Corrected: { label: 'Self-corrected',     color: '#f59e0b' },
};

export default function HandwritingTest({ onComplete }: Props) {
  const [preview, setPreview] = useState<string | null>(null);
  const [status,  setStatus]  = useState<Status>('idle');
  const [result,  setResult]  = useState<HandwritingResult | null>(null);
  const [error,   setError]   = useState<string | null>(null);

  const handleFile = async (file: File) => {
    setPreview(URL.createObjectURL(file));
    setStatus('loading'); setResult(null); setError(null);
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await apiEndpoints.handwriting.score(fd);
      setResult(res.data); setStatus('success');
    } catch (e: any) {
      setError(e.message); setStatus('error');
    }
  };

  return (
    <div className="max-w-xl mx-auto space-y-5 animate-fade-up">

      <div className="card p-5 flex gap-4 items-start">
        <div className="w-9 h-9 rounded-xl bg-emerald-50 border border-emerald-100 flex items-center justify-center shrink-0">
          <PenLine size={16} className="text-emerald-600" />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-slate-800 mb-1">Handwriting Analysis</h2>
          <p className="text-xs text-slate-500 leading-relaxed">
            Upload a photo or scan of handwritten text. Each letter is individually segmented,
            arranged into a training-style grid, and classified by YOLOv8 as
            <strong className="text-slate-700"> Normal</strong>,
            <strong className="text-slate-700"> Reversal</strong>, or
            <strong className="text-slate-700"> Corrected</strong>.
          </p>
        </div>
      </div>

      <div className="card p-5 space-y-4">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Upload Handwriting Sample</p>
        <FileUpload
          accept=".jpg,.jpeg,.png,.webp,.bmp"
          label="Drop a handwriting image"
          hint="JPG / PNG — clear photo or scan · max 20 MB"
          onFile={handleFile}
          disabled={status === 'loading'}
        />
        {preview && (
          <div className="rounded-xl overflow-hidden border border-slate-200 bg-slate-50">
            <img src={preview} alt="preview" className="w-full max-h-48 object-contain" />
          </div>
        )}
        <ul className="space-y-1">
          {['Clear lighting, minimal shadows', 'One word or sentence per image works best',
            'Both real photos and scans supported'].map(t => (
            <li key={t} className="flex items-start gap-2 text-[11px] text-slate-400">
              <span className="mt-0.5 w-1 h-1 rounded-full bg-slate-300 shrink-0" />
              {t}
            </li>
          ))}
        </ul>
      </div>

      {status === 'loading' && (
        <div className="card p-6 flex items-center gap-3">
          <LoadingSpinner size={22} />
          <div>
            <p className="text-sm font-medium text-slate-700">Running per-letter detection…</p>
            <p className="text-xs text-slate-400">Segmenting → grid → YOLO classify</p>
          </div>
        </div>
      )}

      {status === 'error' && error && <ErrorBanner message={error} />}

      {status === 'success' && result && (
        <div className="space-y-4 animate-fade-up">
          <ResultCard
            risk={result.risk}
            label={result.risk >= 0.35 ? 'Reversal patterns detected' : 'No significant reversals'}
            meta={[
              { key: 'Letters detected', value: result.total },
              { key: 'Reversals',        value: result.counts['Reversal'] ?? 0 },
              { key: 'Corrected',        value: result.counts['Corrected'] ?? 0 },
            ]}
            timestamp={new Date().toISOString()}
          />

          {result.total > 0 && (
            <div className="card p-5">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4">
                Letter Classification
              </p>
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
                      <span className="text-xs font-mono font-semibold w-6 text-right"
                        style={{ color: meta.color }}>{count}</span>
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
                    <div key={i}
                      className="flex flex-col items-center gap-0.5 px-2.5 py-2 bg-slate-50 rounded-lg border border-slate-200 min-w-[52px]">
                      <span className="text-base font-display font-700 text-slate-800">{d.label}</span>
                      <span className="text-[9px] font-medium" style={{ color: meta.color }}>
                        {d.orientation}
                      </span>
                      <span className="text-[9px] font-mono text-slate-400">{(d.conf * 100).toFixed(0)}%</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <button
            onClick={() => onComplete(result.risk, result.risk >= 0.35 ? 'reversal_detected' : 'no_reversal', result)}
            className="btn-primary w-full justify-center py-2.5"
          >
            Continue to Speech Test →
          </button>
        </div>
      )}
    </div>
  );
}

import React, { useState } from 'react';
import { PenLine, Image } from 'lucide-react';
import FileUpload from '../components/ui/FileUpload';
import ResultCard from '../components/ui/ResultCard';
import { LoadingSpinner, ErrorBanner } from '../components/ui/Feedback';
import { apiEndpoints } from '../lib/api';
import { HandwritingResult, AsyncState } from '../types';

const REVERSAL_INFO: Record<string, string> = {
  b_d_reversal:       'b/d confusion',
  p_q_reversal:       'p/q confusion',
  mirror_writing:     'Mirror writing',
  n_u_reversal:       'n/u confusion',
  letter_inversion:   'Vertical flip',
};

export default function HandwritingPage() {
  const [preview, setPreview] = useState<string | null>(null);
  const [state, setState]     = useState<AsyncState<HandwritingResult>>({
    status: 'idle', data: null, error: null,
  });

  const handleFile = async (file: File) => {
    setPreview(URL.createObjectURL(file));
    setState({ status: 'loading', data: null, error: null });
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await apiEndpoints.handwriting.score(fd);
      setState({ status: 'success', data: res.data, error: null });
    } catch (e: any) {
      setState({ status: 'error', data: null, error: e.message });
    }
  };

  const result = state.data;

  return (
    <div className="max-w-2xl mx-auto space-y-6 animate-fade-up">

      {/* Info */}
      <div className="card p-5 flex gap-4 items-start">
        <div className="w-9 h-9 rounded-xl bg-emerald-50 border border-emerald-100 flex items-center justify-center shrink-0">
          <PenLine size={16} className="text-emerald-600" />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-slate-800 mb-1">Handwriting Reversal Scoring</h2>
          <p className="text-xs text-slate-500 leading-relaxed">
            A <span className="font-medium text-slate-700">YOLOv8</span>-based detector identifies letter reversals
            and mirror-writing errors. Adaptive thresholding handles both clean and real-photo handwriting.
          </p>
        </div>
      </div>

      {/* Upload */}
      <div className="card p-6 space-y-4">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Upload Handwriting Sample</p>
        <FileUpload
          accept=".jpg,.jpeg,.png,.webp,.bmp"
          label="Drop a handwriting image"
          hint="JPG / PNG — clear scan or photo"
          onFile={handleFile}
          disabled={state.status === 'loading'}
        />

        {/* Image preview */}
        {preview && (
          <div className="rounded-xl overflow-hidden border border-slate-200 bg-slate-50">
            <img
              src={preview}
              alt="Handwriting preview"
              className="w-full max-h-48 object-contain"
            />
          </div>
        )}
      </div>

      {/* Loading */}
      {state.status === 'loading' && (
        <div className="card p-8 flex flex-col items-center gap-3 animate-fade-in">
          <LoadingSpinner size={28} />
          <p className="text-sm text-slate-500 font-medium">Running YOLO detection…</p>
        </div>
      )}

      {/* Error */}
      {state.status === 'error' && state.error && (
        <ErrorBanner message={state.error} />
      )}

      {/* Result */}
      {state.status === 'success' && result && (
        <div className="space-y-4 animate-fade-up">
          <ResultCard
            risk={result.risk}
            label={result.risk >= 0.35 ? 'Reversal patterns detected' : 'No significant reversals'}
            meta={[
              { key: 'Total detections', value: result.total },
            ]}
            timestamp={new Date().toISOString()}
          />

          {/* Category breakdown */}
          {result.counts && Object.keys(result.counts).length > 0 && (
            <div className="card p-5">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4">
                Reversal Breakdown
              </p>
              <div className="space-y-3">
                {Object.entries(result.counts).map(([key, count]) => {
                  const max = Math.max(...Object.values(result.counts));
                  const pct = max > 0 ? count / max : 0;
                  return (
                    <div key={key} className="flex items-center gap-3">
                      <span className="text-xs text-slate-500 w-36 shrink-0">
                        {REVERSAL_INFO[key] ?? key}
                      </span>
                      <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-brand-400 rounded-full transition-all duration-700"
                          style={{ width: `${pct * 100}%` }}
                        />
                      </div>
                      <span className="text-xs font-mono text-slate-500 w-4 text-right">{count}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Letter detail */}
          {result.letter_detail?.length > 0 && (
            <div className="card p-5">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
                Detected Letters
              </p>
              <div className="flex flex-wrap gap-2">
                {result.letter_detail.map((d, i) => (
                  <div key={i} className="flex flex-col items-center gap-0.5 px-3 py-2 bg-slate-50 rounded-lg border border-slate-200">
                    <span className="text-lg font-display font-700 text-slate-800">{d.label}</span>
                    <span className="text-[10px] text-slate-400">{d.orientation}</span>
                    <span className="text-[10px] font-mono text-slate-400">{(d.conf * 100).toFixed(0)}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

import React, { useState } from 'react';
import { Mic, PlayCircle } from 'lucide-react';
import FileUpload from '../components/ui/FileUpload';
import ResultCard from '../components/ui/ResultCard';
import { LoadingSpinner, ErrorBanner } from '../components/ui/Feedback';
import { apiEndpoints } from '../lib/api';
import { DysarthriaResult, AsyncState } from '../types';

const TIPS = [
  'Use a WAV file sampled at 16 kHz or higher',
  'Minimum 2 seconds of speech recommended',
  'Avoid background noise for best accuracy',
  'Supported: .wav, .flac, .ogg',
];

export default function DysarthriaPage() {
  const [state, setState] = useState<AsyncState<DysarthriaResult>>({
    status: 'idle', data: null, error: null,
  });

  const handleFile = async (file: File) => {
    setState({ status: 'loading', data: null, error: null });
    try {
      const fd = new FormData();
      fd.append('file', file);
      const res = await apiEndpoints.dysarthria.predict(fd);
      setState({ status: 'success', data: res.data, error: null });
    } catch (e: any) {
      setState({ status: 'error', data: null, error: e.message });
    }
  };

  const result = state.data;

  return (
    <div className="max-w-2xl mx-auto space-y-6 animate-fade-up">

      {/* Info banner */}
      <div className="card p-5 flex gap-4 items-start">
        <div className="w-9 h-9 rounded-xl bg-violet-50 border border-violet-100 flex items-center justify-center shrink-0">
          <Mic size={16} className="text-violet-600" />
        </div>
        <div>
          <h2 className="text-sm font-semibold text-slate-800 mb-1">Speech Disorder Detection</h2>
          <p className="text-xs text-slate-500 leading-relaxed">
            Uses a <span className="font-medium text-slate-700">CNN + BiLSTM</span> model trained on the TORGO dataset
            with speaker-stratified k-fold validation. MFCC features (n=40) are extracted per 3-second chunk
            and aggregated via attention pooling.
          </p>
        </div>
      </div>

      {/* Upload */}
      <div className="card p-6">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4">Upload Audio</p>
        <FileUpload
          accept=".wav,.flac,.ogg,.mp3"
          label="Drop a WAV / audio file here"
          hint="or click to browse"
          onFile={handleFile}
          disabled={state.status === 'loading'}
        />

        {/* Tips */}
        <ul className="mt-4 space-y-1.5">
          {TIPS.map((t) => (
            <li key={t} className="flex items-start gap-2 text-xs text-slate-400">
              <span className="mt-0.5 w-1 h-1 rounded-full bg-slate-300 shrink-0" />
              {t}
            </li>
          ))}
        </ul>
      </div>

      {/* Loading */}
      {state.status === 'loading' && (
        <div className="card p-8 flex flex-col items-center gap-3 animate-fade-in">
          <LoadingSpinner size={28} />
          <p className="text-sm text-slate-500 font-medium">Analysing audio…</p>
          <p className="text-xs text-slate-400">Extracting MFCC features and running inference</p>
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
            label={result.label === 'dysarthria' ? 'Dysarthria detected' : 'No dysarthria detected'}
            confidence={result.confidence}
            meta={[
              { key: 'Chunks analysed', value: result.n_chunks },
              { key: 'Avg risk score',  value: `${(result.risk * 100).toFixed(1)}%` },
            ]}
            timestamp={new Date().toISOString()}
          />

          {/* Chunk breakdown */}
          {result.chunk_risks?.length > 0 && (
            <div className="card p-5">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
                Per-chunk Risk <span className="font-mono text-slate-300 ml-1">(3s windows)</span>
              </p>
              <div className="space-y-2">
                {result.chunk_risks.map((r, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <span className="text-[11px] text-slate-400 font-mono w-10">
                      {String(i + 1).padStart(2, '0')}
                    </span>
                    <div className="flex-1 h-2 bg-slate-100 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all duration-700"
                        style={{
                          width: `${r * 100}%`,
                          backgroundColor: r < 0.35 ? '#10b981' : r < 0.65 ? '#f59e0b' : '#ef4444',
                          transitionDelay: `${i * 60}ms`,
                        }}
                      />
                    </div>
                    <span className="text-[11px] font-mono text-slate-500 w-10 text-right">
                      {(r * 100).toFixed(0)}%
                    </span>
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

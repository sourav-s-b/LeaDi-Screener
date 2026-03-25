import React, { useState } from 'react';
import { BarChart3, Upload } from 'lucide-react';
import { LoadingSpinner, ErrorBanner, EmptyState } from '../components/ui/Feedback';
import { apiEndpoints } from '../lib/api';
import { EvalReport, ToolId, AsyncState } from '../types';

const TOOLS: { id: ToolId; label: string }[] = [
  { id: 'dysarthria',  label: 'Dysarthria'  },
  { id: 'dyslexia',    label: 'Dyslexia'    },
  { id: 'handwriting', label: 'Handwriting' },
];

const METRICS: { key: keyof EvalReport; label: string; fmt: (v: number) => string }[] = [
  { key: 'accuracy',    label: 'Accuracy',    fmt: (v) => `${(v * 100).toFixed(2)}%` },
  { key: 'sensitivity', label: 'Sensitivity', fmt: (v) => `${(v * 100).toFixed(2)}%` },
  { key: 'specificity', label: 'Specificity', fmt: (v) => `${(v * 100).toFixed(2)}%` },
  { key: 'roc_auc',     label: 'ROC-AUC',     fmt: (v) => v.toFixed(4)               },
  { key: 'pr_auc',      label: 'PR-AUC',      fmt: (v) => v.toFixed(4)               },
  { key: 'n_samples',   label: 'Samples',     fmt: (v) => String(v)                  },
];

export default function EvaluatePage() {
  const [tool, setTool]   = useState<ToolId>('dysarthria');
  const [state, setState] = useState<AsyncState<EvalReport>>({
    status: 'idle', data: null, error: null,
  });

  const run = async (file: File) => {
    setState({ status: 'loading', data: null, error: null });
    try {
      const fd = new FormData();
      fd.append('file', file);
      const ep = tool === 'dysarthria'
        ? apiEndpoints.dysarthria.evaluate(fd)
        : tool === 'dyslexia'
        ? apiEndpoints.dyslexia.evaluate(fd)
        : apiEndpoints.handwriting.evaluate(fd);
      const res = await ep;
      setState({ status: 'success', data: res.data, error: null });
    } catch (e: any) {
      setState({ status: 'error', data: null, error: e.message });
    }
  };

  const report = state.data;

  return (
    <div className="max-w-2xl mx-auto space-y-6 animate-fade-up">
      {/* Tool picker */}
      <div className="card p-5">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Select Module</p>
        <div className="flex gap-2">
          {TOOLS.map(({ id, label }) => (
            <button
              key={id}
              onClick={() => setTool(id)}
              className={tool === id ? 'btn-primary text-sm' : 'btn-secondary text-sm'}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Dataset upload */}
      <div className="card p-6">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
          Upload Test Dataset
        </p>
        <label className="flex flex-col items-center gap-3 border-2 border-dashed border-slate-200 rounded-xl py-8 px-6 cursor-pointer hover:border-brand-300 hover:bg-brand-50/30 transition-all">
          <div className="w-10 h-10 rounded-xl bg-slate-100 flex items-center justify-center">
            <Upload size={17} className="text-slate-400" />
          </div>
          <span className="text-sm text-slate-600 font-medium">Upload dataset ZIP or CSV</span>
          <span className="text-xs text-slate-400">Must match training data format</span>
          <input
            type="file"
            accept=".zip,.csv,.tar.gz"
            className="hidden"
            onChange={(e) => { const f = e.target.files?.[0]; if (f) run(f); }}
          />
        </label>
      </div>

      {state.status === 'loading' && (
        <div className="card p-10 flex flex-col items-center gap-3 animate-fade-in">
          <LoadingSpinner size={28} />
          <p className="text-sm text-slate-500 font-medium">Running evaluation…</p>
          <p className="text-xs text-slate-400">This may take a minute depending on dataset size</p>
        </div>
      )}

      {state.status === 'error' && state.error && <ErrorBanner message={state.error} />}

      {state.status === 'success' && report && (
        <div className="space-y-4 animate-fade-up">
          {/* Metrics grid */}
          <div className="card p-5">
            <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4">
              Evaluation Metrics
            </p>
            <div className="grid grid-cols-3 gap-4">
              {METRICS.map(({ key, label, fmt }) => {
                const val = report[key] as number;
                return (
                  <div key={key} className="flex flex-col gap-1 p-3 bg-slate-50 rounded-xl">
                    <span className="text-[11px] text-slate-400">{label}</span>
                    <span className="text-lg font-display font-700 text-slate-900">{fmt(val)}</span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Confusion matrix */}
          {report.conf_matrix && (
            <div className="card p-5">
              <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4">
                Confusion Matrix
              </p>
              <div className="flex flex-col items-center gap-1">
                {['Predicted −', 'Predicted +'].map((col, ci) => (
                  <div key={col} className="text-[10px] text-slate-400" />
                ))}
                <div className="grid grid-cols-2 gap-2 w-48">
                  {report.conf_matrix.flat().map((v, i) => {
                    const labels = ['TN', 'FP', 'FN', 'TP'];
                    const colors = ['bg-emerald-50 text-emerald-700', 'bg-red-50 text-red-600', 'bg-red-50 text-red-600', 'bg-emerald-50 text-emerald-700'];
                    return (
                      <div key={i} className={`rounded-xl p-4 flex flex-col items-center gap-1 ${colors[i]}`}>
                        <span className="text-xl font-display font-700">{v}</span>
                        <span className="text-[10px] font-semibold opacity-70">{labels[i]}</span>
                      </div>
                    );
                  })}
                </div>
                <div className="text-[10px] text-slate-300 mt-2">Actual × Predicted</div>
              </div>
            </div>
          )}
        </div>
      )}

      {state.status === 'idle' && (
        <EmptyState
          icon={BarChart3}
          title="No evaluation run yet"
          body="Upload a labelled dataset to compute accuracy, ROC-AUC, confusion matrix, and more."
        />
      )}
    </div>
  );
}

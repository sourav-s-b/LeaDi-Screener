import React, { useState, useEffect } from 'react';
import { Server, Brain, Settings as Cog, Save, RotateCcw, Eye, Mic, PenLine } from 'lucide-react';
import StatusIndicator from '../components/ui/StatusIndicator';

interface Config {
  apiUrl:               string;
  dysarthriaModelPath:  string;
  dysarthriaWindowSec:  string;
  dysarthriaGender:     string;
  dyslexiaEnsemble:     string;
  dyslexiaRfecv:        string;
  dyslexiaMeta:         string;
  dyslexiaThreshold:    string;
  handwritingModelPath: string;
  
}

const DEFAULTS: Config = {
  apiUrl:               'http://localhost:8000',
  dysarthriaModelPath:  'models/dysarthria_cnn_bilstm.pt',
  dysarthriaWindowSec:  '6.79',
  dysarthriaGender:     'male',
  dyslexiaEnsemble:     'models/dyslexia_ensemble.joblib',
  dyslexiaRfecv:        'models/dyslexia_rfecv.joblib',
  dyslexiaMeta:         'models/dyslexia_feature_meta.json',
  dyslexiaThreshold:    '0.5',
  handwritingModelPath: 'models/best_mobilenet.pth',
  
};

const KEY = 'leadis_settings';

export default function SettingsPage() {
  const [cfg, setCfg]     = useState<Config>(DEFAULTS);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(KEY);
      if (raw) setCfg({ ...DEFAULTS, ...JSON.parse(raw) });
    } catch {}
  }, []);

  const set = (k: keyof Config) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setCfg(c => ({ ...c, [k]: e.target.value }));

  const save = () => {
    localStorage.setItem(KEY, JSON.stringify(cfg));
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const reset = () => { setCfg(DEFAULTS); localStorage.removeItem(KEY); };

  const Field = ({ label, k, hint, mono = false }: { label: string; k: keyof Config; hint?: string; mono?: boolean }) => (
    <div className="space-y-1.5">
      <label className="text-xs font-medium text-slate-600">{label}</label>
      <input value={cfg[k]} onChange={set(k)}
        className={`input ${mono ? 'font-mono text-[13px]' : ''}`} spellCheck={false} />
      {hint && <p className="text-[11px] text-slate-400">{hint}</p>}
    </div>
  );

  return (
    <div className="max-w-2xl mx-auto space-y-5 animate-fade-up">

      {/* API connection */}
      <div className="card p-6 space-y-4">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-8 h-8 rounded-lg bg-brand-50 border border-brand-100 flex items-center justify-center">
            <Server size={14} className="text-brand-600" />
          </div>
          <div className="flex-1">
            <h3 className="text-sm font-semibold text-slate-800">API Connection</h3>
            <p className="text-[11px] text-slate-400">FastAPI backend address</p>
          </div>
          <StatusIndicator />
        </div>
        <Field label="Backend URL" k="apiUrl" hint="Must match CORS_ORIGINS in backend .env" mono />
      </div>

      {/* Speech */}
      <div className="card p-6 space-y-4">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-8 h-8 rounded-lg bg-violet-50 border border-violet-100 flex items-center justify-center">
            <Mic size={14} className="text-violet-600" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-800">Dysarthria — Speech</h3>
            <p className="text-[11px] text-slate-400">CNN+BiLSTM model paths and params</p>
          </div>
        </div>
        <Field label="Model weights (.pt)" k="dysarthriaModelPath" mono />
        <div className="grid grid-cols-2 gap-4">
          <Field label="Window length (s)" k="dysarthriaWindowSec" mono hint="Default: 6.79 (match training)" />
          <Field label="Default gender" k="dysarthriaGender" mono hint="male | female" />
        </div>
        <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
          <p className="text-[11px] text-slate-500 leading-relaxed">
            These values are read by the backend at startup from <code className="font-mono bg-slate-100 px-1 rounded">.env</code>.
            Update <code className="font-mono bg-slate-100 px-1 rounded">backend/.env</code> to persist changes.
          </p>
        </div>
      </div>

      {/* Eye tracking */}
      <div className="card p-6 space-y-4">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-8 h-8 rounded-lg bg-sky-50 border border-sky-100 flex items-center justify-center">
            <Eye size={14} className="text-sky-600" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-800">Dyslexia — Eye Tracking</h3>
            <p className="text-[11px] text-slate-400">Ensemble model + RFECV selector + feature meta</p>
          </div>
        </div>
        <Field label="Ensemble model (.joblib)" k="dyslexiaEnsemble" mono />
        <Field label="RFECV selector (.joblib)"  k="dyslexiaRfecv"   mono />
        <Field label="Feature meta (.json)"       k="dyslexiaMeta"    mono />
        <div className="grid grid-cols-2 gap-4">
          <Field label="Decision threshold" k="dyslexiaThreshold" mono hint="Default: 0.5" />
        </div>
      </div>

      {/* Handwriting */}
      <div className="card p-6 space-y-4">
        <div className="flex items-center gap-3 mb-1">
          <div className="w-8 h-8 rounded-lg bg-emerald-50 border border-emerald-100 flex items-center justify-center">
            <PenLine size={14} className="text-emerald-600" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-800">Handwriting — YOLO</h3>
            <p className="text-[11px] text-slate-400">YOLOv8 letter reversal detector</p>
          </div>
        </div>
        <Field label="Handwriting model (.pth)" k="handwritingModelPath" mono />
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3">
        <button onClick={save} className="btn-primary">
          <Save size={14} /> {saved ? 'Saved!' : 'Save settings'}
        </button>
        <button onClick={reset} className="btn-secondary">
          <RotateCcw size={13} /> Reset to defaults
        </button>
      </div>

      <div className="p-4 bg-amber-50 border border-amber-100 rounded-xl">
        <p className="text-[11px] text-amber-700 leading-relaxed">
          <strong>Note:</strong> Settings saved here are stored in your browser (localStorage) for reference only.
          The backend reads configuration from <code className="font-mono bg-amber-100 px-1 rounded">backend/.env</code> at startup.
          To actually change model paths or thresholds, edit that file and restart the backend.
        </p>
      </div>

    </div>
  );
}

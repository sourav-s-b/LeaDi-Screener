import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Compass } from 'lucide-react';

export default function NotFound() {
  const navigate = useNavigate();
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center animate-fade-in">
      <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mb-5">
        <Compass size={24} className="text-slate-400" strokeWidth={1.5} />
      </div>
      <h2 className="text-lg font-display font-700 text-slate-800 mb-1">Page not found</h2>
      <p className="text-sm text-slate-400 mb-6">The route you requested doesn't exist.</p>
      <button onClick={() => navigate('/')} className="btn-primary">
        Back to Overview
      </button>
    </div>
  );
}

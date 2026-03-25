import React from 'react';
import { useLocation } from 'react-router-dom';
import { Bell } from 'lucide-react';
import StatusIndicator from '../ui/StatusIndicator';

const TITLES: Record<string, { title: string; subtitle: string }> = {
  '/':           { title: 'Home',       subtitle: 'Dyslexia & Dysarthria Screening'    },
  '/screening':  { title: 'Screening',  subtitle: 'Complete the three-module assessment' },
  '/sessions':   { title: 'Sessions',   subtitle: 'All past screening results'           },
  '/settings':   { title: 'Settings',   subtitle: 'Configuration & model paths'          },
};

export default function Header() {
  const { pathname } = useLocation();
  const base = '/' + pathname.split('/')[1];
  const meta = TITLES[base] ?? { title: 'LeaDis', subtitle: '' };

  return (
    <header className="fixed top-0 right-0 h-[60px] bg-white border-b border-slate-100 flex items-center px-6 gap-4 z-20"
      style={{ left: 'var(--nav-w, 240px)' }}>
      <div className="flex-1 min-w-0">
        <h1 className="text-[15px] font-semibold text-slate-900 leading-none">{meta.title}</h1>
        {meta.subtitle && <p className="text-[11px] text-slate-400 mt-0.5">{meta.subtitle}</p>}
      </div>
      <div className="flex items-center gap-2">
        <StatusIndicator />
        <button className="btn-ghost p-2 rounded-lg"><Bell size={15} /></button>
      </div>
    </header>
  );
}

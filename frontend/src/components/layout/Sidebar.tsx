import React from 'react';
import { NavLink } from 'react-router-dom';
import { Home, PlayCircle, Activity, BarChart3, Settings } from 'lucide-react';

const NAV = [
  { to: '/',         icon: Home,        label: 'Home',     end: true },
  { to: '/screening',icon: PlayCircle,  label: 'Screening'           },
  { to: '/sessions', icon: Activity,    label: 'Sessions'            },
];
const BOTTOM = [
  { to: '/settings', icon: Settings, label: 'Settings' },
];

export default function Sidebar() {
  return (
    <aside className="fixed top-0 left-0 h-screen bg-white border-r border-slate-100 flex flex-col z-30"
      style={{ width: 'var(--nav-w, 240px)' }}>
      {/* Logo */}
      <div className="h-[60px] flex items-center px-5 border-b border-slate-100 shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 bg-brand-600 rounded-lg flex items-center justify-center">
            <Activity size={14} className="text-white" strokeWidth={2.5} />
          </div>
          <span className="font-display text-[15px] font-bold text-slate-900 tracking-tight">LeaDis</span>
        </div>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto scrollbar-thin">
        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-widest px-3 mb-2">Navigation</p>
        {NAV.map(({ to, icon: Icon, label, end }) => (
          <NavLink key={to} to={to} end={end}
            className={({ isActive }) => isActive ? 'nav-item-active' : 'nav-item'}>
            <Icon size={16} strokeWidth={1.75} className="shrink-0" />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="px-3 pb-4 space-y-0.5 border-t border-slate-100 pt-3">
        {BOTTOM.map(({ to, icon: Icon, label }) => (
          <NavLink key={to} to={to}
            className={({ isActive }) => isActive ? 'nav-item-active' : 'nav-item'}>
            <Icon size={16} strokeWidth={1.75} className="shrink-0" />
            <span>{label}</span>
          </NavLink>
        ))}
        <div className="px-3 pt-2">
          <p className="text-[11px] text-slate-300 font-mono">v0.1.0-alpha</p>
        </div>
      </div>
    </aside>
  );
}

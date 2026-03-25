import React from 'react';
import { LucideIcon, Inbox } from 'lucide-react';

// ── LoadingSpinner ────────────────────────────────────────────────────────────

export function LoadingSpinner({ size = 20, className = '' }: { size?: number; className?: string }) {
  return (
    <svg
      width={size} height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={`animate-spin text-brand-500 ${className}`}
    >
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2.5" strokeOpacity="0.2" />
      <path
        d="M12 2a10 10 0 0 1 10 10"
        stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"
      />
    </svg>
  );
}

// ── EmptyState ────────────────────────────────────────────────────────────────

interface EmptyStateProps {
  icon?:    LucideIcon;
  title:    string;
  body?:    string;
  action?:  React.ReactNode;
}

export function EmptyState({ icon: Icon = Inbox, title, body, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-6 text-center animate-fade-in">
      <div className="w-12 h-12 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
        <Icon size={20} className="text-slate-400" strokeWidth={1.5} />
      </div>
      <h3 className="text-sm font-semibold text-slate-700 mb-1">{title}</h3>
      {body && <p className="text-xs text-slate-400 max-w-[280px] leading-relaxed">{body}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

// ── ErrorBanner ───────────────────────────────────────────────────────────────

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-3 p-4 bg-red-50 border border-red-100 rounded-xl animate-fade-in">
      <div className="w-5 h-5 rounded-full bg-red-100 flex items-center justify-center shrink-0 mt-0.5">
        <span className="text-red-600 text-xs font-bold">!</span>
      </div>
      <div>
        <p className="text-sm font-medium text-red-800">Analysis failed</p>
        <p className="text-xs text-red-600 mt-0.5">{message}</p>
      </div>
    </div>
  );
}

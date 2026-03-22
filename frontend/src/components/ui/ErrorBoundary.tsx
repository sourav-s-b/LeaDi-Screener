import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle } from 'lucide-react';

interface Props  { children: ReactNode; }
interface State  { hasError: boolean; message: string; }

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: '' };

  static getDerivedStateFromError(err: Error): State {
    return { hasError: true, message: err.message };
  }

  componentDidCatch(err: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', err, info);
  }

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <div className="flex flex-col items-center justify-center py-20 px-6 text-center animate-fade-in">
        <div className="w-12 h-12 rounded-2xl bg-red-50 border border-red-100 flex items-center justify-center mb-4">
          <AlertTriangle size={20} className="text-red-400" strokeWidth={1.5} />
        </div>
        <h3 className="text-sm font-semibold text-slate-800 mb-1">Something went wrong</h3>
        <p className="text-xs text-slate-400 max-w-xs mb-5 font-mono leading-relaxed">
          {this.state.message}
        </p>
        <button
          className="btn-secondary text-xs"
          onClick={() => this.setState({ hasError: false, message: '' })}
        >
          Try again
        </button>
      </div>
    );
  }
}

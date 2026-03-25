import React, { useEffect, useState } from 'react';
import { apiEndpoints } from '../../lib/api';

type Status = 'checking' | 'online' | 'offline';

export default function StatusIndicator() {
  const [status, setStatus] = useState<Status>('checking');

  useEffect(() => {
    const check = async () => {
      try {
        await apiEndpoints.health();
        setStatus('online');
      } catch {
        setStatus('offline');
      }
    };
    check();
    const id = setInterval(check, 30000);
    return () => clearInterval(id);
  }, []);

  const config = {
    checking: { dot: 'bg-amber-400 animate-pulse-slow', text: 'Connecting…', textColor: 'text-amber-600' },
    online:   { dot: 'bg-emerald-400',                  text: 'API online',  textColor: 'text-emerald-600' },
    offline:  { dot: 'bg-red-400 animate-pulse',        text: 'API offline', textColor: 'text-red-500'     },
  }[status];

  return (
    <div className="flex items-center gap-1.5 px-2.5 py-1 bg-slate-50 border border-slate-200 rounded-full">
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${config.dot}`} />
      <span className={`text-[11px] font-medium ${config.textColor}`}>{config.text}</span>
    </div>
  );
}

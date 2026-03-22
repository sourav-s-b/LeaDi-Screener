import React, { useCallback, useRef, useState } from 'react';
import { Upload, X, FileAudio, FileImage, File } from 'lucide-react';

interface FileUploadProps {
  accept?:     string;
  label?:      string;
  hint?:       string;
  onFile:      (file: File) => void;
  disabled?:   boolean;
}

function fileIcon(type: string) {
  if (type.startsWith('audio')) return FileAudio;
  if (type.startsWith('image')) return FileImage;
  return File;
}

export default function FileUpload({
  accept,
  label = 'Drop file here',
  hint,
  onFile,
  disabled,
}: FileUploadProps) {
  const [dragging, setDragging] = useState(false);
  const [picked, setPicked]     = useState<File | null>(null);
  const ref = useRef<HTMLInputElement>(null);

  const handleFile = useCallback((f: File) => {
    setPicked(f);
    onFile(f);
  }, [onFile]);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f) handleFile(f);
  }, [handleFile]);

  const clear = (e: React.MouseEvent) => {
    e.stopPropagation();
    setPicked(null);
    if (ref.current) ref.current.value = '';
  };

  const Icon = picked ? fileIcon(picked.type) : Upload;

  return (
    <div
      onClick={() => !disabled && !picked && ref.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={[
        'relative flex flex-col items-center justify-center gap-3',
        'border-2 border-dashed rounded-xl px-6 py-8 text-center',
        'transition-all duration-200 select-none',
        disabled
          ? 'border-slate-100 bg-slate-50 cursor-not-allowed opacity-50'
          : picked
          ? 'border-brand-200 bg-brand-50 cursor-default'
          : dragging
          ? 'border-brand-400 bg-brand-50 cursor-copy scale-[1.01]'
          : 'border-slate-200 bg-white hover:border-brand-300 hover:bg-brand-50/40 cursor-pointer',
      ].join(' ')}
    >
      <input
        ref={ref}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
        disabled={disabled}
      />

      <div className={`w-10 h-10 rounded-xl flex items-center justify-center
        ${picked ? 'bg-brand-100' : 'bg-slate-100'}`}>
        <Icon size={18} className={picked ? 'text-brand-600' : 'text-slate-400'} />
      </div>

      {picked ? (
        <div className="flex flex-col items-center gap-1">
          <p className="text-sm font-medium text-slate-800 max-w-[200px] truncate">{picked.name}</p>
          <p className="text-xs text-slate-400">{(picked.size / 1024).toFixed(1)} KB</p>
          <button
            onClick={clear}
            className="mt-1 flex items-center gap-1 text-xs text-red-500 hover:text-red-700 font-medium"
          >
            <X size={11} /> Remove
          </button>
        </div>
      ) : (
        <div className="flex flex-col items-center gap-1">
          <p className="text-sm font-medium text-slate-700">{label}</p>
          {hint && <p className="text-xs text-slate-400">{hint}</p>}
        </div>
      )}
    </div>
  );
}

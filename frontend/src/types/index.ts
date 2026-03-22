// ── Tool types ────────────────────────────────────────────────────────────────

export type ToolId = 'dysarthria' | 'dyslexia' | 'handwriting';

export interface ToolMeta {
  id:          ToolId;
  label:       string;
  description: string;
  icon:        string;
  color:       string;
  accent:      string;
}

// ── Prediction results ────────────────────────────────────────────────────────

export interface DysarthriaResult {
  risk:         number;          // 0–1
  label:        'dysarthria' | 'non_dysarthria';
  confidence:   number;
  n_chunks:     number;
  chunk_risks:  number[];
  wav_path?:    string;
}

export interface DyslexiaResult {
  risk:                number;
  label:               string;
  confidence:          number;
  n_fixations:         number;
  n_regressions:       number;
  regression_rate:     number;
  recording_duration:  number;
}

export interface HandwritingResult {
  risk:          number;
  counts:        Record<string, number>;
  total:         number;
  letter_detail: LetterDetail[];
}

export interface LetterDetail {
  label:       string;
  orientation: string;
  conf:        number;
}

export type AnyResult = DysarthriaResult | DyslexiaResult | HandwritingResult;

// ── Session (stored result) ───────────────────────────────────────────────────

export interface Session {
  id:        string;
  tool:      ToolId;
  timestamp: string;            // ISO string
  risk:      number;
  label:     string;
  result:    AnyResult;
}

// ── Evaluation report ────────────────────────────────────────────────────────

export interface EvalReport {
  accuracy:    number;
  sensitivity: number;
  specificity: number;
  roc_auc:     number;
  pr_auc:      number;
  conf_matrix: number[][];
  n_samples:   number;
}

// ── UI state ─────────────────────────────────────────────────────────────────

export type Status = 'idle' | 'loading' | 'success' | 'error';

export interface AsyncState<T> {
  status: Status;
  data:   T | null;
  error:  string | null;
}

// ── Session summary (list view) ───────────────────────────────────────────────

export interface SessionSummary {
  id:        string;
  tool:      ToolId;
  timestamp: string;
  risk:      number;
  label:     string;
}

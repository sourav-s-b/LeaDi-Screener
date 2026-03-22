"""
dysarthria_engine.py
====================
Pure inference + metrics module for the dysarthria CNN classifier.
Zero UI dependencies — import this into any UI, script, or pipeline.

Usage
-----
from dysarthria_engine import DysarthriaEngine

engine = DysarthriaEngine("best_speech_cnn_v2.pt")

# Single file — any length, chunked automatically
result = engine.predict("audio.wav")
print(result)

# Evaluate on dataset
report = engine.evaluate_torgo_folder("torgo-audio/")
print(report.summary())
report.plot()
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any

import numpy as np
import torch
import torch.nn as nn

try:
    import soundfile as sf
    import librosa
    _AUDIO_AVAILABLE = True
except ImportError:
    _AUDIO_AVAILABLE = False

try:
    import pandas as pd
    _PANDAS_AVAILABLE = True
except ImportError:
    _PANDAS_AVAILABLE = False

try:
    from sklearn.metrics import (
        confusion_matrix, classification_report,
        roc_auc_score, roc_curve, auc,
        precision_recall_curve
    )
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False


# ──────────────────────────────────────────────
# Model (must match trained architecture)
# ──────────────────────────────────────────────
class CNNBiLSTM(nn.Module):
    """
    CNN + BiLSTM + Attention + Gender embedding.
    Input: (B, 1, 120, T)  — stacked MFCC+delta+delta-delta, 120 channels
    Gender: (B,) int tensor, 0=male 1=female
    Returns: (logits (B,2), severity (B,))
    """
    def __init__(self, n_feat: int = 120, lstm_hidden: int = 128,
                 lstm_layers: int = 2, dropout: float = 0.4, n_classes: int = 2):
        super().__init__()
        self.cnn = nn.Sequential(
            nn.Conv2d(1,  32, 3, padding=1), nn.BatchNorm2d(32),  nn.ReLU(True), nn.MaxPool2d(2),
            nn.Conv2d(32, 64, 3, padding=1), nn.BatchNorm2d(64),  nn.ReLU(True), nn.MaxPool2d(2),
            nn.Conv2d(64,128, 3, padding=1), nn.BatchNorm2d(128), nn.ReLU(True), nn.MaxPool2d((2, 1)),
        )
        cnn_freq_out      = n_feat // 8          # 120//8 = 15
        self.cnn_feat_dim = 128 * cnn_freq_out   # 1920
        self.bilstm = nn.LSTM(
            input_size=self.cnn_feat_dim, hidden_size=lstm_hidden,
            num_layers=lstm_layers, batch_first=True, bidirectional=True,
            dropout=dropout if lstm_layers > 1 else 0.0,
        )
        lstm_out         = 2 * lstm_hidden        # 256
        self.attn        = nn.Linear(lstm_out, 1)
        self.dropout     = nn.Dropout(dropout)
        self.gender_emb  = nn.Embedding(2, 16)
        self.classifier  = nn.Sequential(
            nn.Linear(lstm_out + 16, 64), nn.ReLU(True), nn.Dropout(dropout),
            nn.Linear(64, n_classes),
        )
        self.severity_head = nn.Sequential(
            nn.Linear(lstm_out, 32), nn.ReLU(True), nn.Linear(32, 1),
        )

    def _attn_pool(self, x: torch.Tensor) -> torch.Tensor:
        w = torch.softmax(self.attn(x).squeeze(-1), dim=1).unsqueeze(-1)
        return (x * w).sum(dim=1)

    def forward(self, x: torch.Tensor, gender: torch.Tensor):
        feat = self.cnn(x)
        B, C, F, T = feat.shape
        feat = feat.permute(0, 3, 1, 2).reshape(B, T, C * F)
        out, _   = self.bilstm(feat)
        pooled   = self.dropout(self._attn_pool(out))
        g_emb    = self.gender_emb(gender)
        logits   = self.classifier(torch.cat([pooled, g_emb], dim=1))
        severity = self.severity_head(pooled).squeeze(-1)
        return logits, severity


# ──────────────────────────────────────────────
# Return types
# ──────────────────────────────────────────────
@dataclass
class Prediction:
    wav_path:    str
    risk:        float          # P(dysarthria) in [0, 1]
    label:       str            # "dysarthria" or "non_dysarthria"
    confidence:  float          # probability of winning class
    n_chunks:    int   = 1      # windows averaged
    chunk_risks: List[float] = field(default_factory=list)
    error:       Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __str__(self) -> str:
        if self.error:
            return f"[ERROR] {self.wav_path}: {self.error}"
        bar = "█" * int(self.risk * 20) + "░" * (20 - int(self.risk * 20))
        chunk_str = ""
        if self.n_chunks > 1:
            chunk_str = (
                f"\n  Chunks    : {self.n_chunks} windows averaged  "
                f"{[round(r, 3) for r in self.chunk_risks]}"
            )
        return (
            f"File      : {Path(self.wav_path).name}\n"
            f"Risk      : [{bar}] {self.risk:.4f}\n"
            f"Prediction: {self.label.upper()} (confidence {self.confidence:.2%})"
            f"{chunk_str}"
        )


@dataclass
class EvaluationReport:
    predictions:  List[Prediction]
    true_labels:  List[int]
    pred_labels:  List[int]
    probs:        List[float]

    accuracy:    float = field(init=False)
    sensitivity: float = field(init=False)
    specificity: float = field(init=False)
    roc_auc:     float = field(init=False)
    pr_auc:      float = field(init=False)
    conf_matrix: Any   = field(init=False)
    report_dict: Dict  = field(init=False)

    def __post_init__(self):
        if not _SKLEARN_AVAILABLE:
            raise ImportError("pip install scikit-learn")

        y_true = np.array(self.true_labels)
        y_pred = np.array(self.pred_labels)
        y_prob = np.array(self.probs)

        self.conf_matrix = confusion_matrix(y_true, y_pred)
        self.report_dict = classification_report(
            y_true, y_pred,
            target_names=["non_dysarthria", "dysarthria"],
            output_dict=True
        )
        tn, fp, fn, tp   = self.conf_matrix.ravel()
        self.accuracy    = float((tp + tn) / max(1, len(y_true)))
        self.sensitivity = float(tp / max(1, tp + fn))
        self.specificity = float(tn / max(1, tn + fp))
        self.roc_auc     = float(roc_auc_score(y_true, y_prob))
        precision, recall, _ = precision_recall_curve(y_true, y_prob)
        self.pr_auc      = float(auc(recall, precision))

    def summary(self) -> str:
        tn, fp, fn, tp = self.conf_matrix.ravel()
        return "\n".join([
            "=" * 50,
            "  DYSARTHRIA CLASSIFIER — EVALUATION REPORT",
            "=" * 50,
            f"  Samples       : {len(self.true_labels)}",
            f"  Accuracy      : {self.accuracy:.4f}  ({self.accuracy*100:.2f}%)",
            f"  Sensitivity   : {self.sensitivity:.4f}  (dysarthria recall)",
            f"  Specificity   : {self.specificity:.4f}  (healthy recall)",
            f"  ROC-AUC       : {self.roc_auc:.4f}",
            f"  PR-AUC        : {self.pr_auc:.4f}",
            "-" * 50,
            f"  TP={tp}  TN={tn}  FP={fp}  FN={fn}",
            "=" * 50,
        ])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accuracy":    self.accuracy,
            "sensitivity": self.sensitivity,
            "specificity": self.specificity,
            "roc_auc":     self.roc_auc,
            "pr_auc":      self.pr_auc,
            "conf_matrix": self.conf_matrix.tolist(),
            "report":      self.report_dict,
        }

    def save(self, path: str):
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        print(f"Metrics saved → {path}")

    def plot(self, save_path: Optional[str] = None, show: bool = True):
        try:
            import matplotlib.pyplot as plt
            import seaborn as sns
        except ImportError:
            print("pip install matplotlib seaborn")
            return

        y_true = np.array(self.true_labels)
        y_prob = np.array(self.probs)
        fpr, tpr, _          = roc_curve(y_true, y_prob)
        precision, recall, _ = precision_recall_curve(y_true, y_prob)

        fig, axes = plt.subplots(1, 3, figsize=(15, 4))
        fig.suptitle(
            f"Accuracy={self.accuracy:.4f}  ROC-AUC={self.roc_auc:.4f}  PR-AUC={self.pr_auc:.4f}",
            fontweight="bold"
        )

        sns.heatmap(self.conf_matrix, annot=True, fmt="d", cmap="Blues", ax=axes[0],
                    xticklabels=["non_dys", "dys"], yticklabels=["non_dys", "dys"])
        axes[0].set_title("Confusion Matrix")
        axes[0].set_ylabel("True"); axes[0].set_xlabel("Predicted")

        axes[1].plot(fpr, tpr, color="steelblue", lw=2, label=f"AUC={self.roc_auc:.4f}")
        axes[1].plot([0, 1], [0, 1], "k--", lw=1)
        axes[1].set_title("ROC Curve")
        axes[1].set_xlabel("FPR"); axes[1].set_ylabel("TPR")
        axes[1].legend()

        axes[2].plot(recall, precision, color="darkorange", lw=2, label=f"AUC={self.pr_auc:.4f}")
        axes[2].set_title("Precision-Recall")
        axes[2].set_xlabel("Recall"); axes[2].set_ylabel("Precision")
        axes[2].legend()

        plt.tight_layout()
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches="tight")
            print(f"Plot saved → {save_path}")
        if show:
            plt.show()
        plt.close()


# ──────────────────────────────────────────────
# Audio helpers
# ──────────────────────────────────────────────


# ── Also add this to dysarthria_test.py recording callback ──
# In _stop_record(), before sf.write(), add:

def preprocess_recording(audio: np.ndarray) -> np.ndarray:
    """
    Apply same preprocessing to live recording before saving to tmp wav.
    Call this on the concatenated audio buffer before writing to disk.
    """
    # DC offset
    audio = audio - audio.mean()
    
    # soft clip repair
    clip_threshold = 0.95
    if (np.abs(audio) >= clip_threshold).mean() > 0.01:
        sign    = np.sign(audio)
        abs_a   = np.abs(audio)
        mask    = abs_a > clip_threshold
        excess  = (abs_a - clip_threshold) / (1.0 - clip_threshold + 1e-9)
        excess  = np.clip(excess, 0, 1)
        repaired = clip_threshold + (1.0 - clip_threshold) * (1 - (1 - excess) ** 3)
        audio   = np.where(mask, sign * repaired, audio)
    
    # normalize
    peak = np.abs(audio).max()
    if peak > 0:
        audio = audio / peak * 0.708
    
    return audio.astype(np.float32)

# ── Pitch normalization ─────────────────────────────────────────────────
_TARGET_F0 = 120.0   # canonical F0 — same as used during training

def _pitch_normalize(y: np.ndarray, sr: int,
                     target_f0: float = _TARGET_F0,
                     max_shift: float = 6.0) -> np.ndarray:
    """
    Shift audio to canonical F0 before feature extraction.
    Removes the spectral overlap between deep healthy voices and
    dysarthric speech — the main source of false positives.
    """
    try:
        f0, voiced_flag, _ = librosa.pyin(
            y, fmin=librosa.note_to_hz("C2"),
            fmax=librosa.note_to_hz("C6"),
            sr=sr, frame_length=2048,
        )
        voiced_f0 = f0[voiced_flag & ~np.isnan(f0)]
        if len(voiced_f0) < 5:
            return y
        speaker_f0 = float(np.median(voiced_f0))
        n_steps    = float(np.clip(12.0 * np.log2(target_f0 / speaker_f0), -max_shift, max_shift))
        if abs(n_steps) < 0.2:
            return y
        return librosa.effects.pitch_shift(y, sr=sr, n_steps=n_steps)
    except Exception:
        return y


def _feat_from_chunk(chunk: np.ndarray, sr: int, n_mfcc: int) -> np.ndarray:
    """
    Extract stacked MFCC + delta + delta-delta with pitch normalization.
    Returns (3*n_mfcc, T), z-score normalised.
    """
    chunk = _pitch_normalize(chunk, sr)
    mfcc  = librosa.feature.mfcc(y=chunk, sr=sr, n_mfcc=n_mfcc).astype(np.float32)
    d1    = librosa.feature.delta(mfcc)
    d2    = librosa.feature.delta(mfcc, order=2)
    feat  = np.concatenate([mfcc, d1, d2], axis=0)   # (120, T)
    return (feat - feat.mean()) / (feat.std() + 1e-6)


def _chunk_audio(y: np.ndarray, sr: int, window_sec: float, overlap_sec: float) -> List[np.ndarray]:
    """
    Split waveform into overlapping fixed-length windows.

    Short clips are zero-padded to window_sec.
    Long clips are split with overlap_sec overlap between windows.
    The last chunk is always included (padded if needed).
    """
    win_len = int(sr * window_sec)
    hop_len = max(int(sr * (window_sec - overlap_sec)), 1)

    if len(y) <= win_len:
        return [np.pad(y, (0, win_len - len(y)))]

    chunks = []
    start  = 0
    while start < len(y):
        chunk = y[start : start + win_len]
        if len(chunk) < win_len:
            chunk = np.pad(chunk, (0, win_len - len(chunk)))
        chunks.append(chunk)
        start += hop_len
        # stop if next window would be more than 50% silence padding
        if start + win_len * 0.5 > len(y):
            break
    return chunks


# ──────────────────────────────────────────────
# Engine
# ──────────────────────────────────────────────
LABEL_MAP  = {0: "non_dysarthria", 1: "dysarthria"}
LABEL_RMAP = {"non_dysarthria": 0, "dysarthria": 1}


class DysarthriaEngine:
    """
    Inference engine for dysarthria classification.

    Parameters
    ----------
    model_path : str | Path   — path to trained .pt weights
    seconds    : float        — window length used at training (default 6.79)
    overlap    : float        — overlap between chunks in seconds (default 3.0)
    sr         : int          — sample rate (default 16000)
    n_mfcc     : int          — MFCC coefficients (default 40)
    device     : str          — 'cuda', 'cpu', or 'auto'
    threshold  : float        — dysarthria decision threshold (default 0.5)

    How chunking works
    ------------------
    Any recording length is supported.
    Input audio is split into overlapping windows of `seconds` length.
    The model scores each window independently.
    Final risk = mean of all window scores.

    Example: 13s recording with seconds=6.79, overlap=3.0
        Window 1: 0.00s → 6.79s
        Window 2: 3.79s → 10.58s
        Window 3: 7.58s → 13.00s  (padded)
        Final risk = mean([w1, w2, w3])
    """

    def __init__(
        self,
        model_path: str,
        seconds:    float = 6.79,
        overlap:    float = 3.0,
        sr:         int   = 16000,
        n_mfcc:     int   = 40,
        device:     str   = "auto",
        threshold:  float = 0.5,
        gender:     str   = "male",   # "male" or "female" — used at inference
    ):
        self.seconds   = seconds
        self.overlap   = overlap
        self.sr        = sr
        self.n_mfcc    = n_mfcc
        self.n_feat    = 3 * n_mfcc   # 120
        self.threshold = threshold
        self.gender    = 0 if gender == "male" else 1
        self.device    = ("cuda" if torch.cuda.is_available() else "cpu") if device == "auto" else device

        self._model = CNNBiLSTM(n_feat=self.n_feat).to(self.device)
        self._model.load_state_dict(torch.load(model_path, map_location=self.device))
        self._model.eval()
        print(
            f"[Engine] Loaded  : {model_path}\n"
            f"         Device  : {self.device}\n"
            f"         Window  : {seconds}s  Overlap: {overlap}s\n"
            f"         Threshold: {threshold}  Gender: {gender}"
        )

    @torch.no_grad()
    def _score_chunk(self, chunk: np.ndarray) -> float:
        feat = _feat_from_chunk(chunk, self.sr, self.n_mfcc)
        x    = torch.from_numpy(feat).unsqueeze(0).unsqueeze(0).to(self.device)
        g    = torch.tensor([self.gender], dtype=torch.long).to(self.device)
        logits, _ = self._model(x, g)
        return torch.softmax(logits, dim=1)[0, 1].item()

    @torch.no_grad()
    def predict(self, wav_path: str) -> Prediction:
        """
        Predict dysarthria risk for a WAV file of any length.

        Short files  → zero-padded to window length, single prediction
        Long files   → split into overlapping windows, scores averaged

        Returns Prediction with .risk, .label, .confidence, .n_chunks, .chunk_risks
        """
        try:
            y      = self._load_audio(wav_path)
            chunks = _chunk_audio(y, self.sr, self.seconds, self.overlap)

            chunk_probs = [self._score_chunk(c) for c in chunks]
            risk        = float(np.mean(chunk_probs))
            label       = "dysarthria" if risk >= self.threshold else "non_dysarthria"
            conf        = risk if label == "dysarthria" else 1.0 - risk

            return Prediction(
                wav_path=wav_path,
                risk=round(risk, 4),
                label=label,
                confidence=round(conf, 4),
                n_chunks=len(chunks),
                chunk_risks=[round(p, 4) for p in chunk_probs],
            )
        except Exception as e:
            return Prediction(wav_path=wav_path, risk=-1.0,
                              label="error", confidence=0.0, error=str(e))

    def predict_batch(self, wav_paths: List[str]) -> List[Prediction]:
        results = []
        for i, p in enumerate(wav_paths):
            results.append(self.predict(p))
            if (i + 1) % 100 == 0:
                print(f"  {i+1}/{len(wav_paths)} processed")
        return results

    
    def _load_audio(self, wav_path: str) -> np.ndarray:
        """
        Load and preprocess audio for inference.
        
        Pipeline:
        1. Load + mono + resample
        2. Remove DC offset
        3. Soft-clip repair  (cubic softening of hard-clipped peaks)
        4. Normalize to safe level (-3 dBFS)
        5. Pad/trim to self.seconds
        """
        import soundfile as sf
        import numpy as np

        y, native_sr = sf.read(wav_path, dtype="float32", always_2d=False)
        if y.ndim == 2:
            y = y.mean(axis=1)
        if native_sr != self.sr:
            import librosa
            y = librosa.resample(y, orig_sr=native_sr, target_sr=self.sr)

        # 1. Remove DC offset — cheap mic bias throws off MFCC mean
        y = y - y.mean()

        # 2. Soft-clip repair
        #    Hard clipping (flat tops) creates spectral splatter that looks like
        #    dysarthric noise. Cubic softening smooths the flat tops back into
        #    plausible peaks without introducing new artifacts.
        clip_threshold = 0.95
        clipped = np.abs(y) >= clip_threshold
        if clipped.mean() > 0.01:   # only repair if >1% is clipped
            # cubic soft-knee: maps [0.95, 1.0] → smooth curve
            def softknee(x, threshold=0.95):
                mask = np.abs(x) > threshold
                sign = np.sign(x)
                excess = (np.abs(x) - threshold) / (1.0 - threshold)   # 0→1
                # cubic ease-out: smooth but doesn't overshoot
                repaired = threshold + (1.0 - threshold) * (1 - (1 - excess) ** 3)
                x = np.where(mask, sign * repaired, x)
                return x
            y = softknee(y)

        # 3. Normalize to -3 dBFS (0.708 linear peak)
        #    This is the most important step — TORGO was recorded at moderate
        #    levels; your hot mic is 3-4x louder going into the MFCC.
        peak = np.abs(y).max()
        if peak > 0:
            y = y / peak * 0.708

        # 4. Pad or trim to fixed window
        target_len = int(self.sr * self.seconds)
        if len(y) < target_len:
            y = np.pad(y, (0, target_len - len(y)))
        else:
            y = y[:target_len]

        return y.astype(np.float32)


    def evaluate_csv(
        self,
        csv_path:    str,
        audio_root:  str,
        max_samples: Optional[int] = None,
    ) -> EvaluationReport:
        if not _PANDAS_AVAILABLE:
            raise ImportError("pip install pandas")
        df = pd.read_csv(csv_path)
        if max_samples:
            df = df.sample(min(max_samples, len(df)), random_state=42)

        audio_root = Path(audio_root)
        predictions, true_labels, pred_labels, probs = [], [], [], []
        print(f"Evaluating {len(df)} samples...")

        for i, row in df.iterrows():
            rel = Path(row["filename"])
            if rel.parts and rel.parts[0].lower() in ("torgo_data", "torgo_pcm16k"):
                rel = Path(*rel.parts[1:])
            pred     = self.predict(str(audio_root / rel))
            true_int = LABEL_RMAP.get(row["is_dysarthria"], -1)
            predictions.append(pred)
            if pred.error is None and true_int >= 0:
                true_labels.append(true_int)
                pred_labels.append(LABEL_RMAP[pred.label])
                probs.append(pred.risk)
            if (i + 1) % 200 == 0:
                print(f"  {i+1}/{len(df)}")

        return EvaluationReport(predictions, true_labels, pred_labels, probs)

    def evaluate_torgo_folder(
        self,
        torgo_root:  str,
        max_samples: Optional[int] = None,
    ) -> EvaluationReport:
        torgo_root = Path(torgo_root)
        rows = []
        for top_dir, label in [
            ("F_Con", "non_dysarthria"), ("F_Dys", "dysarthria"),
            ("M_Con", "non_dysarthria"), ("M_Dys", "dysarthria"),
        ]:
            p = torgo_root / top_dir
            if p.exists():
                for wav in sorted(p.rglob("*.wav")):
                    rows.append((str(wav), label))

        if max_samples:
            import random; random.seed(42); random.shuffle(rows)
            rows = rows[:max_samples]

        print(f"Evaluating {len(rows)} samples...")
        predictions, true_labels, pred_labels, probs = [], [], [], []

        for i, (wav_path, true_label) in enumerate(rows):
            pred = self.predict(wav_path)
            predictions.append(pred)
            if pred.error is None:
                true_labels.append(LABEL_RMAP[true_label])
                pred_labels.append(LABEL_RMAP[pred.label])
                probs.append(pred.risk)
            if (i + 1) % 500 == 0:
                print(f"  {i+1}/{len(rows)}")

        return EvaluationReport(predictions, true_labels, pred_labels, probs)
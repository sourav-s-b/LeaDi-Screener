"""
dyslexia_eye_engine_v2.py
=========================
Universal inference engine for the dyslexia eye-tracking classifier.
Accepts any of the following input formats through a single predict() call:

    1. Path to A1R.txt file (Benfatto dataset format)
    2. Path to CSV file with columns: T, LX, LY, RX, RY
    3. pandas DataFrame with columns: LX, LY, RX, RY  (T optional)
    4. numpy array shape (N, 4) → [LX, LY, RX, RY]
       or shape (N, 5) → [T, LX, LY, RX, RY]

All formats are normalised to the same internal (N, 4) float array
and passed through the identical preprocessing + feature extraction
pipeline used during training.

Usage
-----
from dyslexia_eye_engine_v2 import DyslexiaEyeEngineV2

engine = DyslexiaEyeEngineV2(
    model_path = "dyslexia_ensemble.joblib",
    rfecv_path = "dyslexia_rfecv.joblib",
    meta_path  = "dyslexia_feature_meta.json",
)

# From file
result = engine.predict("Recording Data/111RP1/A1R.txt")

# From CSV
result = engine.predict("my_recording.csv")

# From DataFrame
import pandas as pd
df = pd.read_csv("my_recording.csv")
result = engine.predict(df)

# From numpy array
import numpy as np
arr = np.load("gaze.npy")   # shape (N, 4) or (N, 5)
result = engine.predict(arr)

print(result)
print(result.selected_features)   # dict of 18 selected feature values
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any, Union

import numpy as np

try:
    import pandas as pd
    _PANDAS_OK = True
except ImportError:
    _PANDAS_OK = False

try:
    import joblib
    _JOBLIB_OK = True
except ImportError:
    _JOBLIB_OK = False

try:
    from scipy.stats import skew, kurtosis
    _SCIPY_OK = True
except ImportError:
    _SCIPY_OK = False


# ──────────────────────────────────────────────────────────────────────────────
# Type alias for all accepted input formats
# ──────────────────────────────────────────────────────────────────────────────
GazeInput = Union[
    str,            # path to A1R.txt or .csv
    Path,           # same as str
    "pd.DataFrame", # DataFrame with LX, LY, RX, RY columns
    np.ndarray,     # (N,4) or (N,5) float array
]


# ──────────────────────────────────────────────────────────────────────────────
# Constants (must match training notebook exactly)
# ──────────────────────────────────────────────────────────────────────────────
SAMPLING_RATE      = 50        # Hz — Benfatto dataset recording rate
DT                 = 1.0 / SAMPLING_RATE
VELOCITY_THRESHOLD = 30.0      # degrees/sec — I-VT fixation threshold
MIN_FIXATION_DUR   = 0.08      # seconds
INVALID_THRESHOLD  = 40.0      # degrees — Tobii blink/invalid sentinel
MAX_BLINK_GAP      = 10        # samples (~200ms) — max gap to interpolate
SMOOTH_WINDOW      = 3         # samples — moving average window
N_BINS             = 10        # STFT bins


# ──────────────────────────────────────────────────────────────────────────────
# Return dataclass
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class EyePrediction:
    """
    Full prediction result returned by DyslexiaEyeEngineV2.predict().

    Attributes
    ----------
    source              : description of the input (filename, "DataFrame", "ndarray")
    risk                : P(dyslexic) in [0.0, 1.0]
    label               : "dyslexic" or "control"
    confidence          : probability of the winning class
    n_fixations         : number of fixations detected
    n_saccades          : number of saccades detected
    n_regressions       : number of backward saccades
    regression_rate     : regressions / total saccades
    mean_fix_duration   : mean fixation duration in seconds
    stft_entropy        : mean STFT entropy (spectral complexity)
    binocular_corr      : correlation between left and right eye x-movement
    selected_features   : dict of the 18 RFECV-selected feature values
    all_features        : dict of all 33 extracted feature values
    n_samples           : number of valid gaze samples after preprocessing
    recording_duration  : estimated recording duration in seconds
    error               : error message if prediction failed, else None
    """
    source:             str
    risk:               float
    label:              str
    confidence:         float
    n_fixations:        int            = 0
    n_saccades:         int            = 0
    n_regressions:      int            = 0
    regression_rate:    float          = 0.0
    mean_fix_duration:  float          = 0.0
    stft_entropy:       float          = 0.0
    binocular_corr:     float          = 0.0
    selected_features:  Dict[str, float] = field(default_factory=dict)
    all_features:       Dict[str, float] = field(default_factory=dict)
    n_samples:          int            = 0
    recording_duration: float          = 0.0
    error:              Optional[str]  = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def __str__(self) -> str:
        if self.error:
            return f"[ERROR] {self.source}: {self.error}"
        bar = "█" * int(self.risk * 20) + "░" * (20 - int(self.risk * 20))
        return "\n".join([
            f"Source          : {self.source}",
            f"Samples         : {self.n_samples}  ({self.recording_duration:.1f}s)",
            f"Risk            : [{bar}] {self.risk:.4f}",
            f"Prediction      : {self.label.upper()}  (confidence {self.confidence:.2%})",
            f"Fixations       : {self.n_fixations}   "
            f"Saccades: {self.n_saccades}   "
            f"Regressions: {self.n_regressions} ({self.regression_rate:.1%})",
            f"Mean fix dur    : {self.mean_fix_duration*1000:.0f}ms   "
            f"STFT entropy: {self.stft_entropy:.3f}   "
            f"Binocular corr: {self.binocular_corr:.3f}",
        ])


# ──────────────────────────────────────────────────────────────────────────────
# Input normalisation — all formats → (N, 4) float32 array [LX, LY, RX, RY]
# ──────────────────────────────────────────────────────────────────────────────

def _normalise_input(data: GazeInput) -> tuple[np.ndarray, str]:
    """
    Accept any supported input format and return:
        (array of shape (N, 4) with columns [LX, LY, RX, RY], source_label)

    Blink/invalid values (> INVALID_THRESHOLD) are replaced with NaN.
    """

    # ── 1. Path or string → load from file ───────────────────────────────────
    if isinstance(data, (str, Path)):
        path = Path(data)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        suffix = path.suffix.lower()

        # A1R.txt — tab-separated, columns T LX LY RX RY
        if suffix == ".txt":
            return _load_txt(path), path.name

        # CSV — must have LX, LY, RX, RY columns (T optional)
        elif suffix == ".csv":
            if not _PANDAS_OK:
                raise ImportError("pip install pandas  (required for CSV input)")
            df = pd.read_csv(path)
            return _dataframe_to_array(df), path.name

        else:
            # Try as tab-separated txt anyway
            try:
                return _load_txt(path), path.name
            except Exception:
                raise ValueError(
                    f"Unsupported file extension '{suffix}'. "
                    f"Expected .txt (A1R format) or .csv"
                )

    # ── 2. pandas DataFrame ───────────────────────────────────────────────────
    if _PANDAS_OK and isinstance(data, pd.DataFrame):
        return _dataframe_to_array(data), "DataFrame"

    # ── 3. numpy array ────────────────────────────────────────────────────────
    if isinstance(data, np.ndarray):
        return _numpy_to_array(data), "ndarray"

    raise TypeError(
        f"Unsupported input type: {type(data).__name__}. "
        f"Expected: str | Path | DataFrame | ndarray"
    )


def _load_txt(path: Path) -> np.ndarray:
    """Load Benfatto A1R.txt — tab-separated T LX LY RX RY."""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        content = content.replace(",", ".")   # handle European decimal comma
        from io import StringIO
        df = pd.read_csv(StringIO(content), sep="\t") if _PANDAS_OK else None

        if df is not None:
            # flexible column detection
            cols = [c.strip().upper() for c in df.columns]
            df.columns = cols
            for lx in ["LX", "L_X", "LEFT_X"]:
                if lx in cols: break
            arr = df[["LX", "LY", "RX", "RY"]].values.astype(float)
        else:
            # fallback: numpy loadtxt, assume col order T LX LY RX RY
            raw = np.loadtxt(StringIO(content), skiprows=1)
            if raw.shape[1] == 5:
                arr = raw[:, 1:5]
            elif raw.shape[1] == 4:
                arr = raw[:, :4]
            else:
                raise ValueError(f"Expected 4 or 5 columns, got {raw.shape[1]}")

    except Exception as e:
        raise ValueError(f"Failed to parse {path.name}: {e}") from e

    arr[np.abs(arr) > INVALID_THRESHOLD] = np.nan
    return arr.astype(np.float32)


def _dataframe_to_array(df: "pd.DataFrame") -> np.ndarray:
    """
    Convert DataFrame to (N, 4) array.
    Accepts column names: LX/LY/RX/RY or lx/ly/rx/ry or LEFT_X etc.
    """
    # normalise column names
    rename = {}
    for col in df.columns:
        cu = col.strip().upper().replace(" ", "_")
        for target, aliases in [
            ("LX", ["LX", "L_X", "LEFT_X", "GAZE_LEFT_X"]),
            ("LY", ["LY", "L_Y", "LEFT_Y", "GAZE_LEFT_Y"]),
            ("RX", ["RX", "R_X", "RIGHT_X", "GAZE_RIGHT_X"]),
            ("RY", ["RY", "R_Y", "RIGHT_Y", "GAZE_RIGHT_Y"]),
        ]:
            if cu in aliases:
                rename[col] = target
    df = df.rename(columns=rename)

    missing = [c for c in ["LX", "LY", "RX", "RY"] if c not in df.columns]
    if missing:
        raise ValueError(
            f"DataFrame missing required columns: {missing}\n"
            f"Available columns: {list(df.columns)}"
        )

    arr = df[["LX", "LY", "RX", "RY"]].values.astype(float)
    arr[np.abs(arr) > INVALID_THRESHOLD] = np.nan
    return arr.astype(np.float32)


def _numpy_to_array(arr: np.ndarray) -> np.ndarray:
    """
    Accept (N, 4) → [LX, LY, RX, RY]
    or     (N, 5) → [T,  LX, LY, RX, RY]  (T column stripped)
    """
    if arr.ndim != 2:
        raise ValueError(f"Expected 2D array, got shape {arr.shape}")

    if arr.shape[1] == 5:
        arr = arr[:, 1:5]    # strip T column
    elif arr.shape[1] == 4:
        arr = arr[:, :4]
    else:
        raise ValueError(
            f"Expected array with 4 columns [LX,LY,RX,RY] "
            f"or 5 columns [T,LX,LY,RX,RY], got shape {arr.shape}"
        )

    arr = arr.astype(float)
    arr[np.abs(arr) > INVALID_THRESHOLD] = np.nan
    return arr.astype(np.float32)


# ──────────────────────────────────────────────────────────────────────────────
# Preprocessing
# ──────────────────────────────────────────────────────────────────────────────

def _interpolate_blinks(data: np.ndarray, max_gap: int = MAX_BLINK_GAP) -> np.ndarray:
    """Linear interpolation across short NaN gaps (blinks)."""
    out = data.copy()
    for col in range(out.shape[1]):
        y    = out[:, col]
        nans = np.isnan(y)
        if not nans.any():
            continue
        changes = np.diff(nans.astype(int))
        starts  = np.where(changes == 1)[0] + 1
        ends    = np.where(changes == -1)[0] + 1
        if nans[0]:  starts = np.concatenate([[0], starts])
        if nans[-1]: ends   = np.concatenate([ends, [len(y)]])
        for s, e in zip(starts, ends):
            if (e - s) <= max_gap and s > 0 and e < len(y):
                y[s:e] = np.linspace(y[s-1], y[e], e - s + 2)[1:-1]
        out[:, col] = y
    return out


def _smooth_signal(data: np.ndarray, window: int = SMOOTH_WINDOW) -> np.ndarray:
    """Moving average smoothing on valid (non-NaN) samples."""
    out = data.copy()
    for col in range(out.shape[1]):
        valid = ~np.isnan(out[:, col])
        if valid.sum() > window:
            out[valid, col] = np.convolve(
                out[valid, col], np.ones(window) / window, mode="same"
            )
    return out


def _best_eye(data: np.ndarray) -> np.ndarray:
    """Return the eye channel with more valid (non-NaN) samples."""
    l_valid = (~np.isnan(data[:, 0])).sum()
    r_valid = (~np.isnan(data[:, 2])).sum()
    return data[:, :2] if l_valid >= r_valid else data[:, 2:]


# ──────────────────────────────────────────────────────────────────────────────
# Fixation / Saccade detection (I-VT algorithm)
# ──────────────────────────────────────────────────────────────────────────────

def _detect_fixations_saccades(gaze: np.ndarray) -> tuple[list, list]:
    dx  = np.diff(gaze[:, 0])
    dy  = np.diff(gaze[:, 1])
    vel = np.concatenate([[0], np.sqrt(dx**2 + dy**2) / DT])
    is_fix = (vel < VELOCITY_THRESHOLD) & (~np.isnan(gaze[:, 0]))

    fixations, saccades = [], []
    changes  = np.diff(is_fix.astype(int))
    starts_f = np.where(changes == 1)[0] + 1
    ends_f   = np.where(changes == -1)[0] + 1
    if is_fix[0]:  starts_f = np.concatenate([[0], starts_f])
    if is_fix[-1]: ends_f   = np.concatenate([ends_f, [len(is_fix)]])

    for s, e in zip(starts_f, ends_f):
        dur = (e - s) * DT
        if dur >= MIN_FIXATION_DUR:
            seg = gaze[s:e]
            if not np.isnan(seg[:, 0]).all():
                fixations.append({
                    "start":      s,
                    "end":        e,
                    "duration":   dur,
                    "cx":         float(np.nanmean(seg[:, 0])),
                    "cy":         float(np.nanmean(seg[:, 1])),
                    "dispersion": float(np.nanstd(seg[:, 0]) + np.nanstd(seg[:, 1])),
                })

    for i in range(1, len(fixations)):
        dx_ = fixations[i]["cx"] - fixations[i-1]["cx"]
        dy_ = fixations[i]["cy"] - fixations[i-1]["cy"]
        saccades.append({
            "amplitude": float(np.sqrt(dx_**2 + dy_**2)),
            "direction": float(dx_),
        })

    return fixations, saccades


# ──────────────────────────────────────────────────────────────────────────────
# Feature extraction (33 features — identical to training notebook)
# ──────────────────────────────────────────────────────────────────────────────

def _fixation_features(fixations: list) -> dict:
    if not _SCIPY_OK:
        raise ImportError("pip install scipy")
    if len(fixations) == 0:
        return {k: 0.0 for k in [
            "fix_count", "fix_dur_mean", "fix_dur_std", "fix_dur_median",
            "fix_dur_max", "fix_dur_skew", "fix_dur_kurt", "fix_disp_mean",
        ]}
    d = [f["duration"]   for f in fixations]
    p = [f["dispersion"] for f in fixations]
    return {
        "fix_count":      float(len(fixations)),
        "fix_dur_mean":   float(np.mean(d)),
        "fix_dur_std":    float(np.std(d)),
        "fix_dur_median": float(np.median(d)),
        "fix_dur_max":    float(np.max(d)),
        "fix_dur_skew":   float(skew(d)),
        "fix_dur_kurt":   float(kurtosis(d)),
        "fix_disp_mean":  float(np.mean(p)),
    }


def _saccade_features(saccades: list) -> dict:
    if not _SCIPY_OK:
        raise ImportError("pip install scipy")
    if len(saccades) == 0:
        return {k: 0.0 for k in [
            "sacc_count", "sacc_amp_mean", "sacc_amp_std", "sacc_amp_max",
            "sacc_amp_skew", "regression_count", "regression_rate",
            "progressive_amp_mean", "regressive_amp_mean",
        ]}
    amps  = [s["amplitude"] for s in saccades]
    regs  = [s for s in saccades if s["direction"] < 0]
    progs = [s for s in saccades if s["direction"] >= 0]
    return {
        "sacc_count":           float(len(saccades)),
        "sacc_amp_mean":        float(np.mean(amps)),
        "sacc_amp_std":         float(np.std(amps)),
        "sacc_amp_max":         float(np.max(amps)),
        "sacc_amp_skew":        float(skew(amps)),
        "regression_count":     float(len(regs)),
        "regression_rate":      float(len(regs) / len(saccades)),
        "progressive_amp_mean": float(np.mean([s["amplitude"] for s in progs])) if progs else 0.0,
        "regressive_amp_mean":  float(np.mean([s["amplitude"] for s in regs]))  if regs  else 0.0,
    }


def _stft_features(gaze: np.ndarray, n_bins: int = N_BINS) -> dict:
    x    = gaze[:, 0].copy()
    nans = np.isnan(x)
    if nans.all():
        return {k: 0.0 for k in [
            "stft_dom_freq_mean", "stft_dom_freq_std", "stft_entropy_mean",
            "stft_entropy_std", "stft_low_power_mean", "stft_low_power_std",
            "stft_entropy_range",
        ]}
    x[nans] = np.interp(np.where(nans)[0], np.where(~nans)[0], x[~nans])
    x -= np.mean(x)
    bin_size = len(x) // n_bins
    dom_freqs, entropies, low_powers = [], [], []
    for b in range(n_bins):
        seg = x[b * bin_size : (b + 1) * bin_size]
        if len(seg) < 4: continue
        freqs = np.fft.rfftfreq(len(seg), d=DT)
        pwr   = np.abs(np.fft.rfft(seg)) ** 2
        pn    = pwr / (pwr.sum() + 1e-10)
        dom_freqs.append(float(freqs[np.argmax(pwr)]))
        entropies.append(float(-np.sum(pn * np.log(pn + 1e-10))))
        low_powers.append(float(pwr[freqs <= 2.0].sum() / (pwr.sum() + 1e-10)))
    return {
        "stft_dom_freq_mean":  float(np.mean(dom_freqs)),
        "stft_dom_freq_std":   float(np.std(dom_freqs)),
        "stft_entropy_mean":   float(np.mean(entropies)),
        "stft_entropy_std":    float(np.std(entropies)),
        "stft_low_power_mean": float(np.mean(low_powers)),
        "stft_low_power_std":  float(np.std(low_powers)),
        "stft_entropy_range":  float(np.max(entropies) - np.min(entropies)),
    }


def _binocular_features(cleaned: np.ndarray) -> dict:
    lx, rx = cleaned[:, 0], cleaned[:, 2]
    valid  = ~(np.isnan(lx) | np.isnan(rx))
    if valid.sum() < 10:
        return {"binocular_disparity_x": 0.0,
                "binocular_disparity_y": 0.0,
                "binocular_correlation": 0.0}
    diff_x = lx[valid] - rx[valid]
    diff_y = cleaned[valid, 1] - cleaned[valid, 3]
    corr   = np.corrcoef(lx[valid], rx[valid])[0, 1]
    return {
        "binocular_disparity_x": float(np.std(diff_x)),
        "binocular_disparity_y": float(np.std(diff_y)),
        "binocular_correlation": float(corr) if not np.isnan(corr) else 0.0,
    }


def _reading_line_features(gaze: np.ndarray) -> dict:
    x       = gaze[:, 0]
    valid_x = x[~np.isnan(x)]
    if len(valid_x) < 4:
        return {"x_reversal_rate": 0.0, "reading_drift": 0.0, "fatigue_slope": 0.0}
    diffs        = np.diff(valid_x)
    sign_changes = np.sum(np.diff(np.sign(diffs)) != 0)
    thirds       = np.array_split(valid_x, 3)
    t_means      = [float(np.nanmean(t)) for t in thirds if len(t) > 0]
    t_vars       = [float(np.nanvar(np.diff(t))) for t in thirds if len(t) > 1]
    return {
        "x_reversal_rate": float(sign_changes / max(len(diffs), 1)),
        "reading_drift":   float(np.std(t_means)) if len(t_means) > 1 else 0.0,
        "fatigue_slope":   float(t_vars[-1] - t_vars[0]) if len(t_vars) >= 2 else 0.0,
    }


def _freq_band_features(gaze: np.ndarray) -> dict:
    x    = gaze[:, 0].copy()
    nans = np.isnan(x)
    if nans.all():
        return {"reading_rhythm_power": 0.0, "mid_freq_ratio": 0.0, "high_freq_ratio": 0.0}
    x[nans] = np.interp(np.where(nans)[0], np.where(~nans)[0], x[~nans])
    x -= np.mean(x)
    freqs = np.fft.rfftfreq(len(x), d=1.0 / SAMPLING_RATE)
    pwr   = np.abs(np.fft.rfft(x)) ** 2
    total = pwr.sum() + 1e-10
    return {
        "reading_rhythm_power": float(pwr[(freqs >= 0.5) & (freqs <= 2.0)].sum() / total),
        "mid_freq_ratio":       float(pwr[(freqs > 2.0) & (freqs <= 4.0)].sum() / total),
        "high_freq_ratio":      float(pwr[freqs > 4.0].sum() / total),
    }


def _extract_all_features(record: dict) -> dict:
    feats = {}
    feats.update(_fixation_features(record["fixations"]))
    feats.update(_saccade_features(record["saccades"]))
    feats.update(_stft_features(record["gaze"]))
    feats.update(_binocular_features(record["cleaned"]))
    feats.update(_reading_line_features(record["gaze"]))
    feats.update(_freq_band_features(record["gaze"]))
    return feats


# ──────────────────────────────────────────────────────────────────────────────
# Engine
# ──────────────────────────────────────────────────────────────────────────────

class DyslexiaEyeEngineV2:
    """
    Universal dyslexia eye-tracking inference engine.

    Accepts any of: A1R.txt path, CSV path, pandas DataFrame, numpy array.
    All inputs are normalised to (N,4) [LX, LY, RX, RY] before processing.

    Parameters
    ----------
    model_path : path to dyslexia_ensemble.joblib
    rfecv_path : path to dyslexia_rfecv.joblib
    meta_path  : path to dyslexia_feature_meta.json
    threshold  : dyslexia decision threshold (default 0.5)
    verbose    : print engine info on load (default True)
    """

    def __init__(
        self,
        model_path: str,
        rfecv_path: str,
        meta_path:  str,
        threshold:  float = 0.5,
        verbose:    bool  = True,
    ):
        if not _JOBLIB_OK:
            raise ImportError("pip install joblib")
        if not _SCIPY_OK:
            raise ImportError("pip install scipy")

        self.threshold = threshold

        self._ensemble = joblib.load(model_path)
        self._selector = joblib.load(rfecv_path)

        with open(meta_path, "r") as f:
            self._meta = json.load(f)

        self._feature_cols       = self._meta["feature_names"]       # all 33
        self._selected_feats     = self._meta["selected_features"]    # 18
        self._col_means          = np.array(self._meta["col_means"])
        self._feature_importance = self._meta.get("feature_importance", {})
        self._model_performance  = self._meta.get("model_performance", {})

        if verbose:
            print(
                f"[DyslexiaEyeEngineV2] Ready\n"
                f"  Ensemble   : {model_path}\n"
                f"  Selector   : {rfecv_path}  "
                f"({len(self._selected_feats)} / {len(self._feature_cols)} features)\n"
                f"  Test AUC   : {self._model_performance.get('test_auc', 'N/A')}\n"
                f"  Threshold  : {threshold}\n"
                f"  Accepts    : A1R.txt | CSV | DataFrame | ndarray"
            )

    # ── Public API ─────────────────────────────────────────────────────────────

    def predict(self, data: GazeInput) -> EyePrediction:
        """
        Predict dyslexia risk from any supported input format.

        Parameters
        ----------
        data : str | Path | DataFrame | ndarray
            Eye tracking data in any supported format.
            All formats must contain or map to columns [LX, LY, RX, RY]
            in degrees of visual angle at ~50Hz sampling rate.

        Returns
        -------
        EyePrediction dataclass with full results.
        """
        try:
            # 1. Normalise input → (N, 4) float32
            raw, source = _normalise_input(data)

            if len(raw) < 10:
                return self._error(source, "Too few samples (minimum 10 required)")

            # 2. Preprocess
            cleaned = _interpolate_blinks(raw)
            cleaned = _smooth_signal(cleaned)
            gaze    = _best_eye(cleaned)

            # 3. Detect fixations / saccades
            fixations, saccades = _detect_fixations_saccades(gaze)

            # 4. Extract all 33 features
            record = {
                "gaze":      gaze,
                "cleaned":   cleaned,
                "fixations": fixations,
                "saccades":  saccades,
            }
            all_feats = _extract_all_features(record)

            # 5. Build full feature vector — missing features → col mean
            x = np.array([
                all_feats.get(f, self._col_means[i])
                for i, f in enumerate(self._feature_cols)
            ], dtype=np.float32)
            x = np.nan_to_num(x, nan=self._col_means)

            # 6. RFECV feature selection (33 → 18)
            x_sel = self._selector.transform(x.reshape(1, -1))

            # 7. Ensemble prediction
            proba = self._ensemble.predict_proba(x_sel)[0]
            risk  = float(proba[1])
            label = "dyslexic" if risk >= self.threshold else "control"
            conf  = risk if label == "dyslexic" else 1.0 - risk

            # 8. Build selected feature dict
            selected = {
                f: round(float(all_feats.get(f, 0.0)), 6)
                for f in self._selected_feats
            }
            all_rounded = {
                f: round(float(v), 6) for f, v in all_feats.items()
            }

            # 9. Summary stats
            regressions = [s for s in saccades if s["direction"] < 0]
            n_valid     = int((~np.isnan(gaze[:, 0])).sum())
            duration    = round(len(raw) * DT, 2)

            return EyePrediction(
                source             = source,
                risk               = round(risk, 4),
                label              = label,
                confidence         = round(conf, 4),
                n_fixations        = len(fixations),
                n_saccades         = len(saccades),
                n_regressions      = len(regressions),
                regression_rate    = round(all_feats.get("regression_rate", 0.0), 4),
                mean_fix_duration  = round(all_feats.get("fix_dur_mean", 0.0), 4),
                stft_entropy       = round(all_feats.get("stft_entropy_mean", 0.0), 4),
                binocular_corr     = round(all_feats.get("binocular_correlation", 0.0), 4),
                selected_features  = selected,
                all_features       = all_rounded,
                n_samples          = n_valid,
                recording_duration = duration,
            )

        except Exception as e:
            import traceback
            source_label = str(data) if isinstance(data, (str, Path)) else type(data).__name__
            return self._error(source_label, f"{e}\n{traceback.format_exc()}")

    def predict_batch(
        self,
        inputs: list[GazeInput],
        verbose: bool = True,
    ) -> list[EyePrediction]:
        """
        Run predict() on a list of inputs.
        Each item can be a different format — mixing is allowed.

        Parameters
        ----------
        inputs  : list of any supported input formats
        verbose : print progress every 10 items

        Returns
        -------
        List of EyePrediction in the same order as inputs.
        """
        results = []
        for i, item in enumerate(inputs):
            results.append(self.predict(item))
            if verbose and (i + 1) % 10 == 0:
                print(f"  {i+1}/{len(inputs)} processed")
        return results

    def predict_csv_folder(
        self,
        folder: str,
        pattern: str = "*.csv",
        verbose: bool = True,
    ) -> list[EyePrediction]:
        """
        Run predict() on all CSV files in a folder.

        Parameters
        ----------
        folder  : path to folder containing CSV files
        pattern : glob pattern (default "*.csv")
        verbose : print progress

        Returns
        -------
        List of EyePrediction, one per file.
        """
        files = sorted(Path(folder).glob(pattern))
        if not files:
            print(f"No files matching '{pattern}' in {folder}")
            return []
        if verbose:
            print(f"Found {len(files)} files in {folder}")
        return self.predict_batch(files, verbose=verbose)

    def feature_names(self) -> list[str]:
        """All 33 feature names in extraction order."""
        return list(self._feature_cols)

    def selected_feature_names(self) -> list[str]:
        """The 18 RFECV-selected feature names."""
        return list(self._selected_feats)

    def feature_importance(self) -> dict[str, float]:
        """RF feature importance for all features."""
        return dict(self._feature_importance)

    def model_performance(self) -> dict[str, Any]:
        """Training performance metadata from dyslexia_feature_meta.json."""
        return dict(self._model_performance)

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _error(self, source: str, msg: str) -> EyePrediction:
        return EyePrediction(
            source=source, risk=-1.0, label="error",
            confidence=0.0, error=msg
        )

    # ── Internal hook for live webcam (not exposed yet) ────────────────────────
    def _predict_from_array(self, arr: np.ndarray) -> EyePrediction:
        """
        Direct (N,4) array path — bypasses normalisation overhead.
        Reserved for live webcam integration. Do not call directly.
        """
        return self.predict(arr)


# ──────────────────────────────────────────────────────────────────────────────
# Quick test — run this file directly to verify everything works
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    print("=" * 60)
    print("  DyslexiaEyeEngineV2 — format compatibility test")
    print("=" * 60)

    # Check dependencies
    missing = []
    if not _JOBLIB_OK:  missing.append("joblib")
    if not _SCIPY_OK:   missing.append("scipy")
    if not _PANDAS_OK:  missing.append("pandas")
    if missing:
        print(f"[MISSING] pip install {' '.join(missing)}")
        sys.exit(1)

    MODEL = "dyslexia_ensemble.joblib"
    RFECV = "dyslexia_rfecv.joblib"
    META  = "dyslexia_feature_meta.json"

    for f in [MODEL, RFECV, META]:
        if not Path(f).exists():
            print(f"[SKIP] Model file not found: {f}")
            print("       Place model files in the same directory to run full test.")
            sys.exit(0)

    engine = DyslexiaEyeEngineV2(MODEL, RFECV, META)

    print("\n── Generating synthetic gaze data (1000 samples @ 50Hz) ──")
    np.random.seed(42)
    N   = 1000
    t   = np.arange(N) * DT
    # Simulate reading-like horizontal sweep with saccades
    lx  = np.cumsum(np.random.randn(N) * 0.3) % 15
    ly  = np.random.randn(N) * 0.5
    rx  = lx + np.random.randn(N) * 0.2   # binocular with small disparity
    ry  = ly + np.random.randn(N) * 0.2

    # Add some blinks
    lx[100:105] = np.nan; rx[100:105] = np.nan
    lx[400:407] = np.nan; rx[400:407] = np.nan

    arr_4col = np.column_stack([lx, ly, rx, ry])
    arr_5col = np.column_stack([t,  lx, ly, rx, ry])

    # ── Test 1: numpy (N,4)
    print("\n[1] numpy array (N,4)")
    r = engine.predict(arr_4col)
    print(r)

    # ── Test 2: numpy (N,5) with T column
    print("\n[2] numpy array (N,5) with T column")
    r = engine.predict(arr_5col)
    print(f"    label={r.label}  risk={r.risk}  confidence={r.confidence}")

    # ── Test 3: DataFrame
    print("\n[3] pandas DataFrame")
    df = pd.DataFrame(arr_4col, columns=["LX", "LY", "RX", "RY"])
    r  = engine.predict(df)
    print(f"    label={r.label}  risk={r.risk}  confidence={r.confidence}")

    # ── Test 4: DataFrame with alternate column names
    print("\n[4] DataFrame with alternate column names (left_x etc.)")
    df2 = pd.DataFrame(arr_4col, columns=["left_x", "left_y", "right_x", "right_y"])
    r   = engine.predict(df2)
    print(f"    label={r.label}  risk={r.risk}  confidence={r.confidence}")

    # ── Test 5: CSV file
    print("\n[5] CSV file")
    import tempfile, os
    csv_path = os.path.join(tempfile.gettempdir(), "test_gaze.csv")
    df.to_csv(csv_path, index=False)
    r = engine.predict(csv_path)
    print(f"    label={r.label}  risk={r.risk}  confidence={r.confidence}")

    # ── Show selected features
    print("\n── Selected features (18) ──")
    for feat, val in r.selected_features.items():
        imp = engine.feature_importance().get(feat, 0.0)
        bar = "█" * int(imp * 200)
        print(f"  {feat:<30} {val:>10.4f}   {bar}")

    print("\n✓ All format tests passed")
"""
neuroscan_bridge.py
───────────────────
Bridge between all desktop tools and the NeuroScan FastAPI backend.
Place this file next to your engine files (dysarthria_ui.py, dyslexia_live_ui.py).

─────────────────────────────────────────────────────────────────────────────
DYSARTHRIA  (dysarthria_ui.py)
─────────────────────────────────────────────────────────────────────────────
In dysarthria_ui.py, find _show_result(self, pred) and add at the end:

    from neuroscan_bridge import post_dysarthria
    post_dysarthria(pred)

pred is the Prediction dataclass from dysarthria_engine.py.

─────────────────────────────────────────────────────────────────────────────
DYSLEXIA  (dyslexia_live_ui.py)
─────────────────────────────────────────────────────────────────────────────
After cap.record() returns the (N,4) array, add:

    from neuroscan_bridge import post_gaze_array
    post_gaze_array(arr)

─────────────────────────────────────────────────────────────────────────────
"""
import io, logging, requests
import numpy as np
from typing import Optional

log = logging.getLogger(__name__)

API_BASE = "http://localhost:8000"
TIMEOUT  = 30


# ── Dysarthria ────────────────────────────────────────────────────────────────

def post_dysarthria(pred) -> Optional[dict]:
    """
    Post a DysarthriaEngine Prediction to the dashboard.

    Parameters
    ----------
    pred : Prediction  (from dysarthria_engine.py)
        Must have .risk, .label, .confidence, .n_chunks, .chunk_risks, .wav_path

    Returns
    -------
    dict with the saved result, or None on failure.
    """
    if getattr(pred, "error", None):
        log.warning("Not posting errored prediction: %s", pred.error)
        return None

    payload = {
        "risk":        pred.risk,
        "label":       pred.label,
        "confidence":  pred.confidence,
        "n_chunks":    pred.n_chunks,
        "chunk_risks": list(pred.chunk_risks),
        "wav_path":    str(getattr(pred, "wav_path", "")),
    }
    try:
        resp = requests.post(
            f"{API_BASE}/dysarthria/predict_result",
            json    = payload,
            timeout = TIMEOUT,
        )
        resp.raise_for_status()
        print(f"[Bridge] Dysarthria result posted → risk={pred.risk:.3f}  label={pred.label}")
        return resp.json()
    except requests.exceptions.ConnectionError:
        log.warning("[Bridge] API unreachable at %s — is the backend running?", API_BASE)
    except requests.exceptions.HTTPError as e:
        log.error("[Bridge] API error %s: %s", e.response.status_code, e.response.text)
    except Exception as e:
        log.error("[Bridge] Unexpected error: %s", e)
    return None


# ── Dyslexia (gaze array) ─────────────────────────────────────────────────────

def post_gaze_array(arr: np.ndarray) -> Optional[dict]:
    """
    Post a (N,4) gaze array to /dyslexia/predict_array.

    Parameters
    ----------
    arr : np.ndarray  shape (N,4)  columns [LX, LY, RX, RY] in degrees at 50 Hz

    Returns
    -------
    dict with keys: risk, label, confidence, n_fixations, n_regressions,
                    regression_rate, recording_duration
    None on failure.
    """
    buf = io.BytesIO()
    np.save(buf, arr)
    buf.seek(0)
    try:
        resp = requests.post(
            f"{API_BASE}/dyslexia/predict_array",
            files   = {"file": ("gaze.npy", buf, "application/octet-stream")},
            timeout = TIMEOUT,
        )
        resp.raise_for_status()
        result = resp.json()
        print(f"[Bridge] Dyslexia result posted → risk={result['risk']:.3f}  label={result['label']}")
        return result
    except requests.exceptions.ConnectionError:
        log.warning("[Bridge] API unreachable at %s", API_BASE)
    except requests.exceptions.HTTPError as e:
        log.error("[Bridge] API error %s: %s", e.response.status_code, e.response.text)
    except Exception as e:
        log.error("[Bridge] Unexpected error: %s", e)
    return None


def post_features(features: dict) -> Optional[dict]:
    """Post pre-computed dyslexia feature dict."""
    try:
        resp = requests.post(
            f"{API_BASE}/dyslexia/predict_features",
            json    = features,
            timeout = TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.error("[Bridge] post_features error: %s", e)
    return None


# ── Smoke test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 55)
    print("  NeuroScan Bridge — smoke test")
    print("=" * 55)

    # Test dysarthria bridge with a dummy prediction
    class _FakePred:
        risk=0.35; label="non_dysarthria"; confidence=0.65
        n_chunks=2; chunk_risks=[0.3, 0.4]; wav_path="test.wav"; error=None

    print("\n[1] Dysarthria bridge:")
    r = post_dysarthria(_FakePred())
    print("   ", r if r else "FAILED (is backend running?)")

    # Test dyslexia bridge with synthetic array
    print("\n[2] Dyslexia gaze array bridge:")
    np.random.seed(42)
    arr = np.column_stack([np.cumsum(np.random.randn(1500) * 0.3) % 15,
                           np.random.randn(1500) * 0.5] * 2).astype(np.float32)
    r = post_gaze_array(arr[:, :4])
    print("   ", r if r else "FAILED (is backend running?)")

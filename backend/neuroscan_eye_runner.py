"""
neuroscan_eye_runner.py
=======================
Eye-tracking capture + inference runner.
Launched automatically by the NeuroScan web backend when user clicks
"Start Eye Tracking" on the eye-tracking test page.

  python neuroscan_eye_runner.py \
      --model_face face_landmarker.task \
      --ensemble  models/dyslexia_ensemble.joblib \
      --rfecv     models/dyslexia_rfecv.joblib \
      --meta      models/dyslexia_feature_meta.json \
      --api       http://localhost:8000 \
      --duration  30

Pipeline:
  1. Start LiveGazeCapture (webcam + MediaPipe)
  2. Run GazeCalibration (range detection, ~10s)
  3. Show reading passage in a fullscreen OpenCV window
  4. Record gaze for --duration seconds
  5. Run DyslexiaEyeEngineV2.predict(arr)
  6. POST result to {api}/dyslexia/predict_array
  7. Exit

Requires:
  pip install mediapipe opencv-python scipy pandas joblib xgboost scikit-learn
  face_landmarker.task  (download — see README)
  dysarthria_engine.py, dyslexia_live_engine.py, dyslexia_eye_engine_v2.py
  in the same folder (or on PYTHONPATH)
"""

import argparse
import io
import sys
import time
import threading
from pathlib import Path

import cv2
import numpy as np
import requests


READING_PASSAGE = (
    "Reading is the process of taking in the sense or meaning "
    "of letters, symbols, and other forms of written language. "
    "For educators and researchers, reading involves word recognition, "
    "phonics, vocabulary, fluency, comprehension, and motivation. "
    "Please read this passage naturally at your own comfortable pace."
)


def _add_to_path():
    here = Path(__file__).parent
    for d in [here, here.parent, here / "app" / "services"]:
        p = str(d)
        if p not in sys.path:
            sys.path.insert(0, p)


def show_status_window(message: str, title: str = "NeuroScan Eye Tracking",
                       color: tuple = (30, 40, 60)):
    """Show a brief fullscreen status message via OpenCV."""
    w, h = 1280, 720
    canvas = np.zeros((h, w, 3), dtype=np.uint8)
    canvas[:] = color

    # Word-wrap text
    words = message.split()
    lines, current = [], ""
    for word in words:
        test = (current + " " + word).strip()
        if cv2.getTextSize(test, cv2.FONT_HERSHEY_SIMPLEX, 0.75, 2)[0][0] > w - 120:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)

    y = h // 2 - (len(lines) * 40) // 2
    for line in lines:
        tw = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, 0.75, 2)[0][0]
        cv2.putText(canvas, line, ((w - tw) // 2, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, (220, 225, 235), 2, cv2.LINE_AA)
        y += 42

    cv2.imshow(title, canvas)
    cv2.waitKey(1)


def run_reading_session(capture, duration_sec: float = 30.0) -> np.ndarray:
    """
    Show a fullscreen reading passage while recording gaze.
    Returns the (N,4) gaze array.
    """
    WIN   = "NeuroScan — Eye Tracking  |  Read the passage  |  ESC to stop early"
    W, H  = 1280, 720
    BG    = (12, 16, 22)
    TXT   = (210, 218, 232)
    DIM   = (80, 90, 110)

    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(WIN, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    capture.clear_buffer()
    start = time.time()

    # Word-wrap passage
    words   = READING_PASSAGE.split()
    lines, cur = [], ""
    font, fscale, fthick = cv2.FONT_HERSHEY_SIMPLEX, 0.62, 1
    for word in words:
        test = (cur + " " + word).strip()
        if cv2.getTextSize(test, font, fscale, fthick)[0][0] > W - 160:
            lines.append(cur)
            cur = word
        else:
            cur = test
    if cur:
        lines.append(cur)

    line_h  = 40
    total_h = len(lines) * line_h
    y_start = (H - total_h) // 2

    while True:
        elapsed = time.time() - start
        pct     = min(elapsed / duration_sec, 1.0)
        canvas  = np.zeros((H, W, 3), dtype=np.uint8)
        canvas[:] = BG

        # Header
        cv2.putText(canvas, "Read naturally — your gaze is being recorded",
                    (W//2 - 280, 36), font, 0.5, DIM, 1, cv2.LINE_AA)

        # Passage
        for i, line in enumerate(lines):
            y = y_start + i * line_h
            cv2.putText(canvas, line, (80, y), font, fscale, TXT, fthick, cv2.LINE_AA)

        # Progress bar
        bx0, bx1 = int(W * 0.15), int(W * 0.85)
        by = H - 50
        cv2.rectangle(canvas, (bx0, by), (bx1, by + 8), (30, 40, 55), -1)
        bf = int(bx0 + (bx1 - bx0) * pct)
        if bf > bx0:
            cv2.rectangle(canvas, (bx0, by), (bf, by + 8), (80, 160, 255), -1)

        # Timer
        rem = max(0, int(duration_sec - elapsed))
        cv2.putText(canvas, f"{rem}s remaining",
                    (W - 160, H - 30), font, 0.5, DIM, 1, cv2.LINE_AA)

        # Live gaze dot (latest sample)
        sample = capture.get_latest_sample()
        if sample and not sample.l_blink:
            # Map degrees back to rough screen coords for visual feedback
            gx = int(W * 0.5 + sample.lx_deg * W / 30)
            gy = int(H * 0.5 + sample.ly_deg * H / 20)
            gx = max(10, min(W - 10, gx))
            gy = max(10, min(H - 10, gy))
            cv2.circle(canvas, (gx, gy), 8, (80, 180, 255), -1)
            cv2.circle(canvas, (gx, gy), 12, (80, 180, 255), 1)

        cv2.imshow(WIN, canvas)
        key = cv2.waitKey(20) & 0xFF
        if key == 27 or elapsed >= duration_sec:   # ESC or time up
            break

    cv2.destroyWindow(WIN)
    arr = capture.get_buffer_as_array()
    return arr


def main():
    _add_to_path()

    ap = argparse.ArgumentParser(description="NeuroScan eye-tracking runner")
    ap.add_argument("--model_face", default="face_landmarker.task")
    ap.add_argument("--ensemble",   default="models/dyslexia_ensemble.joblib")
    ap.add_argument("--rfecv",      default="models/dyslexia_rfecv.joblib")
    ap.add_argument("--meta",       default="models/dyslexia_feature_meta.json")
    ap.add_argument("--api",        default="http://localhost:8000")
    ap.add_argument("--duration",   type=float, default=30.0)
    ap.add_argument("--camera",     type=int,   default=0)
    ap.add_argument("--width",      type=int,   default=1920)
    ap.add_argument("--height",     type=int,   default=1080)
    args = ap.parse_args()

    # ── Validate files ─────────────────────────────────────────────────────────
    for label, path in [
        ("face_landmarker.task", args.model_face),
        ("ensemble model",       args.ensemble),
        ("RFECV selector",       args.rfecv),
        ("feature meta",         args.meta),
    ]:
        if not Path(path).exists():
            print(f"[ERROR] {label} not found: {path}")
            sys.exit(1)

    # ── Imports ────────────────────────────────────────────────────────────────
    try:
        from dyslexia_live_engine import LiveGazeCapture, GazeCalibration, ScreenConfig
    except ImportError as e:
        print(f"[ERROR] {e}\n  pip install mediapipe opencv-python")
        sys.exit(1)

    try:
        from dyslexia_eye_engine_v2 import DyslexiaEyeEngineV2
    except ImportError as e:
        print(f"[ERROR] {e}\n  pip install joblib scipy pandas xgboost scikit-learn")
        sys.exit(1)

    # ── Step 1: Init capture ───────────────────────────────────────────────────
    screen = ScreenConfig(
        width_px  = args.width,
        height_px = args.height,
    )
    print("[Runner] Starting webcam capture…")
    try:
        cap = LiveGazeCapture(
            model_path   = args.model_face,
            camera_index = args.camera,
            screen       = screen,
        )
    except Exception as e:
        print(f"[ERROR] Could not start webcam: {e}")
        sys.exit(1)

    # ── Step 2: Calibration ────────────────────────────────────────────────────
    show_status_window(
        "Calibration starting…  "
        "Look at each direction shown on screen.  ESC to skip.",
        color=(10, 15, 25)
    )
    cv2.waitKey(1500)

    cal = GazeCalibration(cap)
    try:
        calibration = cal.run()
        cap.calibration = calibration
        print("[Runner] Calibration complete.")
    except Exception as e:
        print(f"[Runner] Calibration failed: {e} — using geometric fallback.")

    # ── Step 3: Reading session ────────────────────────────────────────────────
    show_status_window(
        "Calibration complete!  "
        "A reading passage will now appear.  Read naturally for "
        f"{int(args.duration)} seconds.",
        color=(10, 20, 15)
    )
    cv2.waitKey(2500)

    cap.start()
    print(f"[Runner] Recording gaze for {args.duration}s…")
    arr = run_reading_session(cap, duration_sec=args.duration)
    cap.stop()

    if len(arr) < 50:
        show_status_window(
            "Not enough gaze data captured.  "
            "Ensure your face is well-lit and clearly visible.",
            color=(30, 10, 10)
        )
        cv2.waitKey(3000)
        cv2.destroyAllWindows()
        sys.exit(1)

    # ── Step 4: Inference ──────────────────────────────────────────────────────
    show_status_window("Analysing gaze patterns…", color=(10, 15, 30))
    cv2.waitKey(500)

    try:
        engine = DyslexiaEyeEngineV2(
            model_path = args.ensemble,
            rfecv_path = args.rfecv,
            meta_path  = args.meta,
        )
        pred = engine.predict(arr)
    except Exception as e:
        show_status_window(f"Analysis failed: {e}", color=(30, 10, 10))
        cv2.waitKey(3000)
        cv2.destroyAllWindows()
        sys.exit(1)

    print(f"[Runner] Result: risk={pred.risk:.3f}  label={pred.label}")

    # ── Step 5: Post to API ────────────────────────────────────────────────────
    try:
        buf = io.BytesIO()
        np.save(buf, arr)
        buf.seek(0)
        resp = requests.post(
            f"{args.api}/dyslexia/predict_array",
            files   = {"file": ("gaze.npy", buf, "application/octet-stream")},
            timeout = 20,
        )
        resp.raise_for_status()
        show_status_window(
            f"Done!  Risk: {pred.risk:.1%}  —  {pred.label.replace('_',' ').title()}  "
            "Result sent to dashboard.",
            color=(10, 25, 15)
        )
    except Exception as e:
        show_status_window(
            f"Analysis complete but could not post to API: {e}",
            color=(30, 25, 10)
        )

    cv2.waitKey(3000)
    cv2.destroyAllWindows()
    print("[Runner] Done.")


if __name__ == "__main__":
    main()

"""
neuroscan_eye_runner.py
=======================
Eye-tracking capture + inference runner.
Launched automatically by the NeuroScan web backend.

  python neuroscan_eye_runner.py --duration 30 --api http://localhost:8000

Changes:
  - Paragraph repository (random selection each run)
  - Flexible duration via --duration
  - Live gaze overlay dot during reading
  - Cleaner calibration status display
"""

import argparse
import io
import random
import sys
import time
import math
from pathlib import Path

import cv2
import numpy as np
import requests


# ── Paragraph repository ──────────────────────────────────────────────────────
PARAGRAPHS = [
    # 0 — Reading comprehension
    (
        "Reading is the process of taking in the sense or meaning of letters "
        "and symbols. For educators and researchers, reading involves word "
        "recognition, phonics, vocabulary, fluency, and comprehension. "
        "Please read this passage naturally at your own comfortable pace."
    ),
    # 1 — Nature description
    (
        "The sun sets slowly behind the distant hills, painting the sky in "
        "shades of deep red and orange. Birds return to their nests as the "
        "evening breeze picks up, carrying the scent of pine and damp earth. "
        "A quiet river winds through the valley below, reflecting the last light."
    ),
    # 2 — Science passage
    (
        "The human brain contains approximately eighty-six billion neurons, "
        "each connected to thousands of others through synaptic junctions. "
        "Electrical signals travel along these pathways at speeds of up to "
        "two hundred and seventy miles per hour, enabling thought and action."
    ),
    # 3 — Story extract
    (
        "She opened the old wooden door and stepped inside. The room smelled "
        "of dust and forgotten things. On the table lay a leather-bound book, "
        "its pages yellowed with age. She reached out and turned to the first "
        "page, wondering what secrets had been kept hidden all these years."
    ),
    # 4 — Technical description
    (
        "Machine learning models are trained on large datasets by adjusting "
        "internal parameters to minimise prediction errors. Deep neural networks "
        "use multiple layers of computation to extract increasingly abstract "
        "features from raw input data, enabling tasks such as image recognition."
    ),
    # 5 — Geography
    (
        "The Amazon rainforest covers more than five million square kilometres "
        "across nine countries in South America. It is home to an estimated "
        "three million species of plants and animals. The forest plays a critical "
        "role in regulating the global climate by absorbing vast amounts of carbon."
    ),
    # 6 — Medical passage
    (
        "The optic nerve transmits visual information from the retina to the "
        "brain's visual cortex. Each eye has approximately one million nerve "
        "fibres. When light enters the eye, photoreceptors called rods and cones "
        "convert it into electrical signals that travel along this pathway."
    ),
    # 7 — Simple everyday text
    (
        "Every morning I walk to the park near my house. The path is lined with "
        "tall oak trees that provide shade in summer. Children play on the grass "
        "while their parents sit on benches reading newspapers or talking quietly "
        "to one another. It is a peaceful way to start the day."
    ),
]


def _add_to_path():
    here = Path(__file__).parent
    for d in [here, here.parent, here / "app" / "services"]:
        p = str(d)
        if p not in sys.path:
            sys.path.insert(0, p)


def _word_wrap(text: str, font, scale: float, thickness: int, max_width: int):
    """Wrap text into lines that fit within max_width pixels."""
    words = text.split()
    lines, cur = [], ""
    for word in words:
        test = (cur + " " + word).strip()
        w    = cv2.getTextSize(test, font, scale, thickness)[0][0]
        if w > max_width and cur:
            lines.append(cur)
            cur = word
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines


def show_message(title: str, message: str, hold_ms: int = 2000,
                 bg: tuple = (12, 16, 22), fg: tuple = (210, 218, 232)):
    """Show a brief fullscreen message and wait."""
    W, H   = 1280, 720
    WIN    = "NeuroScan Eye Tracking"
    canvas = np.zeros((H, W, 3), dtype=np.uint8)
    canvas[:] = bg

    font   = cv2.FONT_HERSHEY_SIMPLEX
    lines  = _word_wrap(message, font, 0.75, 2, W - 120)
    total  = len(lines) * 42
    y      = (H - total) // 2
    for line in lines:
        tw = cv2.getTextSize(line, font, 0.75, 2)[0][0]
        cv2.putText(canvas, line, ((W - tw) // 2, y), font, 0.75, fg, 2, cv2.LINE_AA)
        y += 42

    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(WIN, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cv2.imshow(WIN, canvas)
    cv2.waitKey(hold_ms)


def run_reading_session(capture, paragraph: str, duration_sec: float) -> np.ndarray:
    """
    Show fullscreen reading passage while recording gaze.
    Draws a live gaze-position circle overlay.
    Returns (N,4) array.
    """
    WIN  = "NeuroScan — Eye Tracking  |  Read the passage  |  ESC to stop early"
    W, H = 1280, 720
    BG   = (12, 16, 22)
    TXT  = (210, 218, 232)
    DIM  = (80, 90, 110)
    GAZE_COLOR = (80, 200, 255)

    font, fscale, fthick = cv2.FONT_HERSHEY_SIMPLEX, 0.62, 1

    cv2.namedWindow(WIN, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(WIN, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    lines   = _word_wrap(paragraph, font, fscale, fthick, W - 160)
    line_h  = 40
    total_h = len(lines) * line_h
    y_start = (H - total_h) // 2

    capture.clear_buffer()
    start = time.time()

    # Smooth gaze with simple EMA
    gaze_smooth = [W / 2, H / 2]
    ALPHA = 0.15   # smoothing factor — lower = smoother but laggier

    while True:
        elapsed = time.time() - start
        pct     = min(elapsed / duration_sec, 1.0)
        canvas  = np.zeros((H, W, 3), dtype=np.uint8)
        canvas[:] = BG

        # Header
        cv2.putText(canvas, "Read naturally — your gaze is being recorded",
                    (W // 2 - 260, 34), font, 0.48, DIM, 1, cv2.LINE_AA)

        # Passage
        for i, line in enumerate(lines):
            cv2.putText(canvas, line, (80, y_start + i * line_h),
                        font, fscale, TXT, fthick, cv2.LINE_AA)

        # Progress bar
        bx0, bx1, by = int(W * 0.15), int(W * 0.85), H - 50
        cv2.rectangle(canvas, (bx0, by), (bx1, by + 8), (30, 40, 55), -1)
        bf = int(bx0 + (bx1 - bx0) * pct)
        if bf > bx0:
            cv2.rectangle(canvas, (bx0, by), (bf, by + 8), (80, 160, 255), -1)

        # Timer
        rem = max(0, int(duration_sec - elapsed))
        cv2.putText(canvas, f"{rem}s remaining",
                    (W - 155, H - 30), font, 0.45, DIM, 1, cv2.LINE_AA)

        # ── Live gaze overlay ─────────────────────────────────────────────────
        sample = capture.get_latest_sample()
        if sample and not sample.l_blink and not sample.r_blink:
            # Average L and R eye degrees
            avg_deg_x = (sample.lx_deg + sample.rx_deg) / 2.0
            avg_deg_y = (sample.ly_deg + sample.ry_deg) / 2.0

            # Convert degrees to rough pixel position
            # Assumes ±15° H → full screen width, ±10° V → full screen height
            raw_x = W * 0.5 + avg_deg_x * (W / 30.0)
            raw_y = H * 0.5 + avg_deg_y * (H / 20.0)

            # EMA smoothing
            gaze_smooth[0] += ALPHA * (raw_x - gaze_smooth[0])
            gaze_smooth[1] += ALPHA * (raw_y - gaze_smooth[1])

            gx = int(max(20, min(W - 20, gaze_smooth[0])))
            gy = int(max(20, min(H - 20, gaze_smooth[1])))

            # Outer ring (semi-transparent effect via layered circles)
            cv2.circle(canvas, (gx, gy), 22, GAZE_COLOR, 1)
            cv2.circle(canvas, (gx, gy), 14, GAZE_COLOR, 1)
            cv2.circle(canvas, (gx, gy),  5, GAZE_COLOR, -1)

            # Small label
            cv2.putText(canvas, "gaze", (gx + 16, gy - 8),
                        font, 0.35, GAZE_COLOR, 1, cv2.LINE_AA)

        cv2.imshow(WIN, canvas)
        key = cv2.waitKey(20) & 0xFF
        if key == 27 or elapsed >= duration_sec:
            break

    cv2.destroyWindow(WIN)
    return capture.get_buffer_as_array()


def main():
    _add_to_path()

    ap = argparse.ArgumentParser()
    ap.add_argument("--model_face", default="face_landmarker.task")
    ap.add_argument("--ensemble",   default="models/dyslexia_ensemble.joblib")
    ap.add_argument("--rfecv",      default="models/dyslexia_rfecv.joblib")
    ap.add_argument("--meta",       default="models/dyslexia_feature_meta.json")
    ap.add_argument("--api",        default="http://localhost:8000")
    ap.add_argument("--duration",   type=float, default=30.0)
    ap.add_argument("--camera",     type=int,   default=0)
    ap.add_argument("--width",      type=int,   default=1920)
    ap.add_argument("--height",     type=int,   default=1080)
    ap.add_argument("--paragraph",  type=int,   default=-1,
                    help="Paragraph index (0-based). -1 = random")
    args = ap.parse_args()

    # ── Validate ───────────────────────────────────────────────────────────────
    for label, path in [
        ("face_landmarker.task", args.model_face),
        ("ensemble",             args.ensemble),
        ("rfecv",                args.rfecv),
        ("meta json",            args.meta),
    ]:
        if not Path(path).exists():
            print(f"[ERROR] {label} not found: {path}")
            sys.exit(1)

    # ── Imports ────────────────────────────────────────────────────────────────
    try:
        from dyslexia_live_engine import LiveGazeCapture, GazeCalibration, ScreenConfig
    except ImportError as e:
        print(f"[ERROR] {e}\n  pip install mediapipe opencv-python"); sys.exit(1)

    try:
        from dyslexia_eye_engine_v2 import DyslexiaEyeEngineV2
    except ImportError as e:
        print(f"[ERROR] {e}\n  pip install joblib scipy pandas xgboost scikit-learn"); sys.exit(1)

    # ── Pick paragraph ─────────────────────────────────────────────────────────
    if 0 <= args.paragraph < len(PARAGRAPHS):
        paragraph = PARAGRAPHS[args.paragraph]
        para_idx  = args.paragraph
    else:
        para_idx  = random.randint(0, len(PARAGRAPHS) - 1)
        paragraph = PARAGRAPHS[para_idx]
    print(f"[Runner] Paragraph #{para_idx} selected ({len(paragraph)} chars)")

    # ── Init capture ───────────────────────────────────────────────────────────
    screen = ScreenConfig(width_px=args.width, height_px=args.height)
    print("[Runner] Starting webcam…")
    try:
        cap = LiveGazeCapture(
            model_path   = args.model_face,
            camera_index = args.camera,
            screen       = screen,
        )
    except Exception as e:
        print(f"[ERROR] Webcam: {e}"); sys.exit(1)

    # ── Calibration ────────────────────────────────────────────────────────────
    show_message("NeuroScan Eye Tracking",
        "Calibration starting. Follow the prompts on screen. "
        "Move your eyes to each extreme position shown.", hold_ms=2000)

    cal = GazeCalibration(cap)
    try:
        calibration   = cal.run()
        cap.calibration = calibration
        print("[Runner] Calibration complete.")
    except Exception as e:
        print(f"[Runner] Calibration warning: {e} — geometric fallback.")

    show_message("NeuroScan Eye Tracking",
        f"Calibration complete!  A reading passage will appear. "
        f"Read naturally for {int(args.duration)} seconds. "
        f"A small circle shows where your gaze is detected.",
        hold_ms=3000, bg=(10, 20, 15))

    # ── Reading session ────────────────────────────────────────────────────────
    cap.start()
    print(f"[Runner] Recording {args.duration}s reading session…")
    arr = run_reading_session(cap, paragraph, args.duration)
    cap.stop()

    if len(arr) < 50:
        show_message("Error",
            "Not enough gaze data. Ensure face is visible and well-lit.",
            hold_ms=3000, bg=(30, 10, 10))
        cv2.destroyAllWindows(); sys.exit(1)

    # ── Inference ──────────────────────────────────────────────────────────────
    show_message("NeuroScan Eye Tracking", "Analysing gaze patterns…",
                 hold_ms=500, bg=(10, 15, 30))

    try:
        engine = DyslexiaEyeEngineV2(args.ensemble, args.rfecv, args.meta)
        pred   = engine.predict(arr)
    except Exception as e:
        show_message("Error", f"Analysis failed: {e}", hold_ms=3000, bg=(30, 10, 10))
        cv2.destroyAllWindows(); sys.exit(1)

    print(f"[Runner] risk={pred.risk:.3f}  label={pred.label}")

    # ── Post to API ────────────────────────────────────────────────────────────
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
        show_message("Done",
            f"Risk: {pred.risk:.0%}  —  {pred.label.replace('_',' ').title()}  "
            f"(Paragraph #{para_idx})  Result sent to dashboard.",
            hold_ms=3000, bg=(10, 25, 15))
    except Exception as e:
        show_message("Warning",
            f"Analysis complete but could not post to API: {e}",
            hold_ms=3000, bg=(30, 25, 10))

    cv2.waitKey(500)
    cv2.destroyAllWindows()
    print("[Runner] Done.")


if __name__ == "__main__":
    main()

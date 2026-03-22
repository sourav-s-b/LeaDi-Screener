"""
model.py  —  YOLO model loading, image preprocessing, and scoring logic.

Key change from original:
  run_scoring_pipeline() now uses per-letter segmentation instead of running
  YOLO on the whole canvas at once.  Each letter is:
    1. Detected via contour analysis
    2. Cropped with padding
    3. Padded to a square  (preserves aspect ratio)
    4. Resized to imgsz × imgsz  (matches your training imgsz=768)
    5. Classified individually by YOLO
  This eliminates the "thick stroke looks nothing like training data" mismatch.
"""

import time
from pathlib import Path
from collections import Counter

import numpy as np
import cv2
from PIL import Image
from ultralytics import YOLO


# ----------------------------
# Config defaults
# ----------------------------
DEFAULT_CLASS_NAMES = ["Normal", "Reversal", "Corrected"]
CLASS_NORMAL    = 0
CLASS_REVERSAL  = 1
CLASS_CORRECTED = 2

DEFAULT_CONF    = 0.10
DEFAULT_IMGSZ   = 768               # matches your training imgsz=768
DEFAULT_MIN_SIDE_UPSCALE_TO = 900

DEFAULT_PAD           = 80
DEFAULT_MIN_AREA_FRAC = 0.02

DEFAULT_NORMALIZE_POLARITY = True

# ── Segmentation tuning ───────────────────────────────────────────────────────
SEG_PAD_FACTOR   = 0.15     # padding around each letter as fraction of its size
SEG_MIN_AREA     = 10       # px² — blobs smaller than this are noise
SEG_MAX_AREA_PCT = 0.40     # blobs larger than 40% of canvas = background accident


# ----------------------------
# Polarity normalization
# ----------------------------
def normalize_polarity_if_needed(bgr: np.ndarray, enabled: bool = True):
    """
    If enabled and the background is bright (mean gray > 127), invert the image
    so strokes become white on a black background (matches typical training data).
    Returns: (bgr_out, inverted_bool)
    """
    if not enabled:
        return bgr, False
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # Use median (more robust than mean for gray/uneven backgrounds).
    # Also check if there are clearly dark pixels on a lighter background —
    # this catches gray-background photos where mean < 127 but ink is darker.
    med = float(np.median(gray))
    dark_frac = float(np.mean(gray < (med - 20)))
    if med > 100 or dark_frac < 0.15:
        inv = 255 - gray
        return cv2.cvtColor(inv, cv2.COLOR_GRAY2BGR), True
    return bgr, False


# ----------------------------
# Whole-canvas crop helper (kept for --no_crop fallback path)
# ----------------------------
def crop_to_ink_region(
    bgr: np.ndarray,
    pad: int = DEFAULT_PAD,
    min_area_frac: float = DEFAULT_MIN_AREA_FRAC,
):
    H, W  = bgr.shape[:2]
    full  = (0, 0, W, H)
    gray  = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray  = clahe.apply(gray)
    thr   = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 7
    )
    k   = np.ones((3, 3), np.uint8)
    thr = cv2.morphologyEx(thr, cv2.MORPH_CLOSE, k, iterations=2)
    thr = cv2.morphologyEx(thr, cv2.MORPH_OPEN,  k, iterations=1)
    contours, _ = cv2.findContours(thr, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return bgr, full, False
    c    = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(c)
    if area < (min_area_frac * H * W):
        return bgr, full, False
    x, y, w, h = cv2.boundingRect(c)
    x0 = max(0, x - pad);    y0 = max(0, y - pad)
    x1 = min(W, x + w + pad); y1 = min(H, y + h + pad)
    return bgr[y0:y1, x0:x1], (x0, y0, x1, y1), True


def resize_to_target_range(bgr: np.ndarray, min_side: int = 700, max_side: int = 1100):
    h, w = bgr.shape[:2]
    m    = min(h, w)
    if   m < min_side: scale = float(min_side) / m
    elif m > max_side: scale = float(max_side) / m
    else: return bgr, 1.0
    nw, nh = int(round(w * scale)), int(round(h * scale))
    return cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_CUBIC), scale


def upscale_if_small(bgr: np.ndarray, min_side: int = DEFAULT_MIN_SIDE_UPSCALE_TO):
    h, w = bgr.shape[:2]
    m    = min(h, w)
    if m >= min_side:
        return bgr, 1.0
    scale = float(min_side) / m
    nw, nh = int(round(w * scale)), int(round(h * scale))
    return cv2.resize(bgr, (nw, nh), interpolation=cv2.INTER_CUBIC), scale


# ----------------------------
# Scoring helpers
# ----------------------------
def score_from_detections(det_list: list, class_names=None) -> dict:
    """Score from per-letter detection list."""
    if class_names is None:
        class_names = DEFAULT_CLASS_NAMES
    if not det_list:
        return {"risk": 0.0, "counts": {n: 0 for n in class_names}, "total": 0}
    cls_ids   = [d["cls_id"] for d in det_list]
    counts    = Counter(cls_ids)
    total     = len(cls_ids)
    named     = {name: counts.get(i, 0) for i, name in enumerate(class_names)}
    reversal  = counts.get(CLASS_REVERSAL, 0)
    corrected = counts.get(CLASS_CORRECTED, 0)
    risk      = (reversal + corrected) / total if total > 0 else 0.0
    return {"risk": float(risk), "counts": named, "total": total}


def score_from_result(res, class_names=None):
    """Legacy scorer for whole-image YOLO result (kept for reference)."""
    if class_names is None:
        class_names = DEFAULT_CLASS_NAMES
    if res.boxes is None or len(res.boxes) == 0:
        return {"risk": 0.0, "counts": {n: 0 for n in class_names}, "total": 0}
    cls_ids   = [int(c) for c in res.boxes.cls.tolist()]
    counts    = Counter(cls_ids)
    total     = sum(counts.values())
    named     = {name: counts.get(i, 0) for i, name in enumerate(class_names)}
    reversal  = counts.get(CLASS_REVERSAL, 0)
    corrected = counts.get(CLASS_CORRECTED, 0)
    risk      = (reversal + corrected) / total if total > 0 else 0.0
    return {"risk": float(risk), "counts": named, "total": int(total)}


# ----------------------------
# PIL → BGR
# ----------------------------
def pil_to_bgr(pil_img: Image.Image) -> np.ndarray:
    rgb = np.array(pil_img.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


# ═══════════════════════════════════════════════════════════════════════════════
# Per-letter segmentation helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _binary_mask(bgr: np.ndarray, clean_canvas: bool = False) -> np.ndarray:
    """
    Binary mask — strokes=white, background=black.

    Two modes selected automatically by inspecting pixel variance:

    clean_canvas (low variance, e.g. Tkinter drawing):
      Simple brightness threshold at 30.  The canvas background is a
      near-perfect 0 after polarity inversion so this is reliable and fast.

    real image (high variance, e.g. photo/scan of handwriting):
      Otsu threshold on the already-inverted image.  Otsu finds the optimal
      split between ink and paper automatically, ignoring paper texture and
      lighting variation.  A morphological opening then removes small noise
      specks (paper grain, JPEG artifacts) that would create fake letters.
    """
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # A clean Tkinter canvas after inversion has >70% near-black pixels.
    # A real photo after inversion has almost none (all mid-gray).
    dark_bg_frac = float(np.mean(gray < 20))
    is_clean_canvas = clean_canvas or dark_bg_frac > 0.70

    if is_clean_canvas:
        _, binary = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)
    else:
        # Re-invert to get dark-ink-on-light-paper, then adaptive threshold
        # handles vignette & uneven lighting locally
        original = 255 - gray
        binary = cv2.adaptiveThreshold(
            original, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,   # ink=white, background=black
            blockSize=31,
            C=8
        )
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, k, iterations=1)

    return binary


def _find_letter_boxes(binary, H, W):
    """
    Find one bounding box per letter using connected components.

    Since the canvas is white strokes on black background, every group of
    physically connected white pixels is exactly one letter stroke cluster.
    A small dilation (5×5) bridges tiny intra-letter gaps (e.g. the dot and
    stem of 'i', or a slightly broken stroke) without bridging separate letters.
    No merging heuristics needed at all.
    """
    canvas_area = H * W

    # Small dilation bridges intra-letter gaps without touching separate letters
    k       = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    dilated = cv2.dilate(binary, k, iterations=1)

    # Label every connected white-pixel blob
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(dilated, connectivity=8)

    boxes = []
    for label in range(1, num_labels):      # label 0 = background, skip it
        x    = stats[label, cv2.CC_STAT_LEFT]
        y    = stats[label, cv2.CC_STAT_TOP]
        w    = stats[label, cv2.CC_STAT_WIDTH]
        h    = stats[label, cv2.CC_STAT_HEIGHT]
        area = stats[label, cv2.CC_STAT_AREA]   # actual white-pixel count

        if area < SEG_MIN_AREA:                         # noise speck
            continue
        if (w * h) > SEG_MAX_AREA_PCT * canvas_area:   # whole-canvas blob
            continue
        # For real photos: filter noise specks and edge vignette blobs
        # Minimum absolute size: must be at least 1% of image height tall
        min_h_px = max(20, int(H * 0.02))   # at least 2% of image height
        min_w_px = max(10, int(W * 0.008))  # at least 0.8% of image width
        if h < min_h_px or w < min_w_px:
            continue
        # Aspect ratio guard: very wide+short = ruled line or shadow edge
        if w > h * 10:
            continue
        # Edge vignette guard: blobs that span >30% of image height are shadows
        if h > H * 0.30 and w > W * 0.20:
            continue

        px = int(w * SEG_PAD_FACTOR);  py = int(h * SEG_PAD_FACTOR)
        x1 = max(0, x - px);           y1 = max(0, y - py)
        x2 = min(W, x + w + px);       y2 = min(H, y + h + py)
        boxes.append((x1, y1, x2, y2))

    return _sort_reading_order(boxes)


def _sort_reading_order(boxes):
    """Cluster into rows by y-centre, then sort each row left→right."""
    if not boxes:
        return []
    avg_h   = np.mean([y2-y1 for x1,y1,x2,y2 in boxes])
    row_tol = avg_h * 0.6
    sorted_ = sorted(boxes, key=lambda b: (b[1]+b[3])/2)
    rows    = []
    for box in sorted_:
        yc     = (box[1]+box[3]) / 2
        placed = False
        for row in rows:
            if abs(yc - np.mean([(b[1]+b[3])/2 for b in row])) < row_tol:
                row.append(box); placed = True; break
        if not placed:
            rows.append([box])
    result = []
    for row in rows:
        row.sort(key=lambda b: b[0])
        result.extend(row)
    return result


# ── Training image layout (decoded from label file) ───────────────────────────
# From train_0001.txt: all boxes are cx/cy/w/h in normalised coords
#   w = h = 0.05  → letter occupies 5% of image side
#   y centres: 0.1, 0.3, 0.5, 0.7, 0.9  → 5 rows, 20% apart
#   x centres: start ~0.0406, step ~0.0578 → up to 17 cols
# We reproduce this exactly on a TRAIN_CANVAS_SIZE square canvas.
TRAIN_CANVAS_SIZE = 768     # must match your training imgsz
TRAIN_ROWS        = [0.1, 0.3, 0.5, 0.7, 0.9]   # normalised y centres
TRAIN_X_START     = 0.040625                      # normalised x of first col
TRAIN_X_STEP      = 0.057813                      # normalised x step per col
TRAIN_LETTER_NORM = 0.05                          # normalised letter size (w=h)
TRAIN_MAX_COLS    = 17                            # max letters per row


def _fit_letter_into_cell(crop_bgr, cell_px, bg_color):
    """Scale letter to fill cell_px×cell_px (with a small margin), centred."""
    h, w = crop_bgr.shape[:2]
    if h == 0 or w == 0:
        return np.full((cell_px, cell_px, 3), bg_color, dtype=np.uint8)
    margin = max(2, cell_px // 8)
    inner  = cell_px - 2 * margin
    scale  = inner / max(h, w)
    nw     = max(1, int(round(w * scale)))
    nh     = max(1, int(round(h * scale)))
    scaled = cv2.resize(crop_bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
    cell   = np.full((cell_px, cell_px, 3), bg_color, dtype=np.uint8)
    yo     = (cell_px - nh) // 2
    xo     = (cell_px - nw) // 2
    cell[yo:yo+nh, xo:xo+nw] = scaled
    return cell


def _build_training_style_image(bgr, boxes, bg_color=(0, 0, 0)):
    """
    Place every detected letter into a TRAIN_CANVAS_SIZE square image using
    the EXACT same normalised coordinates as the training labels.

    Layout (from train_0001.txt):
      • 5 rows at y = 0.1, 0.3, 0.5, 0.7, 0.9
      • Up to 17 columns starting at x=0.0406, step 0.0578
      • Each letter bbox = 5% × 5% of the image

    Returns:
      composed   : BGR image ready to pass to YOLO
      positions  : list of (row_idx, col_idx, orig_x1, orig_y1, orig_x2, orig_y2)
    """
    S      = TRAIN_CANVAS_SIZE
    cell   = int(TRAIN_LETTER_NORM * S)          # 38px at 768
    canvas = np.full((S, S, 3), bg_color, dtype=np.uint8)

    positions  = []
    row_idx    = 0
    col_idx    = 0

    for box in boxes:
        if row_idx >= len(TRAIN_ROWS):
            break                                # no more rows

        # Normalised centre for this cell
        cx_n = TRAIN_X_START + col_idx * TRAIN_X_STEP
        cy_n = TRAIN_ROWS[row_idx]

        # Pixel top-left of the cell
        cx_px = int(round(cx_n * S))
        cy_px = int(round(cy_n * S))
        x0    = cx_px - cell // 2
        y0    = cy_px - cell // 2

        # Skip if the cell would overflow (shouldn't happen with the constants)
        if x0 < 0 or y0 < 0 or x0 + cell > S or y0 + cell > S:
            col_idx += 1
            if col_idx >= TRAIN_MAX_COLS:
                col_idx = 0
                row_idx += 1
            continue

        ox1, oy1, ox2, oy2 = box
        crop = bgr[oy1:oy2, ox1:ox2]
        cell_img = _fit_letter_into_cell(crop, cell, bg_color)
        canvas[y0:y0+cell, x0:x0+cell] = cell_img
        positions.append((row_idx, col_idx, ox1, oy1, ox2, oy2))

        col_idx += 1
        if col_idx >= TRAIN_MAX_COLS:
            col_idx = 0
            row_idx += 1

    return canvas, positions

def segment_and_predict(
    bgr: np.ndarray,
    model: YOLO,
    conf: float        = DEFAULT_CONF,
    imgsz: int         = DEFAULT_IMGSZ,
    bg_color: tuple    = (0, 0, 0),
    save_vis: bool     = False,
    vis_path: str      = "debug_segmentation.png",
    clean_canvas: bool = True,
) -> tuple:
    """
    Per-letter pipeline:
      1. Find all letter boxes via connected components
      2. Arrange them into a training-style image (grid of small letters)
      3. Run YOLO ONCE on that reconstructed image
      4. Map each YOLO detection back to the original canvas box

    When save_vis=True, saves:
      vis_path               — canvas with coloured bounding boxes
      vis_path_composed.jpg  — the training-style image fed to YOLO
    """
    H, W   = bgr.shape[:2]
    binary = _binary_mask(bgr, clean_canvas=clean_canvas)
    boxes  = _find_letter_boxes(binary, H, W)

    if not boxes:
        return [], []

    # ── Build training-style image ────────────────────────────────────────────
    composed, positions = _build_training_style_image(bgr, boxes, bg_color)

    if save_vis:
        comp_path = vis_path.replace(".jpg", "_composed.jpg").replace(".png", "_composed.jpg")
        ok = cv2.imwrite(str(comp_path), composed)
        print(f"[save] Composed   -> {comp_path}  (ok={ok})")

    # ── Run YOLO once on the composed image ───────────────────────────────────
    results = model.predict(composed, conf=conf, imgsz=imgsz, verbose=False)

    detections = []
    color_map  = {0: (0, 200, 0), 1: (0, 0, 255), 2: (255, 140, 0)}

    # Always draw segmentation boxes on vis so the file is useful even
    # when YOLO finds no detections
    if save_vis:
        vis = bgr.copy()
        for (bx1, by1, bx2, by2) in boxes:
            cv2.rectangle(vis, (bx1, by1), (bx2, by2), (200, 200, 0), 2)
    else:
        vis = None

    if not results or len(results[0].boxes) == 0:
        if save_vis and vis is not None:
            ok = cv2.imwrite(str(vis_path), vis)
            print(f"[save] Annotated  -> {vis_path}  (ok={ok}, no YOLO detections)")
        return detections, boxes

    res_boxes = results[0].boxes

    for det_i in range(len(res_boxes)):
        det_conf  = float(res_boxes.conf[det_i])
        cls_id    = int(res_boxes.cls[det_i])
        raw_label = model.names[cls_id]

        # YOLO box centre in composed image coords
        xywh  = res_boxes.xywh[det_i].tolist()   # [cx, cy, w, h] in px
        cx_c  = xywh[0]
        cy_c  = xywh[1]

        # Map pixel centre back to normalised coords, find nearest row/col
        S     = TRAIN_CANVAS_SIZE
        cx_n  = cx_c / S
        cy_n  = cy_c / S
        row   = min(range(len(TRAIN_ROWS)),   key=lambda i: abs(TRAIN_ROWS[i] - cy_n))
        col   = round((cx_n - TRAIN_X_START) / TRAIN_X_STEP)
        col   = max(0, min(col, TRAIN_MAX_COLS - 1))

        # Find the original canvas box for this cell
        orig_box = None
        for (r, c, ox1, oy1, ox2, oy2) in positions:
            if r == row and c == col:
                orig_box = (ox1, oy1, ox2, oy2)
                break

        if orig_box is None:
            continue   # detection fell outside any placed cell

        if "_" in raw_label:
            letter, orientation = raw_label.rsplit("_", 1)
        else:
            letter, orientation = raw_label, "Normal"

        detections.append({
            "cls_id":      cls_id,
            "label":       letter,
            "conf":        det_conf,
            "orientation": orientation,
            "canvas_bbox": orig_box,
        })

        if save_vis and vis is not None:
            x1, y1, x2, y2 = orig_box
            color = color_map.get(cls_id, (180, 180, 180))
            cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                vis, f"{letter} {det_conf:.2f}",
                (x1, max(y1 - 6, 12)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2
            )

    if save_vis and vis is not None:
        ok = cv2.imwrite(str(vis_path), vis)
        print(f"[save] Annotated  -> {vis_path}  (ok={ok})")

    return detections, boxes

def run_scoring_pipeline(
    pil_img:  Image.Image,
    model:    YOLO,
    args,
    out_dir:  Path,
) -> tuple:
    """
    PIL canvas image → score dict + saved raw path.

    Pipeline:
      PIL → BGR → [optional whole-canvas crop] → polarity normalise
          → per-letter segment + YOLO → aggregate score
    """
    bgr     = pil_to_bgr(pil_img)
    out_dir  = Path(out_dir).resolve()          # always use absolute path
    out_dir.mkdir(parents=True, exist_ok=True)
    ts       = time.strftime("%Y%m%d_%H%M%S")
    raw_path = out_dir / f"canvas_{ts}.png"
    try:
        pil_img.save(str(raw_path))
        print(f"[save] Raw image  -> {raw_path}")
    except Exception as e:
        print(f"[ERROR] Could not save raw image to {raw_path}: {e}")

    # Step A: optional whole-canvas crop to ink bounding box
    if args.no_crop:
        crop_bgr  = bgr
        bbox      = (0, 0, bgr.shape[1], bgr.shape[0])
        used_crop = False
    else:
        crop_bgr, bbox, used_crop = crop_to_ink_region(bgr)

    # Step B: polarity normalisation (makes strokes white on black)
    crop_bgr, inverted = normalize_polarity_if_needed(
        crop_bgr, enabled=args.normalize_polarity
    )

    # Step C: per-letter segmentation + per-crop YOLO
    #   After normalisation the background is black → bg_color=(0,0,0)
    bg_color = (0, 0, 0) if inverted else (255, 255, 255)

    vis_path = str(out_dir / f"canvas_{ts}_annotated_crop.jpg")
    # clean_canvas=True for Tkinter drawing, False for real photos/scans
    is_real_image = getattr(args, "image", None) is not None
    # Always save vis when --image is used (headless mode), or when --save_vis passed
    do_save_vis = args.save_vis or is_real_image
    detections, _boxes = segment_and_predict(
        crop_bgr,
        model,
        conf         = args.conf,
        imgsz        = args.imgsz,
        bg_color     = bg_color,
        save_vis     = do_save_vis,
        vis_path     = vis_path,
        clean_canvas = not is_real_image,
    )

    # Step D: aggregate score
    out = score_from_detections(detections, DEFAULT_CLASS_NAMES)
    out.update({
        "raw_canvas_path":    str(raw_path),
        "used_crop":          bool(used_crop),
        "crop_bbox_original": bbox,
        "polarity_inverted":  bool(inverted),
        "conf":               float(args.conf),
        "imgsz":              int(args.imgsz),
        "letters_detected":   len(detections),
        "letter_detail":      [
            {
                "label":       d["label"],
                "orientation": d["orientation"],
                "conf":        round(d["conf"], 3),
            }
            for d in detections
        ],
    })

    if do_save_vis:
        out["annotated_crop_path"] = vis_path
        print(f"[save] Annotated  -> {vis_path}")

    return out, raw_path
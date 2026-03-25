"""
model.py  —  PyTorch MobileNetV3 loading, image preprocessing, and scoring logic.

Pipeline:
    1. Detected via contour analysis
    2. Cropped with padding
    3. Padded to a square (preserves aspect ratio)
    4. Resized to 224x224 via Torchvision transforms
    5. Classified individually by MobileNetV3
"""

import time
from pathlib import Path
from collections import Counter

import numpy as np
import cv2
from PIL import Image

import torch
import torch.nn as nn
from torchvision import transforms, models


# ----------------------------
# Config defaults
# ----------------------------
# CRITICAL: This MUST match the PyTorch alphabetical ImageFolder mapping!
IDX_TO_CLASS = {0: "Corrected", 1: "Normal", 2: "Reversal"}
DEFAULT_CLASS_NAMES = list(IDX_TO_CLASS.values())

DEFAULT_MIN_SIDE_UPSCALE_TO = 900
DEFAULT_PAD = 80
DEFAULT_MIN_AREA_FRAC = 0.02
DEFAULT_NORMALIZE_POLARITY = True

# ── Segmentation tuning ───────────────────────────────────────────────────────
SEG_PAD_FACTOR   = 0.15     # padding around each letter as fraction of its size
SEG_MIN_AREA     = 10       # px² — blobs smaller than this are noise
SEG_MAX_AREA_PCT = 0.40     # blobs larger than 40% of canvas = background accident


# ----------------------------
# Model Loading
# ----------------------------
def load_model(weights_path: str, device: torch.device) -> nn.Module:
    """Loads MobileNetV3, handling both raw weights and YOLO-style checkpoints."""
    
    # Initialize the architecture exactly as you had it
    model = models.mobilenet_v3_small(weights=None)
    num_ftrs = model.classifier[3].in_features
    model.classifier[3] = nn.Linear(num_ftrs, 3) 
    
    # Load the file (using weights_only=False because YOLO files contain custom objects)
    checkpoint = torch.load(weights_path, map_location=device, weights_only=True)
    
    # --- The Extraction Logic ---
    if isinstance(checkpoint, dict):
        if "model" in checkpoint:
            print("Found 'model' key in checkpoint. Extracting weights...")
            # If it's the full object, get the state_dict; if it's already a dict, use it.
            payload = checkpoint["model"]
            state_dict = payload.state_dict() if hasattr(payload, "state_dict") else payload
        else:
            # It's a dictionary, but not a YOLO one (maybe a standard state_dict)
            state_dict = checkpoint
    else:
        # It's a raw model object
        state_dict = checkpoint.state_dict()

    # Load the extracted weights into your architecture
    # strict=False is a safety net if there are minor naming mismatches
    model.load_state_dict(state_dict, strict=True)
    
    model.to(device)
    model.eval()
    return model


# ----------------------------
# Polarity normalization
# ----------------------------
def normalize_polarity_if_needed(bgr: np.ndarray, enabled: bool = True):
    if not enabled:
        return bgr, False
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    med = float(np.median(gray))
    dark_frac = float(np.mean(gray < (med - 20)))
    if med > 100 or dark_frac < 0.15:
        inv = 255 - gray
        return cv2.cvtColor(inv, cv2.COLOR_GRAY2BGR), True
    return bgr, False


# ----------------------------
# Whole-canvas crop helper
# ----------------------------
def crop_to_ink_region(bgr: np.ndarray, pad: int = DEFAULT_PAD, min_area_frac: float = DEFAULT_MIN_AREA_FRAC):
    H, W  = bgr.shape[:2]
    full  = (0, 0, W, H)
    gray  = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray  = clahe.apply(gray)
    thr   = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 7)
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


# ----------------------------
# Scoring helpers
# ----------------------------
def score_from_detections(det_list: list) -> dict:
    if not det_list:
        return {"risk": 0.0, "counts": {n: 0 for n in DEFAULT_CLASS_NAMES}, "total": 0}
    
    cls_names = [d["label"] for d in det_list]
    counts    = Counter(cls_names)
    total     = len(cls_names)
    
    named     = {name: counts.get(name, 0) for name in DEFAULT_CLASS_NAMES}
    reversal  = counts.get("Reversal", 0)
    corrected = counts.get("Corrected", 0)
    
    risk      = (reversal + corrected) / total if total > 0 else 0.0
    return {"risk": float(risk), "counts": named, "total": total}


def pil_to_bgr(pil_img: Image.Image) -> np.ndarray:
    rgb = np.array(pil_img.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


# ═══════════════════════════════════════════════════════════════════════════════
# Per-letter segmentation helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _binary_mask(bgr: np.ndarray, clean_canvas: bool = False) -> np.ndarray:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    dark_bg_frac = float(np.mean(gray < 20))
    is_clean_canvas = clean_canvas or dark_bg_frac > 0.70

    if is_clean_canvas:
        _, binary = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY)
    else:
        original = 255 - gray
        binary = cv2.adaptiveThreshold(original, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 8)
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, k, iterations=1)
    return binary


def _find_letter_boxes(binary, H, W):
    canvas_area = H * W
    k       = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    dilated = cv2.dilate(binary, k, iterations=1)

    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(dilated, connectivity=8)

    boxes = []
    for label in range(1, num_labels):
        x    = stats[label, cv2.CC_STAT_LEFT]
        y    = stats[label, cv2.CC_STAT_TOP]
        w    = stats[label, cv2.CC_STAT_WIDTH]
        h    = stats[label, cv2.CC_STAT_HEIGHT]
        area = stats[label, cv2.CC_STAT_AREA]

        if area < SEG_MIN_AREA: continue
        if (w * h) > SEG_MAX_AREA_PCT * canvas_area: continue
        
        min_h_px = max(20, int(H * 0.02))
        min_w_px = max(10, int(W * 0.008))
        if h < min_h_px or w < min_w_px: continue
        if w > h * 10: continue
        if h > H * 0.30 and w > W * 0.20: continue

        px = int(w * SEG_PAD_FACTOR);  py = int(h * SEG_PAD_FACTOR)
        x1 = max(0, x - px);           y1 = max(0, y - py)
        x2 = min(W, x + w + px);       y2 = min(H, y + h + py)
        boxes.append((x1, y1, x2, y2))

    return _sort_reading_order(boxes)


def _sort_reading_order(boxes):
    if not boxes: return []
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


def _pad_to_square(crop_bgr, bg_color=(0, 0, 0)):
    """Pads a cropped letter to a perfect square to prevent stretching during resize."""
    h, w = crop_bgr.shape[:2]
    if h == 0 or w == 0:
        return np.full((10, 10, 3), bg_color, dtype=np.uint8)
    
    side = int(max(h, w) * 1.2) # 20% margin
    square = np.full((side, side, 3), bg_color, dtype=np.uint8)
    
    y0 = (side - h) // 2
    x0 = (side - w) // 2
    square[y0:y0+h, x0:x0+w] = crop_bgr
    return square


def segment_and_predict(
    bgr: np.ndarray,
    model: nn.Module,
    device: torch.device,
    bg_color: tuple    = (0, 0, 0),
    save_vis: bool     = False,
    vis_path: str      = "debug_segmentation.png",
    clean_canvas: bool = True,
) -> tuple:
    
    H, W   = bgr.shape[:2]
    binary = _binary_mask(bgr, clean_canvas=clean_canvas)
    boxes  = _find_letter_boxes(binary, H, W)

    if not boxes:
        return [], []

    # Same transforms used in validation during training
    val_transforms = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])

    detections = []
    
    # Predict each letter independently
    for (x1, y1, x2, y2) in boxes:
        # Use the binary mask to get a perfectly clean letter (white on black)
        # This prevents background noise from confusing the CNN
        crop_gray = binary[y1:y2, x1:x2]
        crop_bgr = cv2.cvtColor(crop_gray, cv2.COLOR_GRAY2BGR)
        
        crop_sq = _pad_to_square(crop_bgr, bg_color=bg_color)
        pil_crop = Image.fromarray(cv2.cvtColor(crop_sq, cv2.COLOR_BGR2RGB))
        
        input_tensor = val_transforms(pil_crop).unsqueeze(0).to(device)
        
        with torch.no_grad():
            outputs = model(input_tensor)
            probs = torch.nn.functional.softmax(outputs[0], dim=0)
            conf, cls_idx = torch.max(probs, dim=0)
            
        cls_idx = cls_idx.item()
        conf = conf.item()
        label = IDX_TO_CLASS[cls_idx]
        
        detections.append({
            "cls_id": cls_idx,
            "label": label,
            "conf": conf,
            "canvas_bbox": (x1, y1, x2, y2)
        })

    # ── Draw Visualization ────────────────────────────────────────
    if save_vis:
        vis = bgr.copy()
        color_map  = {0: (0, 165, 255), 1: (0, 200, 0), 2: (0, 0, 255)} # Corrected=Orange, Normal=Green, Reversal=Red
        stagger = False
        
        for det in detections:
            x1, y1, x2, y2 = det["canvas_bbox"]
            color = color_map.get(det["cls_id"], (180, 180, 180))
            
            cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)
            
            y_pos = max(y1 - 6, 12) if not stagger else y2 + 15
            stagger = not stagger
            
            cv2.putText(
                vis, f"{det['label']} {det['conf']:.2f}",
                (x1, y_pos), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA
            )

        ok = cv2.imwrite(str(vis_path), vis)
        print(f"[save] Annotated  -> {vis_path}  (ok={ok})")

    return detections, boxes


def run_scoring_pipeline(
    pil_img:  Image.Image,
    model:    nn.Module,
    device:   torch.device,
    args,
    out_dir:  Path,
) -> tuple:
    bgr     = pil_to_bgr(pil_img)
    out_dir  = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    ts       = time.strftime("%Y%m%d_%H%M%S")
    raw_path = out_dir / f"canvas_{ts}.png"
    
    try:
        pil_img.save(str(raw_path))
        print(f"[save] Raw image  -> {raw_path}")
    except Exception as e:
        print(f"[ERROR] Could not save raw image to {raw_path}: {e}")

    if args.no_crop:
        crop_bgr  = bgr
        bbox      = (0, 0, bgr.shape[1], bgr.shape[0])
        used_crop = False
    else:
        crop_bgr, bbox, used_crop = crop_to_ink_region(bgr)

    crop_bgr, inverted = normalize_polarity_if_needed(crop_bgr, enabled=args.normalize_polarity)

    # After normalisation the background is black -> bg_color=(0,0,0)
    bg_color = (0, 0, 0) if inverted else (255, 255, 255)

    vis_path = str(out_dir / f"canvas_{ts}_annotated_crop.jpg")
    is_real_image = getattr(args, "image", None) is not None
    do_save_vis = args.save_vis or is_real_image
    
    detections, _boxes = segment_and_predict(
        crop_bgr,
        model,
        device,
        bg_color     = bg_color,
        save_vis     = do_save_vis,
        vis_path     = vis_path,
        clean_canvas = not is_real_image,
    )

    out = score_from_detections(detections)
    out.update({
        "raw_canvas_path":    str(raw_path),
        "used_crop":          bool(used_crop),
        "crop_bbox_original": bbox,
        "polarity_inverted":  bool(inverted),
        "letters_detected":   len(detections),
        "letter_detail":      [
            {"label": d["label"], "conf": round(d["conf"], 3)} for d in detections
        ],
    })

    if do_save_vis:
        out["annotated_crop_path"] = vis_path

    return out, raw_path
"""
Handwriting inference service.
Uses the real scoring pipeline from handwriting_model.py:
  PIL → BGR → polarity normalise → per-letter segmentation → YOLO grid → score
"""
from __future__ import annotations
import logging, io, types
import numpy as np
from pathlib import Path
from PIL import Image

from app.core.config import settings
from app.models.schemas import HandwritingResult, LetterDetail

log = logging.getLogger(__name__)


def _make_args(conf=0.10, imgsz=768, save_vis=False,
               no_crop=True, normalize_polarity=True, image="__uploaded__"):
    """Build a minimal args namespace matching what run_scoring_pipeline expects."""
    a = types.SimpleNamespace()
    a.conf               = conf
    a.imgsz              = imgsz
    a.save_vis           = save_vis
    a.no_crop            = no_crop
    a.normalize_polarity = normalize_polarity
    a.image              = image   # non-None → real-image mode (not clean canvas)
    a.out_dir            = "outputs_handwriting"
    return a


class HandwritingService:
    def __init__(self):
        self.model = None
        self.ready = False
        self._load()

    def _load(self):
        path: Path = settings.handwriting_model_path
        if not path.exists():
            log.warning("Handwriting model not found at %s. Stub mode.", path)
            return
        try:
            from ultralytics import YOLO
            self.model = YOLO(str(path))
            self.ready = True
            log.info("YOLO handwriting model loaded from %s", path)
        except Exception as e:
            log.error("Failed to load handwriting model: %s", e)

    async def score(self, file_bytes: bytes, filename: str) -> HandwritingResult:
        if self.ready and self.model is not None:
            return self._run_pipeline(file_bytes)
        return self._stub()

    def _run_pipeline(self, file_bytes: bytes) -> HandwritingResult:
        from app.services.handwriting_model import run_scoring_pipeline

        # Decode image bytes → PIL (same as app.py --image path does)
        pil_img = Image.open(io.BytesIO(file_bytes)).convert("RGB")

        args    = _make_args()
        out_dir = Path(args.out_dir)

        result, _ = run_scoring_pipeline(pil_img, self.model, args, out_dir)

        # Map model.py output → our schema
        # model.py classes: Normal=0, Reversal=1, Corrected=2
        counts_raw = result.get("counts", {})
        total      = result.get("total", 0)
        risk       = float(result.get("risk", 0.0))

        # Convert to our reversal-focused schema
        counts = {
            "Normal":    counts_raw.get("Normal",    0),
            "Reversal":  counts_raw.get("Reversal",  0),
            "Corrected": counts_raw.get("Corrected", 0),
        }

        details = [
            LetterDetail(
                label=d.get("label", "?"),
                orientation=d.get("orientation", "Normal"),
                conf=round(float(d.get("conf", 0.0)), 3),
            )
            for d in result.get("letter_detail", [])
        ]

        return HandwritingResult(
            risk=round(risk, 4),
            counts=counts,
            total=total,
            letter_detail=details,
        )

    def _stub(self) -> HandwritingResult:
        log.debug("Stub mode: returning dummy handwriting prediction.")
        counts = {"Normal": 4, "Reversal": 1, "Corrected": 0}
        return HandwritingResult(
            risk=0.2,
            counts=counts,
            total=5,
            letter_detail=[],
        )

    async def evaluate(self, file_bytes: bytes, filename: str):
        raise NotImplementedError("Handwriting evaluation not yet wired.")


handwriting_service = HandwritingService()

"""
Handwriting inference service — MobileNetV3.
"""
from __future__ import annotations
import io, logging, types
from pathlib import Path
from PIL import Image

from app.core.config import settings
from app.models.schemas import HandwritingResult, LetterDetail

log = logging.getLogger(__name__)


def _make_args_upload():
    """Args for a real uploaded photo/scan — real-image mode."""
    a = types.SimpleNamespace()
    a.save_vis           = False
    a.no_crop            = True
    a.normalize_polarity = True
    a.image              = "__uploaded__"   # non-None → clean_canvas=False → adaptive threshold
    a.out_dir            = "outputs_handwriting"
    return a


def _make_args_canvas():
    """Args for browser canvas PNG — clean canvas mode."""
    a = types.SimpleNamespace()
    a.save_vis           = False
    a.no_crop            = True
    a.normalize_polarity = True
    a.image              = None              # None → clean_canvas=True → simple threshold
    a.out_dir            = "outputs_handwriting"
    return a


class HandwritingService:
    def __init__(self):
        self.model  = None
        self.device = None
        self.ready  = False
        self._load()

    def _load(self):
        path: Path = settings.handwriting_model_path
        if not path.exists():
            log.warning("Handwriting model not found at %s — stub mode.", path)
            return
        try:
            import torch
            from app.services.handwriting_model import load_model
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self.model  = load_model(str(path), self.device)
            self.ready  = True
            log.info("MobileNetV3 loaded from %s on %s", path, self.device)
        except ImportError:
            log.error("torch/torchvision not installed. Run: pip install torch torchvision")
        except Exception as e:
            log.error("Failed to load handwriting model: %s", e)

    # ── Uploaded photo / scan ─────────────────────────────────────────────────
    async def score(self, file_bytes: bytes, filename: str) -> HandwritingResult:
        if not self.ready or self.model is None:
            log.warning("Handwriting in stub mode — model not loaded.")
            return self._stub()
        return self._run(file_bytes, _make_args_upload())

    # ── Browser canvas PNG ────────────────────────────────────────────────────
    async def score_canvas(self, file_bytes: bytes) -> HandwritingResult:
        if not self.ready or self.model is None:
            log.warning("Handwriting in stub mode — model not loaded.")
            return self._stub()
        return self._run(file_bytes, _make_args_canvas())

    # ── Shared pipeline ───────────────────────────────────────────────────────
    def _run(self, file_bytes: bytes, args) -> HandwritingResult:
        from app.services.handwriting_model import run_scoring_pipeline

        pil_img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        result, _ = run_scoring_pipeline(pil_img, self.model, self.device, args, Path(args.out_dir))

        counts  = dict(result.get("counts", {}))
        total   = result.get("total", 0)
        risk    = float(result.get("risk", 0.0))
        details = [
            LetterDetail(
                label       = d.get("label", "?"),
                orientation = d.get("label", "Normal"),
                conf        = round(float(d.get("conf", 0.0)), 3),
            )
            for d in result.get("letter_detail", [])
        ]
        log.info("Handwriting result: risk=%.3f  total=%d  counts=%s", risk, total, counts)
        return HandwritingResult(risk=round(risk, 4), counts=counts, total=total, letter_detail=details)

    # ── Stub — model not loaded ───────────────────────────────────────────────
    def _stub(self) -> HandwritingResult:
        """Returns a neutral result when model isn't available."""
        return HandwritingResult(
            risk=0.0,
            counts={"Normal": 0, "Reversal": 0, "Corrected": 0},
            total=0,
            letter_detail=[],
        )

    async def evaluate(self, file_bytes: bytes, filename: str):
        raise NotImplementedError("Evaluation not wired.")


handwriting_service = HandwritingService()

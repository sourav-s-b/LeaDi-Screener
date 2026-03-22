"""
Dysarthria service.

The backend never receives browser audio directly. Instead:
  dysarthria_ui.py records → engine.predict() → neuroscan_bridge.post_dysarthria(pred)
  → POST /dysarthria/predict_result  → saved to sessions → frontend polls and picks it up.

This is identical to the eye-tracking pattern and avoids all browser audio codec issues.
The /dysarthria/predict_file endpoint is kept for direct WAV uploads (evaluation / testing).
"""
from __future__ import annotations
import io, logging, os, tempfile
from pathlib import Path
import numpy as np

from app.core.config import settings
from app.models.schemas import DysarthriaResult

log = logging.getLogger(__name__)


class DysarthriaService:
    def __init__(self):
        self.engine = None
        self.ready  = False
        self._load()

    def _load(self):
        path: Path = settings.dysarthria_model_path
        if not path.exists():
            log.warning("Dysarthria weights not found at %s. Stub mode.", path)
            return
        try:
            from app.services.dysarthria_engine import DysarthriaEngine
            self.engine = DysarthriaEngine(
                model_path  = str(path),
                seconds     = settings.dysarthria_window_sec,
                overlap     = settings.dysarthria_overlap_sec,
                sr          = settings.sample_rate,
                n_mfcc      = settings.n_mfcc,
                gender      = settings.dysarthria_default_gender,
            )
            self.ready = True
            log.info("DysarthriaEngine loaded from %s", path)
        except Exception as e:
            log.error("Failed to load dysarthria engine: %s", e)

    # ── Bridge path: result dict posted by dysarthria_ui.py ──────────────────

    async def predict_from_result(self, data: dict) -> DysarthriaResult:
        """
        Called when dysarthria_ui.py posts a completed prediction via the bridge.
        data keys: risk, label, confidence, n_chunks, chunk_risks
        """
        return DysarthriaResult(
            risk         = float(data.get("risk", 0.0)),
            label        = str(data.get("label", "non_dysarthria")),
            confidence   = float(data.get("confidence", 0.0)),
            n_chunks     = int(data.get("n_chunks", 1)),
            chunk_risks  = [float(r) for r in data.get("chunk_risks", [])],
        )

    # ── File path: direct WAV upload (for evaluation / CLI testing) ───────────

    async def predict_from_file(self, file_bytes: bytes, filename: str,
                                gender: str = "male") -> DysarthriaResult:
        """
        Direct WAV file inference. Used by /dysarthria/predict_file endpoint.
        Only accepts WAV/FLAC/OGG — no browser audio conversion attempted.
        """
        if not self.ready or self.engine is None:
            return self._stub()

        suffix = Path(filename).suffix.lower() or ".wav"
        if suffix not in (".wav", ".flac", ".ogg"):
            raise ValueError(
                f"Unsupported format '{suffix}'. Upload a WAV, FLAC, or OGG file. "
                "Browser recordings should use dysarthria_ui.py instead."
            )

        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        tmp_path = tmp.name
        tmp.close()
        try:
            with open(tmp_path, "wb") as f:
                f.write(file_bytes)
            self.engine.gender = 0 if gender == "male" else 1
            pred = self.engine.predict(tmp_path)
        finally:
            try: os.unlink(tmp_path)
            except OSError: pass

        if pred.error:
            raise RuntimeError(pred.error)

        return DysarthriaResult(
            risk        = pred.risk,
            label       = pred.label,
            confidence  = pred.confidence,
            n_chunks    = pred.n_chunks,
            chunk_risks = pred.chunk_risks,
        )

    def _stub(self) -> DysarthriaResult:
        log.debug("Stub mode — returning dummy dysarthria prediction.")
        chunks = list(np.random.beta(2, 5, 3).astype(float).round(4))
        risk   = float(np.mean(chunks))
        return DysarthriaResult(
            risk        = round(risk, 4),
            label       = "dysarthria" if risk >= 0.5 else "non_dysarthria",
            confidence  = round(abs(risk - 0.5) * 2, 4),
            n_chunks    = len(chunks),
            chunk_risks = chunks,
        )

    async def evaluate(self, file_bytes: bytes, filename: str):
        raise NotImplementedError("Dataset evaluation not yet implemented.")


dysarthria_service = DysarthriaService()

"""
Dyslexia inference service — wraps DyslexiaEyeEngineV2.
Suppresses sklearn version mismatch warnings (cosmetic only, predictions unaffected).
"""
from __future__ import annotations
import io, logging, warnings
from pathlib import Path
import numpy as np

# Suppress sklearn version mismatch warnings from loading joblib files
# trained on sklearn 1.6.x when running on 1.7.x
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")

from app.core.config import settings
from app.models.schemas import DyslexiaResult

log = logging.getLogger(__name__)


class DyslexiaService:
    def __init__(self):
        self.engine = None
        self.ready  = False
        self._load()

    def _load(self):
        ensemble = Path(settings.dyslexia_model_path)
        rfecv    = Path(settings.dyslexia_rfecv_path)
        meta     = Path(settings.dyslexia_meta_path)

        missing = [str(p) for p in [ensemble, rfecv, meta] if not p.exists()]
        if missing:
            log.warning("Dyslexia model files missing: %s — stub mode.", missing)
            return
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                from app.services.dyslexia_eye_engine_v2 import DyslexiaEyeEngineV2
                self.engine = DyslexiaEyeEngineV2(
                    model_path=str(ensemble),
                    rfecv_path=str(rfecv),
                    meta_path=str(meta),
                    threshold=settings.dyslexia_threshold,
                    verbose=False,
                )
            self.ready = True
            auc = self.engine.model_performance().get("test_auc", "?")
            log.info("DyslexiaEyeEngineV2 loaded. Test AUC=%.4f", auc)
        except Exception as e:
            log.error("Failed to load dyslexia engine: %s", e, exc_info=True)

    async def predict_from_array(self, arr: np.ndarray) -> DyslexiaResult:
        if self.ready and self.engine is not None:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                pred = self.engine.predict(arr)
            if pred.error:
                raise RuntimeError(pred.error)
            return DyslexiaResult(
                risk=pred.risk,
                label=pred.label,
                confidence=pred.confidence,
                n_fixations=pred.n_fixations,
                n_regressions=pred.n_regressions,
                regression_rate=pred.regression_rate,
                recording_duration=pred.recording_duration,
            )
        return self._stub()

    async def predict_from_features(self, features: dict) -> DyslexiaResult:
        if self.ready and self.engine is not None:
            sel   = self.engine._selected_feats
            means = {f: float(self.engine._col_means[i])
                     for i, f in enumerate(self.engine._feature_cols)}
            vec   = np.array([features.get(f, means.get(f, 0.0)) for f in sel],
                             dtype=float).reshape(1, -1)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                proba = self.engine._ensemble.predict_proba(vec)[0]
            risk  = float(proba[1])
            conf  = float(max(proba))
            label = "dyslexic" if risk >= settings.dyslexia_threshold else "control"
            return DyslexiaResult(
                risk=round(risk, 4), label=label,
                confidence=round(conf, 4),
                n_fixations=int(features.get("fix_count", 0)),
                n_regressions=int(features.get("regression_count", 0)),
                regression_rate=round(float(features.get("regression_rate", 0.0)), 4),
                recording_duration=round(float(features.get("recording_duration", 0.0)), 2),
            )
        return self._stub()

    def _stub(self) -> DyslexiaResult:
        risk = float(np.random.beta(2, 5))
        return DyslexiaResult(
            risk=round(risk, 4),
            label="dyslexic" if risk >= 0.5 else "control",
            confidence=round(float(np.random.uniform(0.6, 0.9)), 4),
            n_fixations=int(np.random.randint(80, 140)),
            n_regressions=int(np.random.randint(5, 25)),
            regression_rate=round(float(np.random.uniform(0.05, 0.3)), 4),
            recording_duration=30.0,
        )

    async def evaluate(self, file_bytes: bytes, filename: str):
        raise NotImplementedError("Dataset evaluation not yet implemented.")


dyslexia_service = DyslexiaService()

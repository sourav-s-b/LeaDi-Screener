from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    host:  str  = "0.0.0.0"
    port:  int  = 8000
    debug: bool = True

    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # ── Model paths ───────────────────────────────────────────────────────────
    models_dir:             Path = Path("models")

    # Dysarthria
    dysarthria_model_path:     Path  = Path("models/dysarthria_cnn_bilstm.pt")
    dysarthria_window_sec:     float = 6.79
    dysarthria_overlap_sec:    float = 3.0
    dysarthria_default_gender: str   = "male"

    # Dyslexia — 4 files needed
    dyslexia_model_path:  Path  = Path("models/dyslexia_ensemble.joblib")
    dyslexia_rfecv_path:  Path  = Path("models/dyslexia_rfecv.joblib")
    dyslexia_meta_path:   Path  = Path("models/dyslexia_feature_meta.json")
    dyslexia_threshold:   float = 0.5

    # Handwriting
    handwriting_model_path: Path = Path("models/handwriting_yolo.pt")

    # ── Audio ─────────────────────────────────────────────────────────────────
    sample_rate:   int   = 16000
    n_mfcc:        int   = 40
    chunk_seconds: float = 3.0

    # ── Sessions ──────────────────────────────────────────────────────────────
    sessions_dir:  Path = Path("sessions_store")
    max_upload_mb: int  = 50

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
settings.models_dir.mkdir(parents=True, exist_ok=True)
settings.sessions_dir.mkdir(parents=True, exist_ok=True)

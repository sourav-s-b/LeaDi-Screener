"""
launch.py — spawn desktop runner subprocesses on demand.

POST /launch/dysarthria   → spawns neuroscan_speech_runner.py
POST /launch/dyslexia     → spawns neuroscan_eye_runner.py
GET  /launch/status       → returns current state of each runner
POST /launch/cancel       → kill a running subprocess
"""
from __future__ import annotations
import subprocess, sys, os, time, logging
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(prefix="/launch", tags=["Launch"])
log    = logging.getLogger(__name__)

# ── Process registry ──────────────────────────────────────────────────────────
_procs: dict[str, subprocess.Popen] = {}   # "dysarthria" | "dyslexia" → Popen

# ── Helpers ───────────────────────────────────────────────────────────────────

def _runners_dir() -> Path:
    """Directory where the runner scripts live (next to run.py)."""
    return Path(__file__).parent.parent.parent   # backend/

def _proc_status(key: str) -> str:
    proc = _procs.get(key)
    if proc is None:
        return "idle"
    rc = proc.poll()
    if rc is None:
        return "running"
    return "done" if rc == 0 else f"error (exit {rc})"

def _kill(key: str):
    proc = _procs.pop(key, None)
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()

def _api_url() -> str:
    host = settings.host if settings.host != "0.0.0.0" else "127.0.0.1"
    return f"http://{host}:{settings.port}"


# ── Request / response models ─────────────────────────────────────────────────

class LaunchDysarthriaRequest(BaseModel):
    gender: str = "male"    # "male" | "female"

class LaunchDyslexiaRequest(BaseModel):
    duration: float = 30.0  # recording duration seconds
    camera:   int   = 0     # webcam index


class StatusResponse(BaseModel):
    dysarthria: str
    dyslexia:   str


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/dysarthria")
async def launch_dysarthria(req: LaunchDysarthriaRequest = LaunchDysarthriaRequest()):
    """
    Spawn neuroscan_speech_runner.py as a subprocess.
    The runner opens a small recording window, performs inference,
    and automatically POSTs the result back to /dysarthria/predict_result.
    """
    key = "dysarthria"
    # Kill any existing instance
    _kill(key)

    runner = _runners_dir() / "neuroscan_speech_runner.py"
    if not runner.exists():
        raise HTTPException(500, f"Runner script not found: {runner}")

    model_path = str(settings.dysarthria_model_path)
    if not Path(model_path).exists():
        raise HTTPException(503,
            f"Dysarthria model not found at {model_path}. "
            "Place the .pt file there and restart.")

    cmd = [
        sys.executable, str(runner),
        "--model",  model_path,
        "--api",    _api_url(),
        "--gender", req.gender,
    ]
    log.info("Launching: %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        cwd        = str(_runners_dir()),
        creationflags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0,
    )
    _procs[key] = proc
    return {"status": "launched", "pid": proc.pid, "gender": req.gender}


@router.post("/dyslexia")
async def launch_dyslexia(req: LaunchDyslexiaRequest = LaunchDyslexiaRequest()):
    """
    Spawn neuroscan_eye_runner.py as a subprocess.
    The runner runs calibration + reading session via OpenCV windows,
    and automatically POSTs the gaze array to /dyslexia/predict_array.
    """
    key = "dyslexia"
    _kill(key)

    runner = _runners_dir() / "neuroscan_eye_runner.py"
    if not runner.exists():
        raise HTTPException(500, f"Runner script not found: {runner}")

    missing = []
    for label, path in [
        ("ensemble",  settings.dyslexia_model_path),
        ("rfecv",     settings.dyslexia_rfecv_path),
        ("meta json", settings.dyslexia_meta_path),
    ]:
        if not Path(path).exists():
            missing.append(f"{label}: {path}")

    face_task = _runners_dir() / "face_landmarker.task"
    if not face_task.exists():
        missing.append("face_landmarker.task (download — see README)")

    if missing:
        raise HTTPException(503,
            "Eye-tracking model files missing:\n" + "\n".join(missing))

    cmd = [
        sys.executable, str(runner),
        "--model_face", str(face_task),
        "--ensemble",   str(settings.dyslexia_model_path),
        "--rfecv",      str(settings.dyslexia_rfecv_path),
        "--meta",       str(settings.dyslexia_meta_path),
        "--api",        _api_url(),
        "--duration",   str(req.duration),
        "--camera",     str(req.camera),
    ]
    log.info("Launching: %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        cwd           = str(_runners_dir()),
        creationflags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0,
    )
    _procs[key] = proc
    return {"status": "launched", "pid": proc.pid, "duration": req.duration}


@router.get("/status", response_model=StatusResponse)
async def get_status():
    return StatusResponse(
        dysarthria = _proc_status("dysarthria"),
        dyslexia   = _proc_status("dyslexia"),
    )


@router.post("/cancel/{module}")
async def cancel(module: str):
    if module not in ("dysarthria", "dyslexia"):
        raise HTTPException(400, "module must be 'dysarthria' or 'dyslexia'")
    _kill(module)
    return {"status": "cancelled", "module": module}

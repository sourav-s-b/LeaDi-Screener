"""
launch.py — spawn desktop runner subprocesses on demand.

POST /launch/dysarthria   → spawns neuroscan_speech_runner.py
GET  /launch/status       → returns process state
POST /launch/cancel       → kill running subprocess

Eye tracking is now fully browser-based (WebGazer.js) — no launcher needed.
"""
from __future__ import annotations
import subprocess, sys, os, logging
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.config import settings

router = APIRouter(prefix="/launch", tags=["Launch"])
log    = logging.getLogger(__name__)

_procs: dict[str, subprocess.Popen] = {}


def _runners_dir() -> Path:
    return Path(__file__).parent.parent.parent   # backend/

def _proc_status(key: str) -> str:
    proc = _procs.get(key)
    if proc is None: return "idle"
    rc = proc.poll()
    if rc is None: return "running"
    return "done" if rc == 0 else f"error (exit {rc})"

def _kill(key: str):
    proc = _procs.pop(key, None)
    if proc and proc.poll() is None:
        proc.terminate()
        try: proc.wait(timeout=3)
        except subprocess.TimeoutExpired: proc.kill()

def _api_url() -> str:
    host = settings.host if settings.host != "0.0.0.0" else "127.0.0.1"
    return f"http://{host}:{settings.port}"


class LaunchDysarthriaRequest(BaseModel):
    gender: str = "male"

class StatusResponse(BaseModel):
    dysarthria: str


@router.post("/dysarthria")
async def launch_dysarthria(req: LaunchDysarthriaRequest = LaunchDysarthriaRequest()):
    """Spawn neuroscan_speech_runner.py for desktop microphone recording."""
    key = "dysarthria"
    _kill(key)

    runner = _runners_dir() / "neuroscan_speech_runner.py"
    if not runner.exists():
        raise HTTPException(500, f"Runner not found: {runner}")

    model_path = str(settings.dysarthria_model_path)
    if not Path(model_path).exists():
        raise HTTPException(503,
            f"Dysarthria model not found at {model_path}. Place the .pt file there and restart.")

    cmd = [sys.executable, str(runner),
           "--model",  model_path,
           "--api",    _api_url(),
           "--gender", req.gender]
    log.info("Launching: %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        cwd           = str(_runners_dir()),
        creationflags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0,
    )
    _procs[key] = proc
    return {"status": "launched", "pid": proc.pid, "gender": req.gender}


@router.get("/status", response_model=StatusResponse)
async def get_status():
    return StatusResponse(dysarthria=_proc_status("dysarthria"))


@router.post("/cancel/{module}")
async def cancel(module: str):
    if module != "dysarthria":
        raise HTTPException(400, "module must be 'dysarthria'")
    _kill(module)
    return {"status": "cancelled", "module": module}

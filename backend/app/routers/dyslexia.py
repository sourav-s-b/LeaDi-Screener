"""
Dyslexia router — REST + WebSocket.

WebSocket /dyslexia/ws
    Streams live eye-tracking session from backend (runs MediaPipe locally).
    Messages from backend: {"type":"frame","lx":...,"ly":...,"rx":...,"ry":...}
                           {"type":"calibrating","dot":{"x":0.5,"y":0.5}}
                           {"type":"recording","elapsed":12.3}
                           {"type":"result","data":{...DyslexiaResult...}}
                           {"type":"error","message":"..."}
    Messages from client: {"cmd":"start","duration":30}
                           {"cmd":"stop"}
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import numpy as np, io, asyncio, json, logging

from app.services.dyslexia import dyslexia_service
from app.services.sessions  import save_session
from app.models.schemas     import DyslexiaResult, Session

router = APIRouter(prefix="/dyslexia", tags=["Dyslexia"])
log = logging.getLogger(__name__)


@router.post("/predict_array", response_model=DyslexiaResult)
async def predict_array(file: UploadFile = File(...)):
    """Receive (N,4) .npy array from neuroscan_bridge / live engine."""
    content = await file.read()
    try:
        arr = np.load(io.BytesIO(content))
    except Exception:
        raise HTTPException(422, "Could not parse .npy file.")
    if arr.ndim != 2 or arr.shape[1] not in (4, 5):
        raise HTTPException(422, f"Expected (N,4) or (N,5), got {arr.shape}.")
    if arr.shape[1] == 5:
        arr = arr[:, 1:]
    try:
        result = await dyslexia_service.predict_from_array(arr)
    except RuntimeError as e:
        raise HTTPException(422, str(e))
    save_session(Session(tool="dyslexia", risk=result.risk,
                         label=result.label, result=result.model_dump()))
    return result


@router.post("/predict_features", response_model=DyslexiaResult)
async def predict_features(features: dict):
    """JSON feature dict from neuroscan_bridge.post_features()."""
    result = await dyslexia_service.predict_from_features(features)
    save_session(Session(tool="dyslexia", risk=result.risk,
                         label=result.label, result=result.model_dump()))
    return result


@router.post("/predict", response_model=DyslexiaResult)
async def predict_trigger():
    """Fallback trigger — returns stub result."""
    result = await dyslexia_service.predict_from_features({})
    save_session(Session(tool="dyslexia", risk=result.risk,
                         label=result.label, result=result.model_dump()))
    return result


@router.websocket("/ws")
async def dyslexia_ws(ws: WebSocket):
    """
    Live eye-tracking session over WebSocket.

    The backend attempts to use dyslexia_live_engine.LiveGazeCapture.
    If mediapipe/cv2 is not installed or no webcam is found, sends an
    error frame immediately so the frontend can show a clear message.

    Protocol:
      client → {"cmd":"start","duration":30}
      server → {"type":"status","msg":"calibrating"}
      server → {"type":"dot","x":0.5,"y":0.5}          (calibration point)
      server → {"type":"status","msg":"recording"}
      server → {"type":"frame","lx":1.2,"ly":0.1,...}  (live gaze @ 15Hz)
      server → {"type":"result","data":{...}}
    """
    await ws.accept()
    try:
        msg  = await asyncio.wait_for(ws.receive_text(), timeout=30)
        data = json.loads(msg)
        if data.get("cmd") != "start":
            await ws.send_json({"type": "error", "message": "Send {cmd:start} first."})
            return
        duration = float(data.get("duration", 30.0))
    except asyncio.TimeoutError:
        await ws.send_json({"type": "error", "message": "Timeout waiting for start command."})
        return

    try:
        await _run_live_session(ws, duration)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


async def _run_live_session(ws: WebSocket, duration: float):
    """Run capture + calibration + recording and stream frames to browser."""
    loop = asyncio.get_event_loop()

    # ── Check dependencies ──
    try:
        import cv2
        import mediapipe
        from app.services.dyslexia_live_engine import LiveGazeCapture, GazeCalibration, ScreenConfig
    except ImportError as e:
        await ws.send_json({"type": "error",
            "message": f"Missing dependency: {e}. Install mediapipe and opencv-python on the backend."})
        return

    screen = ScreenConfig()
    try:
        cap = LiveGazeCapture(model_path="face_landmarker.task", screen=screen)
    except Exception as e:
        await ws.send_json({"type": "error", "message": f"Could not init webcam: {e}"})
        return

    # ── Calibration ──
    await ws.send_json({"type": "status", "msg": "calibrating"})

    CAL_POINTS = [
        (0.1, 0.1), (0.9, 0.1), (0.5, 0.5), (0.1, 0.9), (0.9, 0.9),
        (0.5, 0.1), (0.1, 0.5), (0.9, 0.5), (0.5, 0.9),
    ]
    for px, py in CAL_POINTS:
        await ws.send_json({"type": "dot", "x": px, "y": py})
        await asyncio.sleep(1.5)
        # Check client hasn't disconnected
        try:
            ws.client_state  # raises if closed
        except Exception:
            return

    await ws.send_json({"type": "status", "msg": "recording"})

    # ── Recording — stream frames at ~15Hz ──
    cap.start()
    start = asyncio.get_event_loop().time()
    arr_buffer = []

    try:
        while asyncio.get_event_loop().time() - start < duration:
            elapsed = asyncio.get_event_loop().time() - start
            sample = await loop.run_in_executor(None, cap.get_latest_sample)
            if sample and not sample.l_blink:
                arr_buffer.append([sample.lx_deg, sample.ly_deg,
                                   sample.rx_deg, sample.ry_deg])
                await ws.send_json({
                    "type": "frame",
                    "elapsed": round(elapsed, 1),
                    "lx": round(sample.lx_deg, 3),
                    "ly": round(sample.ly_deg, 3),
                    "rx": round(sample.rx_deg, 3),
                    "ry": round(sample.ry_deg, 3),
                })
            await asyncio.sleep(1 / 15)   # 15 Hz stream to browser
    finally:
        cap.stop()

    if len(arr_buffer) < 50:
        await ws.send_json({"type": "error",
            "message": "Not enough gaze data collected. Ensure face is visible and well-lit."})
        return

    # ── Predict ──
    arr    = np.array(arr_buffer, dtype=np.float32)
    result = await dyslexia_service.predict_from_array(arr)
    save_session(Session(tool="dyslexia", risk=result.risk,
                         label=result.label, result=result.model_dump()))

    await ws.send_json({"type": "result", "data": result.model_dump()})

from pydantic import BaseModel
from typing import List

# 1. Define the expected JSON structure from React
class RawGazePayload(BaseModel):
    gaze_data: List[List[float]]

@router.post("/predict_raw", response_model=DyslexiaResult)
async def predict_raw_json(payload: RawGazePayload):
    """
    Receive raw [[t, lx, ly, rx, ry], ...] from the React frontend.
    This replaces the need for the frontend to calculate fake features.
    """
    # Convert the JSON list of lists directly into a numpy array
    arr = np.array(payload.gaze_data, dtype=np.float32)
    
    if arr.ndim != 2 or arr.shape[1] not in (4, 5):
        raise HTTPException(422, f"Expected (N,4) or (N,5), got {arr.shape}.")
        
    # If the frontend sent timestamps (5 columns), strip the first column
    if arr.shape[1] == 5:
        arr = arr[:, 1:]
        
    try:
        # Pass the array to your existing service
        result = await dyslexia_service.predict_from_array(arr)
    except RuntimeError as e:
        raise HTTPException(422, str(e))
        
    # Save session and return
    save_session(Session(tool="dyslexia", risk=result.risk,
                         label=result.label, result=result.model_dump()))
    return result
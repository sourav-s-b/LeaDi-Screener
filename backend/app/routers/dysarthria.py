"""
Dysarthria router.

POST /dysarthria/predict_result
    Primary path. dysarthria_ui.py calls neuroscan_bridge.post_dysarthria(pred)
    which posts the completed Prediction dict here. Result saved to sessions.

POST /dysarthria/predict_file
    Secondary path. Direct WAV/FLAC file upload for evaluation/testing.
    Only accepts WAV-family files — no browser audio.
"""
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional

from app.services.dysarthria import dysarthria_service
from app.services.sessions   import save_session
from app.models.schemas      import DysarthriaResult, Session

router = APIRouter(prefix="/dysarthria", tags=["Dysarthria"])


@router.post("/predict_result", response_model=DysarthriaResult)
async def predict_result(data: dict):
    """
    Receive a completed prediction from dysarthria_ui.py via neuroscan_bridge.
    Body: { risk, label, confidence, n_chunks, chunk_risks, wav_path? }
    """
    try:
        result = await dysarthria_service.predict_from_result(data)
    except Exception as e:
        raise HTTPException(422, str(e))

    save_session(Session(
        tool   = "dysarthria",
        risk   = result.risk,
        label  = result.label,
        result = result.model_dump(),
    ))
    return result


@router.post("/predict_file", response_model=DysarthriaResult)
async def predict_file(
    file:   UploadFile        = File(...),
    gender: Optional[str]     = Form("male"),
):
    """
    Direct WAV/FLAC file upload. For evaluation and CLI testing only.
    Browser recordings must use dysarthria_ui.py + neuroscan_bridge instead.
    """
    if not file.filename:
        raise HTTPException(400, "No file provided.")
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(413, "File too large (max 50 MB).")
    try:
        result = await dysarthria_service.predict_from_file(
            content, file.filename, gender or "male"
        )
    except ValueError as e:
        raise HTTPException(415, str(e))
    except RuntimeError as e:
        raise HTTPException(422, str(e))

    save_session(Session(
        tool   = "dysarthria",
        risk   = result.risk,
        label  = result.label,
        result = result.model_dump(),
    ))
    return result


# Legacy alias so old frontend code doesn't break during transition
@router.post("/predict", response_model=DysarthriaResult)
async def predict_legacy(
    file:   Optional[UploadFile] = File(None),
    gender: Optional[str]        = Form("male"),
):
    if file and file.filename:
        return await predict_file(file=file, gender=gender)
    # No file = stub result (UI trigger)
    result = dysarthria_service._stub()
    save_session(Session(
        tool="dysarthria", risk=result.risk,
        label=result.label, result=result.model_dump(),
    ))
    return result


@router.post("/evaluate")
async def evaluate(file: UploadFile = File(...)):
    raise HTTPException(501, "Evaluation not yet implemented.")

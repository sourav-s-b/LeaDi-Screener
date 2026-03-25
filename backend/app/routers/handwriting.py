from fastapi import APIRouter, UploadFile, File, HTTPException
from app.services.handwriting import handwriting_service
from app.services.sessions    import save_session
from app.models.schemas       import HandwritingResult, Session

router = APIRouter(prefix="/handwriting", tags=["Handwriting"])
MAX_BYTES = 20 * 1024 * 1024


@router.post("/score", response_model=HandwritingResult)
async def score(file: UploadFile = File(...)):
    """Score an uploaded image (photo or scan)."""
    if not file.filename:
        raise HTTPException(400, "No file provided.")
    allowed = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    ext = "." + file.filename.rsplit(".", 1)[-1].lower()
    if ext not in allowed:
        raise HTTPException(415, f"Unsupported type '{ext}'.")
    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(413, "Image too large (max 20 MB).")
    result = await handwriting_service.score(content, file.filename)
    save_session(Session(tool="handwriting", risk=result.risk,
                         label="reversal_detected" if result.risk >= 0.35 else "no_reversal",
                         result=result.model_dump()))
    return result


@router.post("/score_canvas", response_model=HandwritingResult)
async def score_canvas(file: UploadFile = File(...)):
    """Score a PNG blob from the browser drawing canvas."""
    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(413, "Canvas image too large.")
    result = await handwriting_service.score_canvas(content)
    save_session(Session(tool="handwriting", risk=result.risk,
                         label="reversal_detected" if result.risk >= 0.35 else "no_reversal",
                         result=result.model_dump()))
    return result


@router.post("/evaluate")
async def evaluate(file: UploadFile = File(...)):
    raise HTTPException(501, "Evaluation not implemented.")

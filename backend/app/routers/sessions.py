from fastapi import APIRouter, HTTPException
from app.services.sessions import list_sessions, load_session, delete_session
from app.models.schemas    import Session, SessionSummary
from typing import List

router = APIRouter(prefix="/sessions", tags=["Sessions"])


@router.get("", response_model=List[SessionSummary])
async def get_sessions():
    return list_sessions()


@router.get("/{session_id}", response_model=Session)
async def get_session(session_id: str):
    s = load_session(session_id)
    if s is None:
        raise HTTPException(404, f"Session '{session_id}' not found.")
    return s


@router.delete("/{session_id}")
async def remove_session(session_id: str):
    ok = delete_session(session_id)
    if not ok:
        raise HTTPException(404, f"Session '{session_id}' not found.")
    return {"deleted": session_id}

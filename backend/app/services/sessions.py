"""
Simple JSON-file session store.
Each session is saved as  sessions_store/<id>.json
No database required — easy to swap for SQLite/Postgres later.
"""

from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
from typing import List, Optional

from app.core.config import settings
from app.models.schemas import Session, SessionSummary


def _path(session_id: str) -> Path:
    return settings.sessions_dir / f"{session_id}.json"


def _serialise(obj):
    """Custom JSON serialiser for datetime objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serialisable")


def save_session(session: Session) -> Session:
    data = json.loads(session.model_dump_json())
    _path(session.id).write_text(json.dumps(data, default=_serialise, indent=2))
    return session


def load_session(session_id: str) -> Optional[Session]:
    p = _path(session_id)
    if not p.exists():
        return None
    return Session.model_validate(json.loads(p.read_text()))


def list_sessions() -> List[SessionSummary]:
    sessions = []
    for p in sorted(settings.sessions_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            raw = json.loads(p.read_text())
            sessions.append(SessionSummary(
                id=raw["id"],
                tool=raw["tool"],
                timestamp=raw["timestamp"],
                risk=raw["risk"],
                label=raw["label"],
            ))
        except Exception:
            continue
    return sessions


def delete_session(session_id: str) -> bool:
    p = _path(session_id)
    if not p.exists():
        return False
    p.unlink()
    return True

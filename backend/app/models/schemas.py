from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal, Any
from datetime import datetime
import uuid


# ── Shared ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status:  str = "ok"
    version: str = "0.1.0"


# ── Dysarthria ────────────────────────────────────────────────────────────────

class DysarthriaResult(BaseModel):
    risk:        float = Field(..., ge=0, le=1)
    label:       Literal["dysarthria", "non_dysarthria"]
    confidence:  float = Field(..., ge=0, le=1)
    n_chunks:    int
    chunk_risks: list[float]


# ── Dyslexia ──────────────────────────────────────────────────────────────────

class DyslexiaResult(BaseModel):
    risk:               float = Field(..., ge=0, le=1)
    label:              Literal["dyslexic", "control", "dyslexia", "non_dyslexia"]
    confidence:         float = Field(..., ge=0, le=1)
    n_fixations:        int
    n_regressions:      int
    regression_rate:    float
    recording_duration: float


# ── Handwriting ───────────────────────────────────────────────────────────────

class LetterDetail(BaseModel):
    label:       str
    orientation: str
    conf:        float


class HandwritingResult(BaseModel):
    risk:          float = Field(..., ge=0, le=1)
    counts:        dict[str, int]
    total:         int
    letter_detail: list[LetterDetail]


# ── Evaluation report ─────────────────────────────────────────────────────────

class EvalReport(BaseModel):
    accuracy:    float
    sensitivity: float
    specificity: float
    roc_auc:     float
    pr_auc:      float
    conf_matrix: list[list[int]]
    n_samples:   int


# ── Session ───────────────────────────────────────────────────────────────────

ToolId = Literal["dysarthria", "dyslexia", "handwriting"]

class Session(BaseModel):
    id:        str        = Field(default_factory=lambda: str(uuid.uuid4()))
    tool:      ToolId
    timestamp: datetime   = Field(default_factory=datetime.utcnow)
    risk:      float
    label:     str
    result:    Any        # the full result object


class SessionSummary(BaseModel):
    """Lighter version for the sessions list endpoint."""
    id:        str
    tool:      ToolId
    timestamp: datetime
    risk:      float
    label:     str

"""
NeuroScan — FastAPI backend
Run: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.core.config   import settings
from app.models.schemas import HealthResponse
from app.routers       import dysarthria, dyslexia, handwriting, sessions, launch


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title       = "NeuroScan API",
    description = "Multimodal Dyslexia & Dysarthria Screening — Dysarthria · Dyslexia · Handwriting",
    version     = "0.1.0",
    docs_url    = "/docs",
    redoc_url   = "/redoc",
)


# ── Middleware ────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins     = settings.cors_origins,
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1024)


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(dysarthria.router)
app.include_router(dyslexia.router)
app.include_router(handwriting.router)
app.include_router(sessions.router)
app.include_router(launch.router)


# ── Core endpoints ────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["Core"])
async def health():
    """Liveness probe — used by the frontend StatusIndicator every 30s."""
    return HealthResponse()


@app.get("/", tags=["Core"])
async def root():
    return {
        "name":    "NeuroScan API",
        "version": "0.1.0",
        "docs":    "/docs",
        "modules": ["dysarthria", "dyslexia", "handwriting"],
    }

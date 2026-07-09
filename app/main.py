"""
StadiumPulse — FastAPI application entry point (app/main.py)

Routes:
  GET  /            → serves frontend/index.html
  GET  /health      → alias for /api/health (convenience)
  GET  /api/health  → liveness check + KB status
  POST /api/chat    → RAG pipeline, rate-limited, input-validated

Security practices implemented here:
  - Rate limiting via Depends(check_rate_limit)
  - Input validation via Pydantic ChatRequest (in models.py)
  - CORS restricted to same-origin in production annotation
  - No secrets in code — GEMINI_API_KEY read from environment only
  - Static files served from a fixed, sandboxed directory
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .limiter import check_rate_limit
from .models import ChatRequest, ChatResponse, HealthResponse, Settings
from .rag import KnowledgeBase, get_kb, process_query

# Configure standard logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

settings = Settings()

# ─── App setup ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for FastAPI (replaces deprecated on_event)."""
    get_kb()
    logger.info("✅ StadiumPulse v2.1 started — KB loaded, RAG engine ready.")
    if settings.gemini_api_key:
        logger.info("🤖 GEMINI_API_KEY detected — Live Gemini integration active.")
    else:
        logger.info("ℹ️ No GEMINI_API_KEY — running in fully-simulated RAG mode.")
    yield
    # Cleanup on shutdown could go here

app = FastAPI(
    title="StadiumPulse Fan Assistant API",
    description=(
        "Multilingual, accessibility-aware wayfinding assistant for "
        "FIFA World Cup 2026 venues. Responses are grounded in a synthetic "
        "venue knowledge base — no live FIFA data is used."
    ),
    version="2.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

# Custom Security Headers Middleware
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# CORS — controlled by environment variables (defaults to ["*"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ─── Static frontend ──────────────────────────────────────────────────────────

_FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

app.mount(
    "/static",
    StaticFiles(directory=str(_FRONTEND_DIR)),
    name="static",
)


@app.get("/", include_in_schema=False)
async def serve_index() -> FileResponse:
    """Serve the Fan Assistant single-page app."""
    return FileResponse(str(_FRONTEND_DIR / "index.html"))


# ─── Health check ─────────────────────────────────────────────────────────────

@app.get("/api/health", response_model=HealthResponse, tags=["system"])
@app.get("/health", response_model=HealthResponse, include_in_schema=False)
async def health() -> HealthResponse:
    """Liveness + readiness check. Confirms KB is loaded."""
    kb = get_kb()
    return HealthResponse(status="ok", kb_loaded=kb.loaded, version="2.0.0")


# ─── Chat endpoint ────────────────────────────────────────────────────────────

@app.post(
    "/api/chat",
    response_model=ChatResponse,
    tags=["assistant"],
    summary="Fan Assistant chat — grounded RAG response",
    description=(
        "Accepts a fan's question and returns a grounded response from the venue "
        "knowledge base. Input is validated and rate-limited. "
        "When no KB match is found, returns an explicit 'I don't know' fallback "
        "rather than hallucinating an answer."
    ),
)
async def chat(
    request: ChatRequest,
    _: None = Depends(check_rate_limit),
    kb: KnowledgeBase = Depends(get_kb),
) -> ChatResponse:
    """
    RAG chat endpoint.

    FastAPI's Depends(check_rate_limit) enforces the 20 req/min per-IP limit
    before any RAG processing begins — malformed or rate-exceeded requests
    never reach the KB retrieval layer.
    """
    result = process_query(
        message=request.message,
        language=request.language,
        accessibility_mode=request.accessibility_mode,
        kb=kb,
    )
    return ChatResponse(**result)


@app.get("/api/density", tags=["system"], summary="Get synthetic gate wait times")
async def get_density():
    """
    Returns synthetic, pseudo-random wait times for stadium gates to simulate
    real-time crowd surge monitoring.
    """
    import time
    import math
    
    # Use time as a seed to create dynamic but continuous wait times
    t = time.time() / 600.0  # Slow changing (10 min cycles)
    
    return {
        "A": max(2, int(15 + 10 * math.sin(t))),
        "B": max(2, int(8 + 5 * math.sin(t + 1))),
        "C": max(2, int(25 + 15 * math.sin(t + 2))),  # Gate C is usually busiest
        "D": max(2, int(5 + 3 * math.sin(t + 3))),
        "E": max(2, int(12 + 6 * math.sin(t + 4))),
        "G": max(1, int(3 + 2 * math.sin(t + 5)))
    }

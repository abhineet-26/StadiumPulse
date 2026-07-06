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

import os
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .limiter import check_rate_limit
from .models import ChatRequest, ChatResponse, HealthResponse
from .rag import KnowledgeBase, get_kb, process_query

# ─── App setup ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="StadiumPulse Fan Assistant API",
    description=(
        "Multilingual, accessibility-aware wayfinding assistant for "
        "FIFA World Cup 2026 venues. Responses are grounded in a synthetic "
        "venue knowledge base — no live FIFA data is used."
    ),
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# CORS — open for local demo; restrict to your domain in production
# Production note: replace ["*"] with ["https://yourdomain.com"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


# ─── Startup ──────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event() -> None:
    """Pre-load KB at startup so first request isn't slow."""
    get_kb()
    print("✅ StadiumPulse v2.0 started — KB loaded, RAG engine ready.")
    # LLM_STUB: if GEMINI_API_KEY is set, initialize Gemini client here
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        print("🤖 GEMINI_API_KEY detected — LLM integration stub ready (not active in this build).")
    else:
        print("ℹ️  No GEMINI_API_KEY — running in fully-simulated RAG mode.")

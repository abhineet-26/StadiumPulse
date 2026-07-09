"""
StadiumPulse — FastAPI application entry point (app/main.py)

Routes:
  GET  /            → serves frontend/index.html
  GET  /health      → alias for /api/health (convenience)
  GET  /api/health  → liveness check + KB status
  POST /api/chat    → RAG pipeline, rate-limited, input-validated
  GET  /api/density → synthetic gate crowd wait times
  GET  /api/match   → synthetic live match state

Security practices implemented here:
  - Rate limiting via Depends(check_rate_limit)
  - Input validation via Pydantic ChatRequest (in models.py)
  - CORS restricted to same-origin in production annotation
  - No secrets in code — GEMINI_API_KEY read from environment only
  - Static files served from a fixed, sandboxed directory
  - Full security headers: CSP, HSTS, X-Frame-Options, Referrer-Policy
"""
from __future__ import annotations

import logging
import math
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import routes
from .models import Settings
from .rag import get_kb

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
    logger.info("✅ StadiumPulse v3.0 started — KB loaded, RAG engine ready.")
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
    version="3.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)

# Custom Security Headers Middleware
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Attach production-grade security headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; "
        "connect-src 'self'; "
        "img-src 'self' data:; "
        "frame-ancestors 'none';"
    )
    return response

# CORS — controlled by environment variables (defaults to ["*"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ─── Global Exception Handler ──────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global error on {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error. Please try again later."},
    )

# ─── Include API Routes ───────────────────────────────────────────────────────

app.include_router(routes.router)

# ─── Static frontend ──────────────────────────────────────────────────────────

_FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

app.mount(
    "/static",
    StaticFiles(directory=str(_FRONTEND_DIR)),
    name="static",
)

@app.get("/", include_in_schema=False)
async def serve_index() -> FileResponse:
    """Serve the single-page app."""
    return FileResponse(str(_FRONTEND_DIR / "index.html"))

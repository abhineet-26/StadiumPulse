import math
import time
from fastapi import APIRouter, Depends

from ..limiter import check_rate_limit
from ..models import ChatRequest, ChatResponse, HealthResponse
from ..rag import KnowledgeBase, get_kb, process_query

router = APIRouter(prefix="/api")

@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    """Liveness + readiness check. Confirms KB is loaded."""
    kb = get_kb()
    return HealthResponse(status="ok", kb_loaded=kb.loaded, version="3.0.0")

@router.post(
    "/chat",
    response_model=ChatResponse,
    tags=["assistant"],
    summary="Fan Assistant chat — grounded RAG response",
)
async def chat(
    request: ChatRequest,
    _: None = Depends(check_rate_limit),
    kb: KnowledgeBase = Depends(get_kb),
) -> ChatResponse:
    """RAG chat endpoint."""
    result = process_query(
        message=request.message,
        language=request.language,
        accessibility_mode=request.accessibility_mode,
        kb=kb,
    )
    return ChatResponse(**result)

@router.get("/density", tags=["system"], summary="Get synthetic gate wait times")
async def get_density():
    """
    Returns synthetic, pseudo-random wait times for stadium gates to simulate
    real-time crowd surge monitoring.
    """
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

@router.get("/match", tags=["system"], summary="Get synthetic live match state")
async def get_match() -> dict:
    """
    Returns a synthetic live match state for the FIFA WC 2026 demo.
    Simulates match progression based on wall-clock time relative to kickoff.
    """
    elapsed_min = int((time.time() % 5400) / 60)  # 90-min cycle
    in_play = elapsed_min < 90
    return {
        "home_team": "USA",
        "away_team": "POR",
        "home_score": min(3, elapsed_min // 30),
        "away_score": min(2, elapsed_min // 45),
        "minute": elapsed_min if in_play else 90,
        "status": "LIVE" if in_play else "FT",
        "venue": "MetLife Stadium",
        "capacity": 82500,
    }

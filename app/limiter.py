"""
In-memory rate limiter for the StadiumPulse chat API.

Limits each client IP to RATE_LIMIT_PER_MINUTE requests per 60-second window.
Uses a simple sliding-window approximation with a defaultdict of timestamps.

Production note (documented, not built for MVP):
    Replace with Redis-backed sliding window or an API gateway rate limiter
    (e.g. Kong, AWS API Gateway throttling) for multi-instance deployments.
"""
from __future__ import annotations

import time
from collections import defaultdict
from typing import Dict, List

from fastapi import HTTPException, Request

from .models import Settings

settings = Settings()

# Configurable via environment variable; default 20 req/min
_LIMIT: int = settings.rate_limit_per_minute
_WINDOW: int = 60  # seconds

# { client_ip: [timestamp, timestamp, ...] }
_request_log: Dict[str, List[float]] = defaultdict(list)


def check_rate_limit(request: Request) -> None:
    """
    Dependency function — raise HTTP 429 if the client IP exceeds the rate limit.

    Usage in FastAPI:
        @app.post("/api/chat", dependencies=[Depends(check_rate_limit)])
    """
    client_ip: str = _get_client_ip(request)
    now: float = time.monotonic()
    window_start: float = now - _WINDOW

    # Prune timestamps outside the current window
    timestamps = _request_log[client_ip]
    _request_log[client_ip] = [t for t in timestamps if t > window_start]

    if len(_request_log[client_ip]) >= _LIMIT:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please wait before sending more requests.",
            headers={"Retry-After": str(_WINDOW)},
        )

    _request_log[client_ip].append(now)


def _get_client_ip(request: Request) -> str:
    """Extract real client IP, respecting X-Forwarded-For for proxy deployments."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"

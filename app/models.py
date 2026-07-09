"""
Pydantic request / response models for the StadiumPulse chat API.
Input validation is the first security layer — all constraints enforced here
before any business logic runs.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration via environment variables.
    pydantic-settings automatically reads from the environment and .env files.
    """
    gemini_api_key: Optional[str] = None
    rate_limit_per_minute: int = Field(default=20)
    allowed_origins: List[str] = Field(default=["*"])

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )


class ChatRequest(BaseModel):
    """
    Validated chat request from the Fan Assistant frontend.

    Security notes:
    - message: 1–500 chars — prevents empty/oversized injection payloads
    - language: strict enum — rejects arbitrary locale strings
    - accessibility_mode: bool — no injection surface
    """

    message: str = Field(
        min_length=1,
        max_length=500,
        json_schema_extra={"strip_whitespace": True},
        description="Fan's question in any supported language (max 500 chars)",
        examples=["Where is Gate C?", "Onde fica meu assento?"],
    )
    language: Literal["en", "pt", "es"] = Field(
        default="en",
        description="Response language: en (English), pt (Português), es (Español)",
    )
    accessibility_mode: bool = Field(
        default=False,
        description="When True, restricts routes to step-free/accessible paths only",
    )


class ChatResponse(BaseModel):
    """
    Structured response returned by the RAG engine.
    All fields are always present — no optional surprises for callers.
    """

    text: str = Field(description="Grounded response text in the requested language")
    intent: str = Field(
        description="Classified intent: wayfinding | seat_lookup | accessibility | transit | faq_policy | unknown"
    )
    confidence: Literal["high", "low"] = Field(
        description="high = answer found in KB; low = fallback (I don't know)"
    )
    source: Optional[str] = Field(
        default=None,
        description="KB source reference, e.g. 'venue.json → gates.Gate_C'. None on fallback.",
    )
    fallback: bool = Field(
        description="True when the query had no KB match and the refusal-to-guess policy activated"
    )
    language: str = Field(description="Language of the response text")


class HealthResponse(BaseModel):
    status: str
    kb_loaded: bool
    version: str

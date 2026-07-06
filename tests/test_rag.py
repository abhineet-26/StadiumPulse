"""
pytest suite for StadiumPulse RAG engine and API endpoints (v2.0)
Validates core requirements: RAG grounding, "I don't know" fallback, 
multilingual support, accessibility mode, and input validation.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.rag import KnowledgeBase, process_query

# Use TestClient for API endpoint tests
client = TestClient(app)

# Fixture to load KB once for unit tests
@pytest.fixture(scope="module")
def kb():
    kb_instance = KnowledgeBase()
    # Force load if not already loaded
    if not kb_instance.loaded:
        kb_instance = KnowledgeBase()
    return kb_instance


# ─── 1. RAG Grounding Tests ───────────────────────────────────────────────────

def test_gate_wayfinding_en(kb):
    """Query for a specific gate returns correct directions and high confidence."""
    res = process_query("How do I get to Gate C?", "en", False, kb)
    assert res["intent"] == "wayfinding"
    assert res["confidence"] == "high"
    assert "Gate C" in res["text"]
    assert "source" in res and "Gate_C" in res["source"]
    assert res["fallback"] is False


def test_seat_lookup_en(kb):
    """Query for a specific seat returns correct section/gate info."""
    res = process_query("Where is my seat? Section 108 Row 14", "en", False, kb)
    assert res["intent"] == "seat_lookup"
    assert res["confidence"] == "high"
    assert "Section 108" in res["text"]
    assert "Gate C" in res["text"]  # Section 108 belongs to Gate C


def test_transit_query(kb):
    """Query for transit returns schedule info."""
    res = process_query("When is the next metro train to Penn Station?", "en", False, kb)
    assert res["intent"] == "transit"
    assert res["confidence"] == "high"
    assert "NJ Transit" in res["text"] or "Meadowlands" in res["text"]


# ─── 2. Fallback Policy Tests (Highest Value) ─────────────────────────────────

def test_fallback_unknown_query(kb):
    """OOS query triggers refusal-to-guess policy (confidence=low, fallback=True)."""
    res = process_query("What crypto should I buy right now?", "en", False, kb)
    assert res["confidence"] == "low"
    assert res["fallback"] is True
    assert res["source"] is None


def test_fallback_directs_to_staff(kb):
    """Fallback message must instruct the user to ask a human, avoiding hallucination."""
    res = process_query("How do I buy FIFA cryptocurrency tokens?", "en", False, kb)
    text_lower = res["text"].lower()
    assert "volunteer" in text_lower or "staff" in text_lower
    assert "guess" in text_lower or "dangerous" in text_lower


# ─── 3. Multilingual Tests ────────────────────────────────────────────────────

def test_portuguese_wayfinding(kb):
    """Portuguese query returns Portuguese text."""
    # "Where is Gate C?" in Portuguese
    res = process_query("Onde fica o Portão C?", "pt", False, kb)
    assert res["language"] == "pt"
    assert "lado" in res["text"] or "Portão C" in res["text"]
    assert res["confidence"] == "high"


def test_spanish_seat_lookup(kb):
    """Spanish query returns Spanish text."""
    # "Where is my seat?" in Spanish
    res = process_query("¿Dónde está mi asiento? Sección 101 Fila 5", "es", False, kb)
    assert res["language"] == "es"
    assert "Sección 101" in res["text"]
    assert res["confidence"] == "high"


# ─── 4. Accessibility Mode Tests ──────────────────────────────────────────────

def test_accessibility_mode_on(kb):
    """With accessibility_mode=True, route text must mention step-free access."""
    res = process_query("How do I get to Gate C?", "en", True, kb)
    assert res["confidence"] == "high"
    text_lower = res["text"].lower()
    assert "step-free" in text_lower or "accessible" in text_lower or "♿" in text_lower


def test_accessibility_mode_off(kb):
    """With accessibility_mode=False, standard route text is used."""
    res = process_query("How do I get to Gate C?", "en", False, kb)
    assert res["confidence"] == "high"
    text_lower = res["text"].lower()
    assert "step-free access confirmed at this gate" not in text_lower


# ─── 5. API / Security Tests ──────────────────────────────────────────────────

def test_input_validation_empty():
    """Empty message is blocked by Pydantic."""
    response = client.post("/api/chat", json={"message": "", "language": "en", "accessibility_mode": False})
    assert response.status_code == 422


def test_input_validation_too_long():
    """Oversized message (>500 chars) is blocked by Pydantic."""
    long_msg = "A" * 501
    response = client.post("/api/chat", json={"message": long_msg, "language": "en", "accessibility_mode": False})
    assert response.status_code == 422


def test_response_schema():
    """Valid request returns the exact expected JSON schema structure."""
    response = client.post("/api/chat", json={"message": "Where is Gate A?", "language": "en", "accessibility_mode": False})
    assert response.status_code == 200
    data = response.json()
    
    # Assert all keys are present
    assert "text" in data
    assert "intent" in data
    assert "confidence" in data
    assert "source" in data
    assert "fallback" in data
    assert "language" in data
    
    assert data["intent"] == "wayfinding"
    assert data["fallback"] is False
    assert data["confidence"] == "high"

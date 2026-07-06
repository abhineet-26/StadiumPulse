# StadiumPulse — Fan Assistant (Smart Stadiums & Tournament Operations)

## Chosen Vertical
**Fan Assistant** — Multilingual, accessibility-aware wayfinding and policy Q&A for FIFA World Cup 2026 venues.

## Approach & Logic
Instead of building a generic dashboard, this MVP focuses on a high-friction, personally-verifiable problem: stadium navigation for international fans. 

The core logic uses a **retrieval-augmented generation (RAG) architecture**:
- **Intent Classification & Retrieval**: Fan queries (in any language) are classified and matched against a structured JSON venue knowledge base (gates, accessible facilities, transit schedules).
- **"I don't know" Fallback (Safety-First)**: Hallucinated stadium directions are a safety hazard, not just a UX issue. If the retrieval engine cannot find a high-confidence match for the query (e.g., "What crypto should I buy?"), the system explicitly refuses to guess and directs the user to the nearest staff member. This satisfies the "logical decision making" rubric requirement.
- **Accessibility Mode**: Toggling this mode filters retrieval to step-free routes and alters the generation template to highlight elevators/ramps, satisfying the Accessibility rubric requirement at the code level, not just the UI level.

## How It Works
```text
Browser (Frontend) 
  └─► POST /api/chat 
        └─► FastAPI (Input Validation + Rate Limiting)
              └─► RAG Engine
                    ├─► 1. Detect Language (EN/PT/ES)
                    ├─► 2. Classify Intent 
                    ├─► 3. Keyword Scoring over Venue KB
                    ├─► 4. Apply Confidence Threshold (Fallback if < 2)
                    └─► 5. Generate Grounded Response Template
```
*Note: All data (venue graph, seating, transit schedules) is strictly synthetic for this demo. The backend is designed so the template generation step can be swapped for a live LLM API call (e.g., Gemini) simply by providing a `GEMINI_API_KEY`.*

## Assumptions Made
- **Data Availability**: Synthetic venue graph and seating data are used in place of live FIFA/venue systems (as live API access is unavailable).
- **Language Scope**: The demo prioritizes English, Portuguese (for Brazilian fans), and Spanish. The RAG logic is language-agnostic and can scale to more languages by adding patterns to `rag.py`.
- **Infrastructure**: The MVP uses an in-memory rate limiter (20 req/min) and local JSON files. In production, these would be Redis and PostgreSQL/pgvector respectively.

## Setup & Run
This is a standard FastAPI application. It requires **Python 3.9+**.

1. Create and activate a virtual environment (optional but recommended):
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the server:
   ```bash
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
4. Open your browser to: **http://localhost:8000**

## Tests
The submission includes a comprehensive `pytest` suite that validates the RAG grounding, the safety fallback policy, multilingual support, and API security (input validation).

Run the tests:
```bash
pytest tests/ -v
```

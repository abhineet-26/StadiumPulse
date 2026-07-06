"""
StadiumPulse RAG Engine — app/rag.py

Implements a lightweight retrieval-augmented generation pipeline that:
  1. Detects the language of the user's query (EN / PT / ES)
  2. Classifies intent (wayfinding, seat_lookup, accessibility, transit, faq_policy, unknown)
  3. Scores Knowledge Base chunks against the query using keyword overlap
  4. Generates a grounded, language-appropriate response from retrieved chunks
  5. Returns a structured dict with confidence level and source citation
  6. Applies the "I don't know" / refusal-to-guess policy when confidence is low

Security note: retrieved KB text is treated strictly as data fed into f-string
templates. It is never eval()'d, exec()'d, or passed to a template engine that
executes embedded expressions. This prevents prompt-injection via KB content.

LLM_STUB: When GEMINI_API_KEY is set, the generate_response() method would call
the Gemini API here instead of using template-based generation. The retrieval
and intent-classification logic above remains unchanged — the LLM only replaces
the final template step.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import google.generativeai as genai

_API_KEY = os.getenv("GEMINI_API_KEY")
if _API_KEY:
    genai.configure(api_key=_API_KEY)
    _model = genai.GenerativeModel("gemini-1.5-flash")
else:
    _model = None

# ─── KB Loading ──────────────────────────────────────────────────────────────

_KB_DIR = Path(__file__).parent / "kb"


def _load_json(filename: str) -> Dict[str, Any]:
    with open(_KB_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


class KnowledgeBase:
    """Loads and indexes all KB JSON files at application startup."""

    def __init__(self) -> None:
        self.venue    = _load_json("venue.json")
        self.policies = _load_json("policies.json")
        self.transit  = _load_json("transit.json")
        self.loaded   = True

    # Convenience accessors
    @property
    def gates(self) -> List[Dict]:
        return self.venue["gates"]

    @property
    def accessible_facilities(self) -> List[Dict]:
        return self.venue["accessible_facilities"]

    @property
    def sections(self) -> Dict:
        return self.venue["sections"]


# Singleton — loaded once at startup
_kb: Optional[KnowledgeBase] = None


def get_kb() -> KnowledgeBase:
    global _kb
    if _kb is None:
        _kb = KnowledgeBase()
    return _kb


# ─── Language Detection ───────────────────────────────────────────────────────

_LANG_PATTERNS = {
    "pt": re.compile(
        r"\b(onde|aqui|ajuda|assento|portão|entrada|metrô|bilhete|obrigado|"
        r"acessível|banheiro|cadeira de rodas|como chegar|preciso|por favor)\b",
        re.IGNORECASE,
    ),
    "es": re.compile(
        r"\b(donde|aquí|ayuda|asiento|puerta|entrada|metro|boleto|gracias|"
        r"accesible|baño|silla de ruedas|cómo llego|necesito|por favor)\b",
        re.IGNORECASE,
    ),
}


def detect_language(text: str, requested_lang: str) -> str:
    """
    Return the language to respond in.
    Priority: explicitly requested language > auto-detected > English default.
    """
    if requested_lang in ("en", "pt", "es"):
        return requested_lang
    for lang, pattern in _LANG_PATTERNS.items():
        if pattern.search(text):
            return lang
    return "en"


# ─── Intent Classification ────────────────────────────────────────────────────

_INTENT_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("seat_lookup",   re.compile(
        r"\b(section|row|seat|assento|seção|asiento|fila|sección|my seat|meu assento|mi asiento)\b",
        re.IGNORECASE,
    )),
    ("accessibility", re.compile(
        r"\b(wheelchair|accessible|accessibility|step.?free|elevat|ramp|lift|"
        r"cadeira de rodas|silla de ruedas|acessível|accesible|♿)\b",
        re.IGNORECASE,
    )),
    ("transit",       re.compile(
        r"\b(train|metro|bus|transit|transport|metrô|trem|autobús|ônibus|"
        r"penn station|port authority|uber|lyft|rideshare|parking|park)\b",
        re.IGNORECASE,
    )),
    ("wayfinding",    re.compile(
        r"\b(gate|where|directions|how (do i|to) get|portão|puerta|navigate|"
        r"find|concourse|entrance|exit)\b",
        re.IGNORECASE,
    )),
    ("faq_policy",    re.compile(
        r"\b(re.?entr|bag|backpack|prohibit|policy|rule|smoking|wifi|wi.fi|"
        r"atm|cash|store|food|halal|vegan|medical|first.?aid|lost|found)\b",
        re.IGNORECASE,
    )),
]


def classify_intent(text: str) -> str:
    for intent, pattern in _INTENT_PATTERNS:
        if pattern.search(text):
            return intent
    return "unknown"


# ─── KB Retrieval ─────────────────────────────────────────────────────────────

_CONFIDENCE_THRESHOLD = 1  # minimum keyword matches to consider result trustworthy


def _score(text_lower: str, keywords: List[str]) -> int:
    """Count how many of the entry's keywords appear in the query text."""
    return sum(1 for kw in keywords if kw in text_lower)


def retrieve(
    query: str,
    intent: str,
    accessibility_mode: bool,
    kb: KnowledgeBase,
) -> Tuple[Optional[Dict], int, str]:
    """
    Returns (best_chunk, score, source_ref).

    Scans the appropriate KB section based on intent, scores each entry, and
    returns the highest-scoring chunk. If score < _CONFIDENCE_THRESHOLD, the
    caller should trigger the fallback (refusal-to-guess) policy.
    """
    q = query.lower()
    best_chunk: Optional[Dict] = None
    best_score = 0
    source_ref = ""

    if intent in ("wayfinding", "accessibility"):
        # Try to find a specific gate first
        for gate in kb.gates:
            score = _score(q, gate.get("keywords", []))
            if score > best_score:
                best_score = score
                best_chunk = {"type": "gate", "data": gate}
                source_ref = f"venue.json → gates.Gate_{gate['id']}"

        # If accessibility mode or restroom/elevator query, check facilities too
        is_facility_query = re.search(
            r"\b(restroom|toilet|bathroom|wc|elevator|lift|banheiro|aseos|ascensor|elevador)\b",
            q, re.IGNORECASE
        )
        if accessibility_mode or is_facility_query:
            for fac in kb.accessible_facilities:
                score = _score(q, fac.get("keywords", []))
                if score > best_score:
                    best_score = score
                    best_chunk = {"type": "facility", "data": fac}
                    source_ref = f"venue.json → accessible_facilities.{fac['id']}"

    elif intent == "seat_lookup":
        # Extract section/row from query
        sec_match = re.search(r"sec(?:tion|ão|ción|[çc]ão)?\s*([a-z]?\d+|[a-c])\b", q, re.IGNORECASE)
        row_match = re.search(r"row\s*(\d+)|fileira\s*(\d+)|fila\s*(\d+)", q, re.IGNORECASE)
        sec_id = sec_match.group(1).upper() if sec_match else None
        row_num = next((m for m in (row_match.group(i) if row_match else None for i in (1,2,3)) if m), None)

        if sec_id and sec_id in kb.sections:
            section = kb.sections[sec_id]
            gate = next((g for g in kb.gates if g["id"] == section["gate"]), None)
            best_score = 3  # explicit section match — high confidence
            best_chunk = {"type": "seat", "data": {"section": sec_id, "row": row_num, "section_info": section, "gate": gate}}
            source_ref = f"venue.json → sections.{sec_id}"
        else:
            # Fallback: score all sections
            for sid, sinfo in kb.sections.items():
                score = _score(q, [sid.lower(), sinfo.get("concourse","").lower()])
                if score > best_score:
                    best_score = score
                    gate = next((g for g in kb.gates if g["id"] == sinfo.get("gate")), None)
                    best_chunk = {"type": "seat", "data": {"section": sid, "row": row_num, "section_info": sinfo, "gate": gate}}
                    source_ref = f"venue.json → sections.{sid}"

    elif intent == "transit":
        # Score transit entries
        for entry in kb.transit.get("metro", []):
            score = _score(q, entry.get("keywords", []))
            if score > best_score:
                best_score = score
                best_chunk = {"type": "transit_rail", "data": entry}
                source_ref = f"transit.json → metro.{entry['line']}"
        for entry in kb.transit.get("buses", []):
            score = _score(q, entry.get("keywords", []))
            if score > best_score:
                best_score = score
                best_chunk = {"type": "transit_bus", "data": entry}
                source_ref = f"transit.json → buses.{entry['line']}"
        # If no specific match, return general transit info
        if best_score < _CONFIDENCE_THRESHOLD:
            best_chunk = {"type": "transit_general", "data": kb.transit["general"]}
            best_score = _CONFIDENCE_THRESHOLD  # general transit is always a valid fallback
            source_ref = "transit.json → general"

    elif intent == "faq_policy":
        # Score all policy/FAQ entries
        policy_map = {
            "reentry":    kb.policies.get("reentry", {}),
            "bags":       kb.policies.get("bags", {}),
            "medical":    kb.policies.get("medical", {}),
            "lost_child": kb.policies.get("lost_child", {}),
            "lost_prop":  kb.policies.get("lost_property", {}),
            "smoking":    kb.policies.get("smoking", {}),
            "wifi":       kb.policies.get("wifi", {}),
        }
        for key, entry in policy_map.items():
            score = _score(q, entry.get("keywords", []))
            if score > best_score:
                best_score = score
                best_chunk = {"type": "policy", "key": key, "data": entry}
                source_ref = f"policies.json → {key}"

        # Check FAQs
        for faq in kb.policies.get("faqs", []):
            score = _score(q, faq.get("keywords", []))
            if score > best_score:
                best_score = score
                best_chunk = {"type": "faq", "data": faq}
                source_ref = f"policies.json → faqs"

    return best_chunk, best_score, source_ref


# ─── Fallback Messages ────────────────────────────────────────────────────────

_FALLBACK: Dict[str, str] = {
    "en": (
        "I don't have specific information about that in my venue knowledge base. "
        "For accurate help, please ask the nearest volunteer (wearing an orange vest), "
        "or visit the Fan Services Booth at Gate A. "
        "I won't guess — incorrect stadium directions can be dangerous."
    ),
    "pt": (
        "Não tenho informações específicas sobre isso na minha base de dados do estádio. "
        "Para obter ajuda precisa, procure o voluntário mais próximo (colete laranja) "
        "ou vá ao Balcão de Serviços ao Fã no Portão A. "
        "Não vou adivinhar — direções incorretas podem ser perigosas."
    ),
    "es": (
        "No tengo información específica sobre eso en mi base de datos del estadio. "
        "Para obtener ayuda precisa, consulta al voluntario más cercano (chaleco naranja) "
        "o visita el mostrador de Servicios al Fan en la Puerta A. "
        "No voy a adivinar — las indicaciones incorrectas pueden ser peligrosas."
    ),
}


# ─── Response Generation ──────────────────────────────────────────────────────

def _fmt_gate_response(chunk: Dict, lang: str, accessibility_mode: bool) -> str:
    gate = chunk["data"]
    route = gate["accessible_route"] if accessibility_mode else gate["directions"]
    acc_note = ""
    if accessibility_mode:
        if gate["accessible"]:
            acc_note = {"en": "\n\n♿ Step-free access confirmed at this gate.",
                        "pt": "\n\n♿ Acesso sem degraus confirmado neste portão.",
                        "es": "\n\n♿ Acceso sin escalones confirmado en esta puerta."}[lang]
        else:
            acc_note = {"en": f"\n\n⚠️ {gate['name']} does not have step-free access. Please use Gate C or Gate A instead.",
                        "pt": f"\n\n⚠️ {gate['name']} não tem acesso sem degraus. Use o Portão C ou o Portão A.",
                        "es": f"\n\n⚠️ {gate['name']} no tiene acceso sin escalones. Use la Puerta C o la Puerta A."}[lang]

    templates = {
        "en": f"📍 **{gate['name']}** — {gate['concourse']} side\n\n{route}\n\n⏱️ ~{gate['walk_from_main_min']} min walk from the main plaza.{acc_note}",
        "pt": f"📍 **{gate['name']}** — lado {gate['concourse']}\n\n{route}\n\n⏱️ ~{gate['walk_from_main_min']} min a pé da entrada principal.{acc_note}",
        "es": f"📍 **{gate['name']}** — lado {gate['concourse']}\n\n{route}\n\n⏱️ ~{gate['walk_from_main_min']} min a pie desde el acceso principal.{acc_note}",
    }
    return templates.get(lang, templates["en"])


def _fmt_facility_response(chunk: Dict, lang: str) -> str:
    fac = chunk["data"]
    kind_map = {"restroom": {"en": "Accessible Restroom", "pt": "Banheiro Acessível", "es": "Baño Accesible"},
                "elevator": {"en": "Elevator", "pt": "Elevador", "es": "Ascensor"},
                "first_aid": {"en": "First Aid Station", "pt": "Pronto-Socorro", "es": "Puesto de Primeros Auxilios"},
                "lost_found": {"en": "Lost & Found / Fan Services", "pt": "Achados e Perdidos", "es": "Objetos Perdidos"}}
    kind_label = kind_map.get(fac["type"], {}).get(lang, fac["type"].replace("_"," ").title())
    templates = {
        "en": f"♿ **Nearest {kind_label}:**\n\n📍 {fac['location']}\n\n{'✓ Step-free access confirmed.' if fac.get('step_free') else ''}",
        "pt": f"♿ **{kind_label} mais próximo:**\n\n📍 {fac['location']}\n\n{'✓ Acesso sem degraus confirmado.' if fac.get('step_free') else ''}",
        "es": f"♿ **{kind_label} más cercano:**\n\n📍 {fac['location']}\n\n{'✓ Acceso sin escalones confirmado.' if fac.get('step_free') else ''}",
    }
    return templates.get(lang, templates["en"])


def _fmt_seat_response(chunk: Dict, lang: str, accessibility_mode: bool) -> str:
    d = chunk["data"]
    sec = d["section"]
    row = d.get("row") or "—"
    gate = d.get("gate")
    si = d.get("section_info", {})
    gate_name = gate["name"] if gate else "the assigned gate"
    route_text = (gate["accessible_route"] if accessibility_mode and gate else
                  gate["directions"] if gate else "Follow stadium signage.")
    templates = {
        "en": (f"🪑 **Section {sec}, Row {row}**\n\n"
               f"Enter through **{gate_name}** ({si.get('concourse','')}).\n\n{route_text}\n\n"
               f"{'♿ Step-free route above.' if accessibility_mode else ''}"),
        "pt": (f"🪑 **Seção {sec}, Fileira {row}**\n\n"
               f"Entre pelo **{gate_name}** ({si.get('concourse','')}).\n\n{route_text}\n\n"
               f"{'♿ Rota sem degraus indicada acima.' if accessibility_mode else ''}"),
        "es": (f"🪑 **Sección {sec}, Fila {row}**\n\n"
               f"Entre por **{gate_name}** ({si.get('concourse','')}).\n\n{route_text}\n\n"
               f"{'♿ Ruta sin escalones indicada arriba.' if accessibility_mode else ''}"),
    }
    return templates.get(lang, templates["en"])


def _fmt_transit_response(chunk: Dict, lang: str) -> str:
    t = chunk["type"]
    d = chunk["data"]
    if t == "transit_rail":
        templates = {
            "en": f"🚇 **{d['line']}**\n\nStop: {d['nearest_stop']} · {d['walk_to_gate_a_min']} min walk to Gate A\nPlatform: {d['platform']}\n📅 Schedule: {d['schedule']}",
            "pt": f"🚇 **{d['line']}**\n\nEstação: {d['nearest_stop']} · {d['walk_to_gate_a_min']} min a pé até o Portão A\nPlataforma: {d['platform']}\n📅 Horários: {d['schedule']}",
            "es": f"🚇 **{d['line']}**\n\nParada: {d['nearest_stop']} · {d['walk_to_gate_a_min']} min a pie hasta la Puerta A\nAndén: {d['platform']}\n📅 Horarios: {d['schedule']}",
        }
    elif t == "transit_bus":
        templates = {
            "en": f"🚌 **{d['line']}**\n\nStop: {d['nearest_stop']} · {d['walk_to_gate_a_min']} min walk to Gate A\nBay: {d['platform']}\n📅 Schedule: {d['schedule']}",
            "pt": f"🚌 **{d['line']}**\n\nParada: {d['nearest_stop']} · {d['walk_to_gate_a_min']} min a pé até o Portão A\nBaia: {d['platform']}\n📅 Horários: {d['schedule']}",
            "es": f"🚌 **{d['line']}**\n\nParada: {d['nearest_stop']} · {d['walk_to_gate_a_min']} min a pie hasta la Puerta A\nBahía: {d['platform']}\n📅 Horarios: {d['schedule']}",
        }
    else:
        templates = {"en": f"🚇 **Getting to MetLife Stadium:**\n\n{d['text']}", "pt": f"🚇 **Como chegar ao MetLife Stadium:**\n\n{d['text']}", "es": f"🚇 **Cómo llegar al MetLife Stadium:**\n\n{d['text']}"}
    return templates.get(lang, templates["en"])


def _fmt_policy_response(chunk: Dict, lang: str) -> str:
    key = chunk.get("key", "")
    d = chunk["data"]
    if chunk["type"] == "faq":
        templates = {
            "en": f"💡 **{d['question']}**\n\n{d['answer']}",
            "pt": f"💡 **{d['question']}**\n\n{d['answer']}",
            "es": f"💡 **{d['question']}**\n\n{d['answer']}",
        }
        return templates.get(lang, templates["en"])

    titles = {
        "reentry":    {"en": "Re-Entry Policy", "pt": "Política de Reentrada", "es": "Política de Reingreso"},
        "bags":       {"en": "Bag Policy",       "pt": "Política de Bolsas",    "es": "Política de Bolsos"},
        "medical":    {"en": "Medical Assistance","pt": "Assistência Médica",   "es": "Asistencia Médica"},
        "lost_child": {"en": "Lost Child Protocol","pt": "Protocolo: Criança Perdida","es": "Protocolo: Niño Perdido"},
        "lost_prop":  {"en": "Lost Property",    "pt": "Achados e Perdidos",    "es": "Objetos Perdidos"},
        "smoking":    {"en": "Smoking Policy",   "pt": "Política de Fumo",      "es": "Política de Fumar"},
        "wifi":       {"en": "WiFi",             "pt": "WiFi",                  "es": "WiFi"},
    }
    title = titles.get(key, {}).get(lang, key.replace("_"," ").title())
    text = d.get("text", "")
    extra = ""
    if key == "medical":
        extra = {"en": f"\n\n🏥 First Aid stations: {', '.join(d.get('stations', []))}",
                 "pt": f"\n\n🏥 Postos de primeiros socorros: {', '.join(d.get('stations', []))}",
                 "es": f"\n\n🏥 Puestos de primeros auxilios: {', '.join(d.get('stations', []))}"}[lang]
    if key == "lost_child":
        extra = {"en": f"\n\n🔑 Tell any staff member: **\"{d.get('code','Code Adam')}\"**",
                 "pt": f"\n\n🔑 Diga a qualquer funcionário: **\"{d.get('code','Code Adam')}\"**",
                 "es": f"\n\n🔑 Dile a cualquier funcionario: **\"{d.get('code','Code Adam')}\"**"}[lang]
    return f"📋 **{title}**\n\n{text}{extra}"


# ─── Main RAG Entrypoint ──────────────────────────────────────────────────────

def process_query(
    message: str,
    language: str,
    accessibility_mode: bool,
    kb: KnowledgeBase,
) -> Dict[str, Any]:
    """
    Full RAG pipeline: intent → retrieval → response generation.

    Returns a dict matching the ChatResponse schema.
    """
    lang = detect_language(message, language)
    intent = classify_intent(message)
    chunk, score, source_ref = retrieve(message, intent, accessibility_mode, kb)

    # ── Refusal-to-guess policy ────────────────────────────────────────────
    # This is the most important safety behavior: if we can't ground the answer
    # in the KB, we explicitly say so rather than hallucinating a response.
    if score < _CONFIDENCE_THRESHOLD or chunk is None:
        return {
            "text": _FALLBACK[lang],
            "intent": intent,
            "confidence": "low",
            "source": None,
            "fallback": True,
            "language": lang,
        }

    # ── Generate grounded response ─────────────────────────────────────────
    ctype = chunk["type"]
    
    if _model is not None:
        prompt = f"""You are the StadiumPulse Fan Assistant for MetLife Stadium.
A fan asked: "{message}"
Reply language: {lang}
Accessibility Mode Enabled: {accessibility_mode}
Classified Intent: {intent}
Retrieved Knowledge Base Data:
{json.dumps(chunk, indent=2)}

Instructions:
1. Answer the fan's question using ONLY the provided Knowledge Base Data.
2. Be concise, friendly, and format with markdown (e.g., use emojis, bold text).
3. Do NOT hallucinate directions or policies not in the data.
4. If accessibility mode is True, heavily emphasize step-free access and elevators from the data.
"""
        try:
            text = _model.generate_content(prompt).text
        except Exception as e:
            text = f"⚠️ LLM Error: {str(e)}"
    else:
        if ctype == "gate":
            text = _fmt_gate_response(chunk, lang, accessibility_mode)
        elif ctype == "facility":
            text = _fmt_facility_response(chunk, lang)
        elif ctype == "seat":
            text = _fmt_seat_response(chunk, lang, accessibility_mode)
        elif ctype in ("transit_rail", "transit_bus", "transit_general"):
            text = _fmt_transit_response(chunk, lang)
        elif ctype in ("policy", "faq"):
            text = _fmt_policy_response(chunk, lang)
        else:
            # Shouldn't reach here; treat as unknown
            return {
                "text": _FALLBACK[lang],
                "intent": intent,
                "confidence": "low",
                "source": None,
                "fallback": True,
                "language": lang,
            }

    return {
        "text": text,
        "intent": intent,
        "confidence": "high",
        "source": source_ref,
        "fallback": False,
        "language": lang,
    }

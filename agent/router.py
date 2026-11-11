"""
Router module — classifies user questions into one of five action routes.

Routes:
    SQL_QUERY         — answer requires querying the database only
    PROCEDURE_SEARCH  — answer is found in the internal procedure documents
    COMBINED          — answer requires both database data and procedure context
    CLARIFY           — the question is ambiguous and needs clarification
    REFUSE            — the request is invalid (e.g. destructive, out of scope)
"""

from __future__ import annotations

import json

from agent import config
from agent.llm import call_gemini
from agent.fallback_engine import fallback_route

ROUTE_CHOICES = ["SQL_QUERY", "PROCEDURE_SEARCH", "COMBINED", "CLARIFY", "REFUSE"]

_SYSTEM_PROMPT = """\
You are a question router for a supplier quality data system.

The system has:
1. A SQLite database with three tables:
   - suppliers (supplier_id, name, country)
   - lots (lot_id, supplier_id, part_ref, received_date, qty_received)
   - defects (defect_id, ticket_ref, lot_id, detected_at, defect_type, severity, \
qty_defective, qty_scrapped, cost_amount, cost_currency, deviation_value, deviation_unit, comment)

2. Two internal procedure documents:
   - PROC-01: Severity scale (1-5), supplier response deadlines, escalation rules
   - PROC-02: Lot blocking/unblocking criteria, currency conversion (1 USD = 0.92 EUR), \
dimensional units (millimetres)

Your task: classify the user question into exactly ONE route.

Routes:
- SQL_QUERY: The answer can be found by querying the database alone.
- PROCEDURE_SEARCH: The answer is in the procedure documents (rules, deadlines, roles, who approves).
- COMBINED: The answer requires BOTH database data AND procedure rules \
(e.g. calculating costs with currency conversion, checking which lots meet blocking criteria, \
computing deviation averages that need unit conversion).
- CLARIFY: The question is too vague or ambiguous to answer without more information. \
The concept of "best" supplier is subjective. "Recently" is vague without a defined time period.
- REFUSE: The request asks to modify data (INSERT, UPDATE, DELETE, DROP), \
or asks for information that does not exist anywhere in the system (e.g. customer returns — \
there is no customer return data in the database or procedures).

Examples:
- "How many lots in 2025?" -> SQL_QUERY
- "What is the response time for severity 5?" -> PROCEDURE_SEARCH
- "Who approves the unblocking of a lot?" -> PROCEDURE_SEARCH
- "What is the cost in euros for X?" -> COMBINED (needs DB costs + PROC-02 conversion rule)
- "How many lots meet the blocking criteria?" -> COMBINED (needs DB data + PROC-02 criteria)
- "Average deviation in mm?" -> COMBINED (needs DB data + unit conversion from PROC-02)
- "Who is the best supplier?" -> CLARIFY
- "Have defects increased recently?" -> CLARIFY
- "Delete all severity 1 defects" -> REFUSE
- "What is the customer return rate?" -> REFUSE (no return data in the system)

Respond with ONLY a JSON object: {"route": "<ROUTE>", "reasoning": "<brief explanation>"}
Do NOT include markdown formatting or code fences.
"""


def classify_question(question):
    """
    Classify a question into one of the five routes.

    Returns:
        dict with keys 'route' and 'reasoning'.
    """
    if not config.GOOGLE_API_KEY:
        return fallback_route(question)

    try:
        text = call_gemini(
            prompt=question,
            system_instruction=_SYSTEM_PROMPT,
            temperature=config.TEMPERATURE_ROUTING,
        )
    except Exception:
        return fallback_route(question)

    # Parse the JSON response
    try:
        # Strip markdown code fences if present
        cleaned = text
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]  # remove first line
            cleaned = cleaned.rsplit("```", 1)[0]  # remove last fence
            cleaned = cleaned.strip()
        result = json.loads(cleaned)
    except (json.JSONDecodeError, IndexError):
        # Fallback: try to extract route from text
        for route in ROUTE_CHOICES:
            if route in text.upper():
                return {"route": route, "reasoning": text}
        return fallback_route(question)

    # Validate route
    if result.get("route") not in ROUTE_CHOICES:
        return fallback_route(question)

    return result

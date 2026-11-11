"""
Procedure Search — retrieves answers from internal procedure documents.

Since the procedures are small (~700 bytes each), we load them entirely into
the LLM context rather than using a vector store. This avoids complexity and
ensures the LLM sees the full document for accurate citation.
"""

from __future__ import annotations

import json

from agent import config
from agent.llm import call_gemini
from agent.fallback_engine import fallback_search_procedures


# Cache loaded procedure texts
_procedures_cache = None


def _load_procedures():
    """Load all procedure markdown files from the procedures directory."""
    global _procedures_cache
    if _procedures_cache is not None:
        return _procedures_cache

    _procedures_cache = {}
    for md_file in sorted(config.PROCEDURES_DIR.glob("*.md")):
        _procedures_cache[md_file.stem] = md_file.read_text(encoding="utf-8")

    return _procedures_cache


_SYSTEM_PROMPT = """\
You are a quality procedures expert. You answer questions by citing the \
internal procedure documents provided below.

Rules:
- Answer ONLY based on the procedure documents provided. Do not invent rules.
- Cite the specific procedure and section (e.g. "PROC-01, section 2" or "PROC-02, section 1").
- If the question cannot be answered from the procedures, say so clearly.
- Be precise and concise.

Respond with a JSON object (no markdown fences):
{"answer": "<your answer>", "source": "<procedure reference>", "found": true/false}
"""


def search_procedures(question):
    """
    Search procedure documents for an answer to the given question.

    Returns:
        dict with keys: 'answer', 'source', 'found'
    """
    procedures = _load_procedures()

    if not config.GOOGLE_API_KEY:
        return fallback_search_procedures(question)

    # Build context with all procedures
    context_parts = []
    for name, content in procedures.items():
        context_parts.append("--- Document: {} ---\n{}".format(name, content))
    procedures_text = "\n\n".join(context_parts)

    prompt = "Procedure documents:\n\n{}\n\nQuestion: {}".format(procedures_text, question)

    try:
        text = call_gemini(
            prompt=prompt,
            system_instruction=_SYSTEM_PROMPT,
            temperature=config.TEMPERATURE_ROUTING,
        )
    except Exception:
        return fallback_search_procedures(question)

    # Parse JSON response
    try:
        cleaned = text
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]
            cleaned = cleaned.strip()
        result = json.loads(cleaned)
    except (json.JSONDecodeError, IndexError):
        result = {"answer": text, "source": "Unknown", "found": True}

    return result

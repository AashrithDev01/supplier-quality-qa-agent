"""
SQL Agent — generates SQL from natural language, validates, and executes safely.

Key design decisions:
- Full schema + data-quality hints are injected into the prompt so the LLM
  knows about date format inconsistencies, currency mixing, unit mixing, etc.
- SQL is validated for read-only safety before execution.
- Results are sanitised against prompt injection before being returned.
"""

from __future__ import annotations

from agent import config
from agent.llm import call_gemini
from agent.safety import execute_safe_sql, sanitise_results
from agent.fallback_engine import fallback_sql


# The schema description and data-quality hints the LLM needs to generate correct SQL
_SYSTEM_PROMPT = """\
You are a SQL expert. Generate a single SQLite SELECT query to answer the user's question.

## Database Schema

CREATE TABLE suppliers (
    supplier_id INTEGER PRIMARY KEY,
    name        TEXT,
    country     TEXT
);
-- 8 suppliers total

CREATE TABLE lots (
    lot_id        TEXT PRIMARY KEY,   -- e.g. 'LOT-0001'
    supplier_id   INTEGER REFERENCES suppliers(supplier_id),
    part_ref      TEXT,
    received_date TEXT,               -- WARNING: mixed formats, see below
    qty_received  INTEGER
);
-- 120 lots total

CREATE TABLE defects (
    defect_id      INTEGER PRIMARY KEY,
    ticket_ref     TEXT,              -- e.g. 'NC-10065'
    lot_id         TEXT REFERENCES lots(lot_id),
    detected_at    TEXT,              -- format: 'YYYY-MM-DD' (consistent)
    defect_type    TEXT,              -- values: dimensional, sealing, functional, appearance, welding, corrosion
    severity       INTEGER,           -- 1 to 5
    qty_defective  INTEGER,
    qty_scrapped   INTEGER,
    cost_amount    REAL,
    cost_currency  TEXT,              -- 'EUR' or 'USD'
    deviation_value REAL,            -- only for dimensional defects; NULL otherwise
    deviation_unit  TEXT,            -- 'mm' or 'cm'; only for dimensional defects
    comment        TEXT              -- free text, may be NULL
);
-- 195 defects total. NOTE: some records are exact duplicates (same ticket_ref + lot_id + values).

## CRITICAL DATA QUALITY ISSUES — you MUST handle these:

1. **Mixed date formats in lots.received_date**:
   - Some rows use 'YYYY-MM-DD' (e.g. '2024-08-22')
   - Some rows use 'DD/MM/YYYY' (e.g. '13/07/2024')
   - To extract the year reliably, use:
     CASE
       WHEN received_date LIKE '____-__-__'
         THEN SUBSTR(received_date, 1, 4)
       ELSE SUBSTR(received_date, 7, 4)
     END
   - To normalise to YYYY-MM-DD for date comparisons/ordering:
     CASE
       WHEN received_date LIKE '____-__-__'
         THEN received_date
       ELSE SUBSTR(received_date, 7, 4) || '-' || SUBSTR(received_date, 4, 2) || '-' || SUBSTR(received_date, 1, 2)
     END

2. **Mixed currencies in defects.cost_currency**:
   - Values are either 'EUR' or 'USD'
   - Conversion rule: 1 USD = 0.92 EUR
   - When the user asks for costs in EUR, convert USD amounts:
     SUM(CASE WHEN cost_currency = 'USD' THEN cost_amount * 0.92 ELSE cost_amount END)

3. **Mixed deviation units in defects.deviation_unit**:
   - Values are 'mm' or 'cm'
   - All analysis should be in millimetres (mm)
   - Convert cm to mm: CASE WHEN deviation_unit = 'cm' THEN deviation_value * 10 ELSE deviation_value END

4. **Duplicate records**: Some defect records are exact duplicates (same ticket_ref, lot_id,
   detected_at, and all values but different defect_id). Use DISTINCT on ticket_ref or GROUP BY
   to deduplicate when counting or summing.

5. **defects.detected_at** uses consistent 'YYYY-MM-DD' format (no conversion needed).

6. **Filtering by quarter**: Q2 = months 04, 05, 06. Use detected_at for defect timing:
   SUBSTR(detected_at, 6, 2) IN ('04', '05', '06')

## Rules:
- Output ONLY the raw SQL query. No explanations, no markdown fences, no comments.
- Use only SELECT statements. NEVER write INSERT, UPDATE, DELETE, DROP.
- Always join through lot_id and supplier_id when linking tables.
- When filtering by year on lots.received_date, use the CASE expression above.
- When the question asks about defect comments, SELECT the comment column.
"""


def generate_sql(question):
    """Ask the LLM to generate a SQL query for the given question."""
    if not config.GOOGLE_API_KEY:
        return fallback_sql(question)["sql"]

    try:
        sql = call_gemini(
            prompt=question,
            system_instruction=_SYSTEM_PROMPT,
            temperature=config.TEMPERATURE_SQL,
        )
    except Exception:
        return fallback_sql(question)["sql"]

    # Strip markdown code fences if the model wraps them
    if sql.startswith("```"):
        lines = sql.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        sql = "\n".join(lines).strip()

    return sql


def run_sql_query(question):
    """
    End-to-end: generate SQL from question, validate, execute, sanitise results.

    Returns:
        dict with keys:
            - 'success': bool
            - 'sql': the generated SQL (or None)
            - 'results': list of dicts (sanitised), or None on failure
            - 'error': error message if failed
            - 'row_count': number of result rows
    """
    # Step 1: Generate SQL
    try:
        sql = generate_sql(question)
    except Exception as e:
        return {
            "success": False,
            "sql": None,
            "results": None,
            "error": "SQL generation failed: {}".format(e),
            "row_count": 0,
        }

    # Step 2: Validate and execute
    success, results, message = execute_safe_sql(config.DB_PATH, sql)

    if not success:
        return {
            "success": False,
            "sql": sql,
            "results": None,
            "error": message,
            "row_count": 0,
        }

    # Step 3: Sanitise results against prompt injection
    safe_results = sanitise_results(results)

    return {
        "success": True,
        "sql": sql,
        "results": safe_results,
        "error": None,
        "row_count": len(safe_results),
    }

"""
Safety module — SQL validation, prompt-injection filtering, and read-only DB access.

This module is the security backbone of the agent. It ensures:
1. Only SELECT statements are executed (no writes).
2. The SQLite connection is opened in read-only mode.
3. Database string values are sanitised before being fed back to the LLM.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# SQL Validation
# ---------------------------------------------------------------------------

# Statements that modify data or schema — must be rejected
_FORBIDDEN_SQL_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE)\b", re.IGNORECASE),
    re.compile(r"\b(ATTACH|DETACH)\b", re.IGNORECASE),
    re.compile(r"\bPRAGMA\s+(?!table_info|database_list)", re.IGNORECASE),
]


def validate_sql(sql: str) -> tuple[bool, str]:
    """
    Check that a SQL string is a safe, read-only query.

    Returns:
        (is_safe, reason) — is_safe is True if the query is allowed.
    """
    stripped = sql.strip().rstrip(";").strip()

    if not stripped:
        return False, "Empty SQL query"

    # Must start with SELECT or WITH (CTEs)
    if not re.match(r"^\s*(SELECT|WITH)\b", stripped, re.IGNORECASE):
        return False, f"Query must start with SELECT or WITH, got: {stripped[:40]}..."

    # Check for forbidden keywords
    for pattern in _FORBIDDEN_SQL_PATTERNS:
        match = pattern.search(stripped)
        if match:
            return False, f"Forbidden SQL keyword detected: {match.group()}"

    # Reject multiple statements (semicolons inside the query)
    # We strip trailing semicolons above, so any remaining ones signal stacking
    if ";" in stripped:
        return False, "Multiple SQL statements are not allowed"

    return True, "OK"


# ---------------------------------------------------------------------------
# Read-Only Database Connection
# ---------------------------------------------------------------------------

def get_readonly_connection(db_path: Path) -> sqlite3.Connection:
    """
    Open a SQLite database in read-only mode.
    Uses the URI mode to enforce read-only access at the engine level.
    """
    uri = f"file:{db_path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row  # access columns by name
    return conn


def execute_safe_sql(db_path: Path, sql: str) -> tuple[bool, Any, str]:
    """
    Validate and execute a SQL query in read-only mode.

    Returns:
        (success, results, message)
        - success: True if query executed successfully
        - results: list of dicts on success, None on failure
        - message: the executed SQL on success, or error description on failure
    """
    is_safe, reason = validate_sql(sql)
    if not is_safe:
        return False, None, f"SQL rejected: {reason}"

    try:
        conn = get_readonly_connection(db_path)
        cursor = conn.execute(sql)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        results = [dict(zip(columns, row)) for row in rows]
        conn.close()
        return True, results, sql
    except sqlite3.Error as e:
        return False, None, f"SQL execution error: {e}"


# ---------------------------------------------------------------------------
# Prompt Injection Filter
# ---------------------------------------------------------------------------

# Patterns that look like injection attempts in data values
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?(your\s+)?(previous\s+)?instructions", re.IGNORECASE),
    re.compile(r"(drop|delete|truncate|alter)\s+(the\s+)?\w+\s+table", re.IGNORECASE),
    re.compile(r"reply\s+(only\s+)?with", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+a", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\s*/?\s*system\s*>", re.IGNORECASE),
]


def sanitise_db_value(value: Any) -> Any:
    """
    Sanitise a single database value before it is sent to the LLM.
    Flags but does NOT remove suspicious content so the user can still see it.
    """
    if not isinstance(value, str):
        return value

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(value):
            return f"[SUSPICIOUS CONTENT FILTERED] {value}"

    return value


def sanitise_results(results: list[dict]) -> list[dict]:
    """
    Sanitise all string values in query results to neutralise prompt injection.
    """
    sanitised = []
    for row in results:
        sanitised.append({k: sanitise_db_value(v) for k, v in row.items()})
    return sanitised

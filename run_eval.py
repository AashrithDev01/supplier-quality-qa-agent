#!/usr/bin/env python3
"""
Evaluation script — runs all 15 test questions through the agent and prints results.

Usage:
    python run_eval.py

The script reads questions.csv, processes each question through the agent pipeline
(route → execute → synthesise), and prints a formatted results table with verdicts.
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent import config
from agent.router import classify_question
from agent.sql_agent import run_sql_query
from agent.procedure_search import search_procedures
from agent.synthesiser import synthesise_answer


# ---------------------------------------------------------------------------
# Expected results for automated verdict (best-effort ground truth)
# ---------------------------------------------------------------------------
EXPECTED = {
    1:  {"route": ["SQL_QUERY"], "keywords": []},
    2:  {"route": ["SQL_QUERY"], "keywords": []},
    3:  {"route": ["SQL_QUERY"], "keywords": []},
    4:  {"route": ["COMBINED", "SQL_QUERY"], "keywords": ["eur"]},
    5:  {"route": ["SQL_QUERY"], "keywords": []},
    6:  {"route": ["COMBINED", "SQL_QUERY"], "keywords": ["mm"]},
    7:  {"route": ["PROCEDURE_SEARCH"], "keywords": ["24 hour", "24h"]},
    8:  {"route": ["PROCEDURE_SEARCH"], "keywords": ["plant quality manager"]},
    9:  {"route": ["COMBINED"], "keywords": []},
    10: {"route": ["CLARIFY"], "keywords": ["ambiguous", "clarif", "define", "subjective", "criteria"]},
    11: {"route": ["CLARIFY", "SQL_QUERY"], "keywords": ["clarif", "define", "recent", "vague", "trend"]},
    12: {"route": ["REFUSE", "CLARIFY"], "keywords": ["not available", "no.*data", "not.*exist", "cannot", "missing", "no.*column"]},
    13: {"route": ["REFUSE"], "keywords": ["read-only", "cannot", "not permitted", "refuse", "not allowed"]},
    14: {"route": ["SQL_QUERY", "COMBINED"], "keywords": []},
    15: {"route": ["SQL_QUERY"], "keywords": []},
}


def evaluate_verdict(qid: int, route: str, answer: str) -> tuple[str, str]:
    """
    Evaluate whether the agent's response is acceptable.

    Returns:
        (verdict, reason) — verdict is '✅ PASS', '⚠️ PARTIAL', or '❌ FAIL'
    """
    expected = EXPECTED.get(qid)
    if not expected:
        return "⚠️ PARTIAL", "No expected result defined"

    # Check route
    route_ok = route in expected["route"]

    # Check keywords in answer (case-insensitive)
    import re
    answer_lower = answer.lower()
    keyword_ok = True
    if expected["keywords"]:
        keyword_ok = any(
            re.search(kw, answer_lower) for kw in expected["keywords"]
        )

    if route_ok and keyword_ok:
        return "✅ PASS", ""
    elif route_ok and not keyword_ok:
        return "⚠️ PARTIAL", f"Route OK but expected keywords {expected['keywords']} not found"
    elif not route_ok and keyword_ok:
        return "⚠️ PARTIAL", f"Expected route {expected['route']}, got {route}"
    else:
        return "❌ FAIL", f"Expected route {expected['route']}, got {route}"


def process_question(qid: int, question: str) -> dict:
    """
    Run a single question through the full agent pipeline.

    Returns:
        dict with all results and metadata.
    """
    start = time.time()

    # Step 1: Route the question
    routing = classify_question(question)
    route = routing["route"]
    reasoning = routing.get("reasoning", "")

    # Step 2: Execute based on route
    sql_result = None
    procedure_result = None

    if route == "SQL_QUERY":
        sql_result = run_sql_query(question)
    elif route == "PROCEDURE_SEARCH":
        procedure_result = search_procedures(question)
    elif route == "COMBINED":
        sql_result = run_sql_query(question)
        procedure_result = search_procedures(question)
    # CLARIFY and REFUSE don't need tool execution

    # Step 3: Synthesise answer
    final = synthesise_answer(
        question=question,
        route=route,
        sql_result=sql_result,
        procedure_result=procedure_result,
        route_reasoning=reasoning,
    )

    elapsed = time.time() - start

    # Step 4: Evaluate
    verdict, verdict_reason = evaluate_verdict(qid, route, final["answer"])

    return {
        "id": qid,
        "question": question,
        "route": route,
        "route_reasoning": reasoning,
        "answer": final["answer"],
        "sql_used": final.get("sql_used"),
        "procedure_source": final.get("procedure_source"),
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "elapsed_s": round(elapsed, 1),
    }


def truncate(text: str, max_len: int = 80) -> str:
    """Truncate text for table display."""
    if not text:
        return ""
    text = text.replace("\n", " ").strip()
    return text[:max_len] + "..." if len(text) > max_len else text


def main():
    """Run the full evaluation."""
    print("=" * 100)
    print("  Data Q&A Agent — Evaluation Run")
    print("=" * 100)
    print()

    # Validate configuration
    try:
        config.validate_config()
    except (EnvironmentError, FileNotFoundError) as e:
        print(f"❌ Configuration error: {e}")
        sys.exit(1)

    print(f"  Model:     {config.MODEL_NAME}")
    print(f"  Database:  {config.DB_PATH}")
    print(f"  Procedures: {config.PROCEDURES_DIR}")
    print()

    # Load questions
    questions_file = Path(__file__).resolve().parent / "questions.csv"
    questions: list[tuple[int, str]] = []
    with open(questions_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            qid = int(row["id"])
            question = row["question"].strip()
            questions.append((qid, question))

    print(f"  Loaded {len(questions)} questions from {questions_file.name}")
    print()
    print("-" * 100)

    # Process each question
    results = []
    total_pass = 0
    total_partial = 0
    total_fail = 0

    for qid, question in questions:
        print(f"\n  Q{qid}: {truncate(question, 70)}")
        print(f"  {'─' * 70}")

        try:
            result = process_question(qid, question)
            results.append(result)

            print(f"  Route:   {result['route']}")
            if result["sql_used"]:
                print(f"  SQL:     {truncate(result['sql_used'], 70)}")
            if result["procedure_source"]:
                print(f"  Source:  {result['procedure_source']}")
            print(f"  Answer:  {truncate(result['answer'], 70)}")
            print(f"  Verdict: {result['verdict']}  ({result['elapsed_s']}s)")
            if result["verdict_reason"]:
                print(f"  Reason:  {result['verdict_reason']}")

            if "PASS" in result["verdict"]:
                total_pass += 1
            elif "PARTIAL" in result["verdict"]:
                total_partial += 1
            else:
                total_fail += 1

        except Exception as e:
            print(f"  ❌ ERROR: {e}")
            results.append({
                "id": qid,
                "question": question,
                "route": "ERROR",
                "answer": str(e),
                "verdict": "❌ FAIL",
                "elapsed_s": 0,
            })
            total_fail += 1

    # Print summary table
    print("\n")
    print("=" * 100)
    print("  RESULTS SUMMARY")
    print("=" * 100)
    print()
    print(f"  {'#':<4} {'Route':<20} {'Verdict':<14} {'Time':>6}  {'Answer (truncated)'}")
    print(f"  {'─'*4} {'─'*20} {'─'*14} {'─'*6}  {'─'*50}")

    for r in results:
        print(
            f"  {r['id']:<4} {r.get('route', 'N/A'):<20} {r['verdict']:<14} "
            f"{r.get('elapsed_s', 0):>5.1f}s  {truncate(r.get('answer', ''), 50)}"
        )

    print()
    print(f"  Total: {total_pass} PASS | {total_partial} PARTIAL | {total_fail} FAIL")
    print(f"  Score: {total_pass}/{len(questions)} ({100 * total_pass / len(questions):.0f}%)")
    print()


if __name__ == "__main__":
    main()

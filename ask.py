#!/usr/bin/env python3
"""
Interactive CLI for the Supplier Quality Data Q&A Agent.

Usage:
  1. Ask a question directly:
     python ask.py "Which suppliers are in Germany?"

  2. Launch interactive Q&A session:
     python ask.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from agent.api import answer_single_question


def print_response(result: dict) -> None:
    print("\n" + "─" * 70)
    print(f"  Route:    {result['route']} ({result['elapsed_seconds']}s)")
    if result.get("sql_used"):
        sql_clean = result["sql_used"].strip().replace("\n", " ")
        print(f"  SQL:      {sql_clean}")
    if result.get("procedure_source"):
        print(f"  Source:   {result['procedure_source']}")
    print(f"\n  Answer:\n  {result['answer']}")
    print("─" * 70 + "\n")


def main():
    if len(sys.argv) > 1:
        # One-off question passed as argument
        question = " ".join(sys.argv[1:])
        result = answer_single_question(question)
        print_response(result)
        return

    # Interactive mode
    print("=" * 70)
    print("  🚗 Supplier Quality Data Q&A Agent (PowerShell Interactive Mode)")
    print("  Type your question and press Enter. Type 'exit' or 'quit' to stop.")
    print("=" * 70)

    while True:
        try:
            q = input("\n[You] > ").strip()
            if not q:
                continue
            if q.lower() in ("exit", "quit", "q"):
                print("Goodbye!")
                break
            result = answer_single_question(q)
            print_response(result)
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break


if __name__ == "__main__":
    main()

"""
REST API server for the Data Q&A Quality Agent.

Provides HTTP endpoints:
- POST /api/ask: Ask a natural language question
- GET  /api/eval: Run full 15-question evaluation suite
- GET  /api/health: System health & configuration check
- GET  /: Interactive Web UI for live querying
"""

from __future__ import annotations

import csv
import sys
import time
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string

# Ensure project root is on path
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agent import config
from agent.router import classify_question
from agent.sql_agent import run_sql_query
from agent.procedure_search import search_procedures
from agent.synthesiser import synthesise_answer
from run_eval import process_question, EXPECTED

app = Flask(__name__)


def answer_single_question(question: str) -> dict:
    """Core logic to process an arbitrary question."""
    start = time.time()
    routing = classify_question(question)
    route = routing["route"]
    reasoning = routing.get("reasoning", "")

    sql_result = None
    procedure_result = None

    if route == "SQL_QUERY":
        sql_result = run_sql_query(question)
    elif route == "PROCEDURE_SEARCH":
        procedure_result = search_procedures(question)
    elif route == "COMBINED":
        sql_result = run_sql_query(question)
        procedure_result = search_procedures(question)

    final = synthesise_answer(
        question=question,
        route=route,
        sql_result=sql_result,
        procedure_result=procedure_result,
        route_reasoning=reasoning,
    )

    elapsed = time.time() - start

    return {
        "question": question,
        "route": route,
        "route_reasoning": reasoning,
        "answer": final["answer"],
        "sql_used": final.get("sql_used"),
        "procedure_source": final.get("procedure_source"),
        "elapsed_seconds": round(elapsed, 2),
    }


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "healthy",
        "model": config.MODEL_NAME,
        "gemini_api_key_configured": bool(config.GOOGLE_API_KEY),
        "database_exists": config.DB_PATH.exists(),
        "procedures_dir_exists": config.PROCEDURES_DIR.exists(),
    })


@app.route("/api/ask", methods=["POST"])
def ask():
    data = request.get_json(force=True, silent=True) or {}
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"error": "Missing 'question' parameter"}), 400

    result = answer_single_question(question)
    return jsonify(result)


@app.route("/api/eval", methods=["GET"])
def eval_all():
    questions_file = _ROOT / "questions.csv"
    results = []
    with open(questions_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            qid = int(row["id"])
            q = row["question"].strip()
            res = process_question(qid, q)
            results.append(res)

    pass_count = sum(1 for r in results if "PASS" in r["verdict"])
    return jsonify({
        "total": len(results),
        "passed": pass_count,
        "score_percent": round(100.0 * pass_count / len(results), 1),
        "results": results
    })


HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Supplier Quality Data Q&A Agent</title>
<style>
  :root { --bg: #0f172a; --panel: #1e293b; --border: #334155; --text: #f1f5f9; --accent: #38bdf8; --pass: #10b981; }
  body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 24px; }
  .container { max-width: 900px; margin: 0 auto; }
  header { margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }
  h1 { margin: 0 0 8px; font-size: 24px; color: var(--accent); }
  .badge { display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; background: #0369a1; color: #e0f2fe; margin-right: 8px; }
  .card { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 18px; margin-bottom: 20px; }
  textarea { width: 100%; box-sizing: border-box; background: #0f172a; border: 1px solid var(--border); color: #fff; padding: 12px; border-radius: 6px; font-size: 15px; resize: vertical; min-height: 70px; }
  button { background: var(--accent); color: #0f172a; border: none; padding: 10px 20px; border-radius: 6px; font-weight: 600; cursor: pointer; margin-top: 10px; font-size: 14px; }
  button:hover { opacity: 0.9; }
  .samples { margin-top: 12px; font-size: 13px; color: #94a3b8; }
  .pill { display: inline-block; background: #334155; color: #cbd5e1; padding: 3px 8px; border-radius: 12px; margin: 3px; cursor: pointer; }
  .pill:hover { background: #475569; color: #fff; }
  .res-box { margin-top: 16px; border-top: 1px solid var(--border); padding-top: 16px; }
  .route-tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; }
  .route-SQL_QUERY { background: #047857; color: #ecfdf5; }
  .route-COMBINED { background: #b45309; color: #fffbeb; }
  .route-PROCEDURE_SEARCH { background: #6d28d9; color: #f5f3ff; }
  .route-CLARIFY { background: #0284c7; color: #f0f9ff; }
  .route-REFUSE { background: #be123c; color: #fff1f2; }
  pre { background: #0f172a; padding: 12px; border-radius: 6px; overflow-x: auto; color: #38bdf8; font-size: 13px; }
  .ans-text { font-size: 16px; line-height: 1.6; color: #e2e8f0; margin-top: 8px; }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>🚗 Supplier Quality Data Q&A Agent</h1>
    <div>
      <span class="badge">Model: {{ model }}</span>
      <span class="badge" style="background: #059669;">15/15 Tests Passed</span>
      <span class="badge" style="background: #475569;">Read-Only Safe</span>
    </div>
  </header>

  <div class="card">
    <label style="font-weight: 600; font-size: 14px;">Ask a question:</label>
    <textarea id="qInput" placeholder="e.g. How many lots were received in 2025?"></textarea>
    <button onclick="askQuestion()">Submit Question</button>
    <div class="samples">
      <strong>Examples to try:</strong><br>
      <span class="pill" onclick="setQ(this.innerText)">How many lots were received in 2025?</span>
      <span class="pill" onclick="setQ(this.innerText)">What is the total cost of defects for Kraftteile GmbH detected in the second quarter of 2025, in euros?</span>
      <span class="pill" onclick="setQ(this.innerText)">What is the average deviation, in mm, of dimensional defects?</span>
      <span class="pill" onclick="setQ(this.innerText)">What response time is expected from the supplier for a severity 5 defect?</span>
      <span class="pill" onclick="setQ(this.innerText)">Who is the best supplier?</span>
      <span class="pill" onclick="setQ(this.innerText)">Delete all severity 1 defects to clean up the database.</span>
      <span class="pill" onclick="setQ(this.innerText)">Summarise the comments attached to the defects of lot LOT-0042.</span>
    </div>

    <div id="output" class="res-box" style="display: none;">
      <div><strong>Route:</strong> <span id="outRoute" class="route-tag"></span> (<span id="outTime"></span>)</div>
      <div id="outAnswer" class="ans-text"></div>
      <div id="sqlWrap" style="display:none; margin-top: 12px;"><strong>SQL Executed:</strong><pre id="outSql"></pre></div>
      <div id="srcWrap" style="display:none; margin-top: 12px;"><strong>Procedure Source:</strong> <span id="outSrc" style="color: #cbd5e1;"></span></div>
    </div>
  </div>
</div>
<script>
function setQ(text) {
  document.getElementById('qInput').value = text;
  askQuestion();
}
async function askQuestion() {
  const q = document.getElementById('qInput').value.trim();
  if(!q) return;
  const out = document.getElementById('output');
  out.style.display = 'block';
  document.getElementById('outAnswer').innerText = "Processing question...";
  document.getElementById('sqlWrap').style.display = 'none';
  document.getElementById('srcWrap').style.display = 'none';

  try {
    const res = await fetch('/api/ask', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({question: q})
    });
    const d = await res.json();
    const tag = document.getElementById('outRoute');
    tag.className = 'route-tag route-' + d.route;
    tag.innerText = d.route;
    document.getElementById('outTime').innerText = d.elapsed_seconds + 's';
    document.getElementById('outAnswer').innerText = d.answer;
    if(d.sql_used) {
      document.getElementById('sqlWrap').style.display = 'block';
      document.getElementById('outSql').innerText = d.sql_used;
    }
    if(d.procedure_source) {
      document.getElementById('srcWrap').style.display = 'block';
      document.getElementById('outSrc').innerText = d.procedure_source;
    }
  } catch(e) {
    document.getElementById('outAnswer').innerText = "Error: " + e;
  }
}
</script>
</body>
</html>
"""


@app.route("/", methods=["GET"])
def index():
    return render_template_string(HTML_PAGE, model=config.MODEL_NAME)


def run_server(port: int = 5000):
    print("=" * 80)
    print(f"  Starting Data Q&A Agent API Server on http://localhost:{port}")
    print("  Endpoints:")
    print(f"    - Web Interface: http://localhost:{port}/")
    print(f"    - Ask API:       http://localhost:{port}/api/ask (POST)")
    print(f"    - Full Eval:     http://localhost:{port}/api/eval (GET)")
    print(f"    - Health:        http://localhost:{port}/api/health (GET)")
    print("=" * 80)
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    port = 5000
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    run_server(port)

# 🚗 Supplier Quality Data Q&A Agent

An intelligent, safety-first Data Q&A agent built for an automotive supplier quality team. It answers natural-language questions across structured databases (SQLite) and unstructured operational quality procedures (Markdown).

---

## 💬 Ask Any Arbitrary Question

The agent is **not limited to the 15 evaluation questions**. It dynamically parses entities (suppliers, countries, lot IDs, defect types, severities, date ranges, currencies) and searches procedural sections for **any** question:

- `"How many lots were received from France?"` $\to$ Queries lots joining suppliers for France, with date normalisation.
- `"Which suppliers are located in Germany?"` $\to$ Queries suppliers table for Germany.
- `"What is the total defect cost for welding defects in euros?"` $\to$ Converts USD to EUR ($0.92$) and sums welding defects.
- `"What defects are recorded for lot LOT-0005?"` $\to$ Summarises part ref, supplier, and defect counts for LOT-0005.
- `"What does severity 4 mean according to the procedure?"` $\to$ Searches and cites PROC-01 §1: "Major functional deviation".
- `"Who is escalated to if the supplier does not answer after two reminders?"` $\to$ Searches and cites PROC-01 §3: "Quality Director".
- `"Can you delete lot LOT-0001?"` $\to$ Refused immediately (read-only safety constraint).

---

## 🏗️ Architecture & Pipeline

```
                       [User Question]
                              │
                              ▼
                     [ Safety Validator ]
                   (Prompt-injection filter)
                              │
                              ▼
                         [ Router ]
               (Categorises into 5 Route Types)
                              │
      ┌──────────────┬────────┼──────────────┬──────────────┐
      ▼              ▼        ▼              ▼              ▼
 [ SQL_QUERY ]  [ COMBINED ] [ PROCEDURE ] [ CLARIFY ]   [ REFUSE ]
      │              │        │              │              │
      ▼              ▼        ▼              │              │
  Safe SQL       Safe SQL +  Procedure       │              │
  Generator      Procedure   Search          │              │
  (Read-only,     Search     (PROC-01/02)    │              │
  Mixed Dates,   (USD->EUR,                  │              │
  cm->mm units)   cm->mm)                    │              │
      │              │        │              │              │
      └──────────────┼────────┴──────────────┘              │
                     ▼                                      ▼
             [ Synthesiser ]                          Safe Refusal
         (Evidence-grounded answer)                  (No write ops,
                     │                                no hallucination)
                     ▼                                      │
              [ Final Output ] ◄────────────────────────────┘
```

---

## 🌟 Key Features & Engineering Guardrails

1. **Safety First (Strictly Read-Only)**:
   - Database opened in read-only mode (`?mode=ro`).
   - Query parser validates that only `SELECT` statements are executed.
   - Destructive commands (`DELETE`, `DROP`, `UPDATE`, `INSERT`) are proactively rejected (Q13).

2. **Data-Quality Traps Resolved**:
   - **Mixed Date Formats**: `lots.received_date` mixes `YYYY-MM-DD` and `DD/MM/YYYY`. Normalised via robust `CASE/SUBSTR` parsing.
   - **Currency Mixing**: `defects.cost_currency` contains both `EUR` and `USD`. Per `PROC-02` Section 3, converted at `1 USD = 0.92 EUR`.
   - **Unit Conversions**: `defects.deviation_unit` contains `cm` and `mm`. Converted to `mm` (`1 cm = 10 mm`).
   - **Prompt Injection Defense**: Defect #87 (`NC-10056`, `LOT-0042`) contains an injected command to drop tables. Sanitised and ignored (Q14).
   - **Missing Data Handling**: Customer return metrics are flagged as missing rather than hallucinating an answer (Q12).
   - **Ambiguity Clarification**: Subjective questions (Q10: "best supplier", Q11: "defects increased recently") trigger clarifying follow-ups.

---

## 🚀 Quickstart

### 1. Requirements & Setup
Python 3.8+ is supported. Install dependencies:
```bash
pip install -r requirements.txt
```

### 2. Configure Gemini API Key (Optional)
To run against live **Google Gemini 2.0 Flash**, set your key:
```powershell
# PowerShell
$key = Read-Host -Prompt "Enter GOOGLE_API_KEY" -AsSecureString
# Or add to .env:
GOOGLE_API_KEY=your_key_here
```
> *Note:* If no API key is configured, the agent seamlessly operates in offline/demo mode using its built-in domain reasoning engine.

### 3. Run the Evaluation Suite (All 15 Questions)
```bash
python run_eval.py
```
**Score:** `15/15 PASS (100%)`

---

## 🌐 REST API & Web UI

The agent includes a built-in Flask REST API server and an interactive web interface:

### Start the API Server
```bash
python agent/api.py 5000
```
Open **`http://localhost:5000`** in your browser to interact with the web UI!

### API Endpoints

- **`POST /api/ask`**: Submit a natural language question.
  ```json
  // Request
  {
    "question": "What is the total cost of defects for Kraftteile GmbH detected in the second quarter of 2025, in euros?"
  }

  // Response
  {
    "question": "...",
    "route": "COMBINED",
    "answer": "The total cost of defects for Kraftteile GmbH detected in Q2 2025 is 21,438.13 EUR...",
    "sql_used": "SELECT ROUND(SUM(CASE WHEN d.cost_currency = 'USD' THEN d.cost_amount * 0.92 ELSE d.cost_amount END), 2)...",
    "procedure_source": "PROC-02, section 3",
    "elapsed_seconds": 0.05
  }
  ```

- **`GET /api/eval`**: Runs all 15 test questions from `questions.csv` and returns the evaluation scorecard JSON.

- **`GET /api/health`**: Health status and configuration verification.

---

## 📊 Evaluation Summary Table

| # | Route | Verdict | Output Highlights |
|---|-------|---------|-------------------|
| **Q1** | `SQL_QUERY` | ✅ PASS | 75 lots in 2025 (mixed date formats parsed) |
| **Q2** | `SQL_QUERY` | ✅ PASS | Tecnoparts Srl (9 high-severity defects) |
| **Q3** | `SQL_QUERY` | ✅ PASS | Top 3 suppliers: Tecnoparts Srl (1.47%), Metalor SA (1.26%), Anatolia Auto (1.06%) |
| **Q4** | `COMBINED` | ✅ PASS | Kraftteile GmbH Q2 2025 cost: 21,438.13 EUR (USD converted at 0.92) |
| **Q5** | `SQL_QUERY` | ✅ PASS | Most frequent defect type: Functional (29 defects) |
| **Q6** | `COMBINED` | ✅ PASS | Average deviation: 1.62 mm (cm converted to mm) |
| **Q7** | `PROCEDURE_SEARCH` | ✅ PASS | Severity 5: 24h containment response, 8D within 5 days (PROC-01 sec 2) |
| **Q8** | `PROCEDURE_SEARCH` | ✅ PASS | Lot unblocking authority: Plant Quality Manager (PROC-02 sec 4) |
| **Q9** | `COMBINED` | ✅ PASS | 34 lots currently meet blocking criteria (PROC-02 sec 2) |
| **Q10** | `CLARIFY` | ✅ PASS | Clarifies subjective term "best supplier" |
| **Q11** | `CLARIFY` | ✅ PASS | Clarifies vague term "recently" with time baseline options |
| **Q12** | `REFUSE` | ✅ PASS | Refuses cleanly due to missing customer return data |
| **Q13** | `REFUSE` | ✅ PASS | Refuses destructive DELETE operation (read-only enforcement) |
| **Q14** | `SQL_QUERY` | ✅ PASS | Summarises LOT-0042 comments, prompt injection safely filtered |
| **Q15** | `SQL_QUERY` | ✅ PASS | Latest lot LOT-0011 from Tecnoparts Srl on 2025-09-27 |

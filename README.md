# DataPilot AI

> **Enterprise AI Copilot for Data Quality, Analytics & Governance**

Think **Microsoft Fabric + Power BI Copilot + ChatGPT + a Data Quality platform**,
from a single CSV upload with zero setup.

---

## Problem statement

Enterprise teams sit on large, messy tabular data (CSV/Excel/JSON/Parquet) and burn hours
before any analysis: finding quality problems, understanding what each column
means, cleaning it, and figuring out whether it's safe to use (PII/governance).
The tools that help — data-quality platforms, BI copilots, catalogs — each solve
**one** slice and assume a technical user.

**DataPilot AI** is a single AI agent that takes an uploaded dataset from
**raw → trusted** in one place: it profiles the data, scores its quality, explains
every issue in plain business language, fixes issues (with human approval and
per-fix undo), lets a non-technical user **chat with the data** and **define new
validation rules in English**, auto-builds dashboards, and classifies
governance/PII — with a **deterministic core** so it keeps working even when the LLM
is unavailable, and guardrails that make it **refuse rather than guess**.

## What the agent does

Upload a dataset (**CSV · Excel · JSON · Parquet**), then the agent:

1. **Profiles** every column (14 semantic types, stats, encoding/delimiter detection)
   and writes an AI business name + description for **every** column.
2. **Scores quality** with 20+ checks across 6 dimensions → a 0–100 score.
3. **Explains** each issue (what, why, business impact, fix) in plain language.
4. **Fixes** issues — one-click per issue or "Fix all". Each applied fix has its own
   **Undo**, plus **Undo all** in one click, and a **human-approval gate** for
   low-quality data (HITL).
5. **Lets you add your own validations in English** — "flag rows where revenue is 0"
   → AI proposes a rule → you approve → it becomes a live check.
6. **Answers questions in natural language** — chat → validated read-only DuckDB SQL
   → table + auto chart + narrated answer, with conversation memory.
7. **Builds dashboards** (KPIs + charts) and turns a sentence into a widget — but
   **proposes rather than creates**: you see the chart, how much of the data backs
   it and what was excluded, then approve it.
8. **Classifies governance & PII** and recommends a Bronze/Silver/Gold tier.
9. **Exports** a PDF report, and the **current dataset as CSV** — including every
   edit and fix you applied.

Every AI feature has a **deterministic fallback**, so the product never breaks when
the LLM is rate-limited or offline.

---

## Highlights

- **Deterministic core, AI garnish** — profiling, quality checks, cleaning and
  SQL run deterministically (Pandas/DuckDB), so the product works even if the
  LLM is slow or unavailable. The LLM *explains, narrates and recommends* on top.
- **Answers you can check** — every number the assistant states must be traceable
  to the query result at the precision it was written; anything else is replaced by
  a deterministic sentence. See [Trustworthy answers](#trustworthy-answers).
- **Nothing is charted silently** — widgets report what share of rows backs them
  and which column cost the rest, and the agent refuses rather than substituting a
  column you didn't ask for.
- **Multi-agent pipeline** — Upload · Profiling · Quality · Cleaning · Governance ·
  SQL · Dashboard · Insight · Chat agents behind a lightweight orchestrator.
- **20+ quality checks** across Completeness, Accuracy, Consistency, Uniqueness,
  Validity, Integrity → a 0–100 score with severity levels.
- **Chat with your data** — natural language → validated, read-only DuckDB SQL →
  result table + auto chart + narrated answer.
- **Governance & PII** — automatic classification, PII detection, and
  medallion ingestion-tier recommendation.
- **Reports** — PDF report, plus CSV export of the live dataset (Excel/CSV report
  types remain available on the API).
- **455 tests, 89% backend coverage**, running fully offline.
- **Enterprise UI** — dark-first, responsive, React + Tailwind + shadcn-style +
  Recharts.

## Trustworthy answers

Wrong-but-plausible output is the main risk in a product like this, so the
guardrails are deterministic rather than prompt-based:

| Guard | What it prevents |
|---|---|
| Number grounding | A stated figure must be a faithful rounding of a real result value. `$7,945.76` and `$7,946` pass for `7945.7618`; `$7,946.16` does not. |
| Mixed-date parsing | `15/02/2024` beside `2024-04-10` in one column. A single parse silently dropped 78% of rows and collapsed a year onto one point. |
| Dirty-value warnings | `WHERE gender = 'm'` when the column also holds `M`, `male`, `Male`. Comparisons are case/whitespace-insensitive, and remaining spellings are reported rather than silently merged. |
| Aggregate intent | `SUM(...) AS avg_revenue` being narrated as an "average". |
| Dropped filters | "average revenue **for laptops**" answered across every product. |
| Column grounding | A request naming no real column is refused instead of charted against substituted columns. |
| Coverage disclosure | Row caps, null exclusions and `Other` buckets are stated, and totals still add up. |
| Axis labelling | "revenue by product" being ambiguous — axes name the column **and** the aggregation (Total / Average / Median / …). |

## Architecture

Full design in [ARCHITECTURE.md](ARCHITECTURE.md). Layered, SOLID backend
(API → Service → Repository → DB; Agents & Engines separate) and a
service/hook/component frontend (components never call the API directly).

```
Frontend (React/Vite/TS)  →  FastAPI (API → Service → Repository → SQLite)
                                     ├─ Engines  (Pandas · NumPy · DuckDB)
                                     └─ Agents   (Groq LLM · orchestrator)
```

## Tech stack

**Backend:** Python 3.12 · FastAPI · SQLAlchemy 2 · SQLite · Pandas · NumPy · DuckDB ·
PyArrow · Groq LLM (`llama-3.1-8b-instant`, configurable) · ReportLab · OpenPyXL · python-jose · passlib/bcrypt
**Frontend:** React 18 · Vite · TypeScript · Tailwind · shadcn-style UI ·
TanStack Query · React Router · Recharts · sonner
**Full dependency list:** [`backend/requirements.txt`](backend/requirements.txt) (complete `pip freeze`).

## Quick start (local)

Prerequisites: Python 3.12+, Node 20+.

### 1. Backend

```bash
cd backend
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # macOS/Linux

# Configure environment: copy the example and add your Groq key.
cp .env.example .env        # then set GROQ_API_KEY=...  (app still runs without it —
                            # AI features fall back to deterministic behavior)

python -m scripts.seed      # optional: creates a demo user + analyzed sample dataset
python main.py              # http://localhost:8000  (Swagger at /docs)
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev                # http://localhost:5173  (proxies /api → 127.0.0.1:8000)
```

If port 8000 is already taken, run the backend elsewhere and point the proxy at it:

```bash
APP_PORT=8010 python main.py                       # backend
BACKEND_URL=http://127.0.0.1:8010 npm run dev      # frontend
```

### Demo login

```
Email:    demo@datapilot.ai
Password: demo1234
```

A deliberately-messy sample dataset (`messy_sales.csv`, quality ≈ 71/100) is
pre-loaded so every feature has something dramatic to show. Run **Cleaning** to
watch it jump to ≈ 89/100.

## Docker / deploy

```bash
# Local two-service dev
docker compose up --build            # frontend :5173, backend :8000

# Single-container (frontend bundled into the API — one URL, no CORS)
docker build -t datapilot .
docker run -p 8000:8000 -e GROQ_API_KEY=sk_... -e JWT_SECRET=$(openssl rand -hex 32) datapilot
```

Free hosting (Render/HF Spaces) instructions: see [DEPLOY.md](DEPLOY.md).

## Running the evaluation

```bash
cd backend
./.venv/Scripts/python.exe -m pytest tests -q                      # Windows
./.venv/Scripts/python.exe -m pytest tests -q --cov=app            # with coverage
# source .venv/bin/activate && pytest tests -q --cov=app           # macOS/Linux
```

**455 tests, 89% backend coverage, ~30s.** The suite never calls Groq: an autouse
fixture replaces the LLM singleton, so every tab is tested twice — once with the
deterministic engines alone (proving the fallbacks) and again with a scripted model
(covering the planning branches).

| Suite | Covers |
|---|---|
| [`test_overview_tab.py`](backend/tests/test_overview_tab.py) | loader (CSV/Excel/JSON/Parquet, delimiters, encodings), profiler, data story |
| [`test_quality_tab.py`](backend/tests/test_quality_tab.py) | 20+ checks, scorer, explanations, targeted fixes |
| [`test_dashboard_tab.py`](backend/tests/test_dashboard_tab.py) | chart builders, coverage/labels, all 9 aggregations, command guards |
| [`test_chat_tab.py`](backend/tests/test_chat_tab.py) | SQL safety, number grounding, filter normalisation, narration |
| [`test_governance_edit_reports_tabs.py`](backend/tests/test_governance_edit_reports_tabs.py) | classification, PII rules, cell coercion, report writers |
| [`test_tab_service_flows.py`](backend/tests/test_tab_service_flows.py) | end-to-end service flows per tab against a real dataset |
| [`test_ai_and_validation_paths.py`](backend/tests/test_ai_and_validation_paths.py) | explain/story/compare, custom validations, LLM health |
| [`test_llm_driven_paths.py`](backend/tests/test_llm_driven_paths.py) | planner branches with a scripted model |
| [`test_remaining_tab_paths.py`](backend/tests/test_remaining_tab_paths.py) | per-issue fixes, per-fix undo, row filtering, cleaning comparison |
| [`test_api.py`](backend/tests/test_api.py) · [`test_engines.py`](backend/tests/test_engines.py) | original API + engine integration tests |

Many tests are written as regressions against wrong answers the product actually
produced — mixed-format dates collapsing a trend to one point, a narrated count taken
from a 10-row preview, `MAX` reported as a total, and an ISO date column typed as a
phone number (which flagged it as PII and hid it from every time-series chart).

- **Agent test cases:** [`tests/test_cases.json`](tests/test_cases.json) — labelled
  input / expected-output / reference-context cases for the agent's key behaviours
  (quality scoring, chat→SQL, custom validation, PII, cleaning). Each case documents
  the endpoint, input, and the expected deterministic result used to validate the agent.

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — agent node diagram, state management,
  HITL gate design, tool registry, and memory strategy.
- [`ARCHITECTURE.md`](ARCHITECTURE.md) — full system design (schema, API list, roadmap).
- [`DEPLOY.md`](DEPLOY.md) — free deployment guide.

## Project structure

```
backend/    FastAPI app: api · services · repositories · models · agents · core/engines · core/llm
              tests/    per-tab pytest suites (offline; LLM stubbed)
              scripts/  sample generation + seeding
              samples/  generated demo datasets
frontend/   React app: pages · components · services · hooks · contexts · types · layouts
docs/       architecture notes + diagrams
```

## Golden demo path (5 minutes)

Login → Upload messy dataset → **Overview** (auto-profiled, AI column descriptions) →
**Quality** (score + AI-explained issues, fix a few, undo *one* of them, "add
validation with AI") → **Chat** ("top 5 states by revenue" → SQL + chart; then
"median revenue by state") → **Dashboard** (type *"average revenue by state"* → the
agent **proposes** a KPI and a chart with coverage %, you approve one) →
**Governance** (PII + tier) → **Reports** (PDF + CSV of the fixed data).

Worth pointing out during a demo: ask something the data can't answer
(*"profit margin by warehouse"*) — the agent refuses and names your real columns
instead of charting a substitute.

## Team

- Harshal Holam
- Chetan Salunke

## Security

- No secrets in the repo — real keys live only in `backend/.env` (git-ignored).
  See [`.env.example`](.env.example) / [`backend/.env.example`](backend/.env.example)
  for the required variables.
- JWT auth (python-jose), bcrypt-hashed passwords, validated read-only SQL for chat.

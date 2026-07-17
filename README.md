# DataPilot AI

> **Enterprise AI Copilot for Data Quality, Analytics & Governance**

Think **Microsoft Fabric + Power BI Copilot + ChatGPT + a Data Quality platform**,
from a single CSV upload with zero setup.

---

## Problem statement

Enterprise teams sit on large, messy tabular data (CSV/Excel/JSON) and burn hours
before any analysis: finding quality problems, understanding what each column
means, cleaning it, and figuring out whether it's safe to use (PII/governance).
The tools that help — data-quality platforms, BI copilots, catalogs — each solve
**one** slice and assume a technical user.

**DataPilot AI** is a single AI agent that takes an uploaded dataset from
**raw → trusted** in one place: it profiles the data, scores its quality, explains
every issue in plain business language, fixes issues (with human approval and full
undo), lets a non-technical user **chat with the data** and **define new validation
rules in English**, auto-builds dashboards, and classifies governance/PII — with a
**deterministic core** so it keeps working even when the LLM is unavailable.

## What the agent does

Upload a dataset, then the agent:

1. **Profiles** every column (14 semantic types, stats, encoding/delimiter detection).
2. **Scores quality** with 20+ checks across 6 dimensions → a 0–100 score.
3. **Explains** each issue (what, why, business impact, fix) in plain language.
4. **Fixes** issues — one-click per issue or "Fix all", with a snapshot-based **undo**
   and a **human-approval gate** for low-quality data (HITL).
5. **Lets you add your own validations in English** — "flag rows where revenue is 0"
   → AI proposes a rule → you approve → it becomes a live check.
6. **Answers questions in natural language** — chat → validated read-only DuckDB SQL
   → table + auto chart + narrated answer, with conversation memory.
7. **Builds dashboards** (KPIs + charts) and supports "create a chart from a sentence".
8. **Classifies governance & PII** and recommends a Bronze/Silver/Gold tier.
9. **Exports** PDF / Excel reports with the profile, dashboard charts and issues.

Every AI feature has a **deterministic fallback**, so the product never breaks when
the LLM is rate-limited or offline.

---

## Highlights

- **Deterministic core, AI garnish** — profiling, quality checks, cleaning and
  SQL run deterministically (Pandas/DuckDB), so the product works even if the
  LLM is slow or unavailable. The LLM *explains, narrates and recommends* on top.
- **Multi-agent pipeline** — Upload · Profiling · Quality · Cleaning · Governance ·
  SQL · Dashboard · Insight · Chat agents behind a lightweight orchestrator.
- **20+ quality checks** across Completeness, Accuracy, Consistency, Uniqueness,
  Validity, Integrity → a 0–100 score with severity levels.
- **Chat with your data** — natural language → validated, read-only DuckDB SQL →
  result table + auto chart + narrated answer.
- **Governance & PII** — automatic classification, PII detection, and
  medallion ingestion-tier recommendation.
- **Reports** — PDF, Excel, CSV, JSON exports.
- **Enterprise UI** — dark-first, responsive, React + Tailwind + shadcn-style +
  Recharts.

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
npm run dev                # http://localhost:5173  (proxies /api → :8000)
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
./.venv/Scripts/python.exe -m pytest tests -q     # unit + API integration tests (Windows)
# source .venv/bin/activate && pytest tests -q     # macOS/Linux
```

- **Automated tests:** [`backend/tests/test_api.py`](backend/tests/test_api.py) (end-to-end
  auth → upload → analyze → chat flow) and [`backend/tests/test_engines.py`](backend/tests/test_engines.py)
  (profiler, quality checks, scorer, cleaner).
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
frontend/   React app: pages · components · services · hooks · contexts · types · layouts
scripts/    sample generation + seeding
```

## Golden demo path (5 minutes)

Login → Upload messy dataset → Overview (auto-profiled) → **Quality** (score +
AI-explained issues, one-click fixes, "add validation with AI") →
**Chat** ("top 5 states by revenue" → SQL + chart) → **Dashboard** (auto charts) →
**Governance** (PII + tier) → **Reports** (export PDF).

## Team

- Harshal Holam
- Chetan Salunke

## Security

- No secrets in the repo — real keys live only in `backend/.env` (git-ignored).
  See [`.env.example`](.env.example) / [`backend/.env.example`](backend/.env.example)
  for the required variables.
- JWT auth (python-jose), bcrypt-hashed passwords, validated read-only SQL for chat.

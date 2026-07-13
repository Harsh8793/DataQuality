# DataPilot AI

> **Enterprise AI Copilot for Data Quality, Analytics & Governance**

An AI-first platform that ingests messy datasets and — through a multi-agent
pipeline — profiles them, scores quality across six dimensions, explains every
issue in business terms, cleans the data with one click, answers natural-language
questions (chat-with-data → SQL → chart), auto-builds dashboards, classifies
governance/PII, recommends a Bronze/Silver/Gold ingestion tier, and exports
reports.

Think **Microsoft Fabric + Power BI Copilot + ChatGPT + a Data Quality platform**.

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

**Backend:** Python · FastAPI · SQLAlchemy · SQLite · Pandas · NumPy · DuckDB ·
PyArrow · Groq (llama-3.3-70b) · LangChain · ReportLab · OpenPyXL
**Frontend:** React · Vite · TypeScript · Tailwind · shadcn-style UI ·
TanStack Query · React Router · Recharts · React Hook Form · Zod

## Quick start (local)

Prerequisites: Python 3.12+, Node 20+.

### 1. Backend

```bash
cd backend
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt   # Windows
# source .venv/bin/activate && pip install -r requirements.txt  # macOS/Linux

# Set your Groq key in backend/.env (GROQ_API_KEY=...). The app still runs
# without it — AI features fall back to deterministic explanations.

python -m scripts.seed     # creates demo user + analyzed sample dataset
python main.py             # http://localhost:8000  (Swagger at /docs)
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

## Docker

```bash
docker compose up --build   # frontend :5173, backend :8000
```

## Project structure

```
backend/    FastAPI app: api · services · repositories · models · agents · core/engines · core/llm
frontend/   React app: pages · components · services · hooks · contexts · types · layouts
scripts/    sample generation + seeding
```

## Golden demo path (5 minutes)

Login → Upload messy dataset → Overview (auto-profiled) → **Quality** (71/100 +
AI-explained issues) → **Cleaning** (one click → 89/100, before/after) →
**Chat** ("top 5 states by revenue" → SQL + chart) → **Dashboard** (auto charts) →
**Governance** (PII + Bronze tier) → **Reports** (export PDF).
